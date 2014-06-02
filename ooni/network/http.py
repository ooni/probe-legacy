try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin

from twisted.internet import defer
from twisted.internet import reactor, protocol, endpoints
from twisted.web import client, _newclient

from ooni.utils import log

from ooni.errors import MaximumRedirects
from ooni.utils.trueheaders import TrueHeaders
from ooni.utils.net import StringProducer, BodyReceiver


class _HTTPClientParser(_newclient.HTTPClientParser):
    def logPrefix(self):
        return 'HTTPClientParser'

    def connectionMade(self):
        """
        Taken from Twisted 14.0.0.

        Use TrueHeaders instead of regular headers.
        """
        from twisted.web._newclient import STATUS
        self.headers = TrueHeaders()
        self.connHeaders = TrueHeaders()
        self.state = STATUS
        self._partialHeader = None

    def headerReceived(self, name, value):
        """
        Taken from Twisted 14.0.0.

        and removed the line that makes the Header lowecase.
        """
        if self.isConnectionControlHeader(name.lower()):
            headers = self.connHeaders
        else:
            headers = self.headers
        headers.addRawHeader(name, value)


class _HTTPClientProtocol(_newclient.HTTP11ClientProtocol):
    def request(self, request):
        """
        Issue C{request} over C{self.transport} and return a L{Deferred} which
        will fire with a L{Response} instance or an error.

        @param request: The object defining the parameters of the request to
           issue.
        @type request: L{Request}

        @rtype: L{Deferred}
        @return: The deferred may errback with L{RequestGenerationFailed} if
            the request was not fully written to the transport due to a local
            error.  It may errback with L{RequestTransmissionFailed} if it was
            not fully written to the transport due to a network error.  It may
            errback with L{ResponseFailed} if the request was sent (not
            necessarily received) but some or all of the response was lost.  It
            may errback with L{RequestNotSent} if it is not possible to send
            any more requests using this L{HTTP11ClientProtocol}.

        This is taken from Twisted 14.0.0.
        """
        from twisted.web._newclient import RequestNotSent
        from twisted.web._newclient import RequestGenerationFailed
        from twisted.web._newclient import TransportProxyProducer
        from twisted.internet.defer import Deferred, fail
        from twisted.internet.defer import maybeDeferred
        from twisted.python.failure import Failure
        from twisted.internet.defer import CancelledError

        if self._state != 'QUIESCENT':
            return fail(RequestNotSent())

        self._state = 'TRANSMITTING'
        _requestDeferred = maybeDeferred(request.writeTo, self.transport)

        def cancelRequest(ign):
            # Explicitly cancel the request's deferred if it's still trying to
            # write when this request is cancelled.
            if self._state in (
                    'TRANSMITTING', 'TRANSMITTING_AFTER_RECEIVING_RESPONSE'):
                _requestDeferred.cancel()
            else:
                self.transport.abortConnection()
                self._disconnectParser(Failure(CancelledError()))
        self._finishedRequest = Deferred(cancelRequest)

        # Keep track of the Request object in case we need to call stopWriting
        # on it.
        self._currentRequest = request

        self._transportProxy = TransportProxyProducer(self.transport)
        self._parser = _HTTPClientParser(request, self._finishResponse)
        self._parser.makeConnection(self._transportProxy)
        self._responseDeferred = self._parser._responseDeferred

        def cbRequestWrotten(ignored):
            if self._state == 'TRANSMITTING':
                self._state = 'WAITING'
                self._responseDeferred.chainDeferred(self._finishedRequest)

        def ebRequestWriting(err):
            if self._state == 'TRANSMITTING':
                self._state = 'GENERATION_FAILED'
                self.transport.abortConnection()
                self._finishedRequest.errback(
                    Failure(RequestGenerationFailed([err])))
            else:
                log.err(err, 'Error writing request, but not in valid state '
                             'to finalize request: %s' % self._state)

        _requestDeferred.addCallbacks(cbRequestWrotten, ebRequestWriting)

        return self._finishedRequest


class _HTTPClientFactory(protocol.Factory):
    def buildProtocol(self, addr):
        return _HTTPClientProtocol()


class Response(object):
    def __init__(self, response, request):
        self.headers = response.headers
        self.code = response.code
        self.version = response.version
        self.phrase = response.phrase
        self.headers = response.headers
        self.request = request
        self.body = None

        self.body_deferred = defer.Deferred()
        self.body_deferred.addCallback(self._received_body)
        self.previous_response = None

    def _received_body(self, body_data):
        self.body = body_data
        return self

    def deliverBody(self):
        return BodyReceiver(self.body_deferred)

    def responseChain(self):
        r = self
        while True:
            yield r
            if r.previous_response is not None:
                r = r.previous_response
            else:
                break


class Request(object):
    _maximum_redirects = 4
    _redirect_codes = [301, 302, 303, 307]

    def __init__(self, reactor=reactor, agent=None):
        self.agent = agent
        self._reactor = reactor
        if not self.agent:
            self.agent = client.Agent(reactor)

    def _compute_host_value(self, parsed_uri):
        """
        Compute the string to use for the value of the I{Host} header, based on
        the given scheme, host name, and port number.
        """
        if (parsed_uri.scheme, parsed_uri.port) in \
                (('http', 80), ('https', 443)):
            return parsed_uri.host
        return '%s:%d' % (parsed_uri.host, parsed_uri.port)

    def resolve_host(self, host):
        pass

    def _create_request(self, method, parsed_uri, headers, body):
        headers = TrueHeaders(headers)
        if not headers.hasHeader('host'):
            headers = headers.copy()
            headers.addRawHeader(
                'host', self._compute_host_value(parsed_uri)
            )

        bodyProducer = None
        if body:
            bodyProducer = StringProducer(body)

        return _newclient.Request._construct(
            method, parsed_uri.originForm,  headers, bodyProducer, parsed_uri,
        )

    def connect(self, parsed_uri):
        factory = _HTTPClientFactory()
        endpoint = endpoints.TCP4ClientEndpoint(self._reactor,
                                                parsed_uri.host,
                                                parsed_uri.port)
        return endpoint.connect(factory)

    def _handle_response(self, response, request, body_receiver, ignore_body,
                         previous_response):
        r = Response(response,
                     request)
        if ignore_body:
            return r
        if body_receiver:
            response.deliverBody(body_receiver)
            return r
        else:
            response.deliverBody(r.deliverBody())
            return r.body_deferred

    def _handle_redirect(self, response, method, uri, headers, body,
                         body_receiver, ignore_body, redirect_count):
        if response.code in self._redirect_codes:
            if redirect_count >= self._maximum_redirects:
                raise MaximumRedirects()
            new_location = response.headers.getRawHeaders('location')[0]
            new_uri = urljoin(uri, new_location)
            return self.execute(method, new_uri, headers, body, body_receiver,
                                ignore_body, previous_response=response,
                                follow_redirects=True,
                                redirect_count=redirect_count+1)
        return response

    def _set_previous_response(self, response, previous_response):
        response.previous_response = previous_response
        return response

    def execute(self, method, uri, headers, body=None,
                body_receiver=None, ignore_body=False,
                follow_redirects=False, previous_response=None,
                redirect_count=0):
        d = defer.Deferred()

        parsed_uri = client._URI.fromBytes(uri)

        ed = self.connect(parsed_uri)

        request = self._create_request(method, parsed_uri, headers, body)

        @ed.addCallback
        def connected(proto):
            proto.request(request).chainDeferred(d)

            @d.addCallback
            def cb(result):
                proto.transport.loseConnection()

        d.addCallback(self._handle_response, request, body_receiver,
                      ignore_body, previous_response)

        if previous_response:
            d.addCallback(self._set_previous_response, previous_response)

        if follow_redirects:
            d.addCallback(self._handle_redirect, method, uri, headers, body,
                          body_receiver, ignore_body, redirect_count)

        return d

    def get(self, *args, **kw):
        return self.execute("GET", *args, **kw)

    def put(self, *args, **kw):
        return self.execute("PUT", *args, **kw)

    def post(self, *args, **kw):
        return self.execute("POST", *args, **kw)

    def delete(self, *args, **kw):
        return self.execute("DELETE", *args, **kw)
