import itertools
from copy import copy

try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin

from zope.interface import implements

from twisted.names import dns
from twisted.names.client import Resolver
from twisted.web.iweb import IBodyProducer

from twisted.internet import defer
from twisted.internet import reactor, protocol, endpoints
from twisted.web import client, _newclient, http_headers

from ooni.utils import log

from ooni.network import isIPAddress
from twisted.internet.error import DNSLookupError
from ooni.errors import MaximumRedirects
from ooni.network.dns import getSystemResolver

# These user agents are taken from the "How Unique Is Your Web Browser?"
# (https://panopticlick.eff.org/browser-uniqueness.pdf) paper as the browser user
# agents with largest anonymity set.
userAgents = ("Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.1.7) Gecko/20091221 Firefox/3.5.7",
              "Mozilla/5.0 (iPhone; U; CPU iPhone OS 3 1 2 like Mac OS X; en-us) AppleWebKit/528.18 (KHTML, like Gecko) Mobile/7D11",
              "Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.2) Gecko/20100115 Firefox/3.6",
              "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.2) Gecko/20100115 Firefox/3.6",
              "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.2) Gecko/20100115 Firefox/3.6",
              "Mozilla/5.0 (Windows; U; Windows NT 5.1; de; rv:1.9.2) Gecko/20100115 Firefox/3.6",
              "Mozilla/5.0 (Windows; U; Windows NT 6.1; de; rv:1.9.2) Gecko/20100115 Firefox/3.6",
              "Mozilla/5.0 (Windows; U; Windows NT 5.1; de; rv:1.9.2) Gecko/20100115 Firefox/3.6",
              "Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.7) Gecko/20091221 Firefox/3.5.7",
              "Mozilla/5.0 (Windows; U; Windows NT 5.1; de; rv:1.9.1.7) Gecko/20091221 Firefox/3.5.7 (.NET CLR 3.5.30729)")


class StringProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


class BodyReceiver(protocol.Protocol):

    def __init__(self, finished, content_length=None, body_processor=None):
        self.finished = finished
        self.data = []
        self.bytes_remaining = content_length
        self.body_processor = body_processor

    def dataReceived(self, b):
        self.data.append(b)
        if self.bytes_remaining:
            if self.bytes_remaining == 0:
                self.connectionLost(None)
            else:
                self.bytes_remaining -= len(b)

    def connectionLost(self, reason):
        try:
            if self.body_processor:
                self.data = self.body_processor(''.join(self.data))
            self.finished.callback(''.join(self.data))
        except Exception as exc:
            self.finished.errback(exc)


class Downloader(protocol.Protocol):

    def __init__(self, download_path,
                 finished, content_length=None):
        self.finished = finished
        self.bytes_remaining = content_length
        self.fp = open(download_path, 'w+')

    def dataReceived(self, b):
        self.fp.write(b)
        if self.bytes_remaining:
            if self.bytes_remaining == 0:
                self.connectionLost(None)
            else:
                self.bytes_remaining -= len(b)

    def connectionLost(self, reason):
        self.fp.flush()
        self.fp.close()
        self.finished.callback(None)


class TrueOrderedHeaders(http_headers.Headers):

    def __init__(self, rawHeaders=None):
        self._rawHeaders = []
        if isinstance(rawHeaders, list):
            for name, value in rawHeaders:
                if isinstance(value, list):
                    for v in value:
                        self.addRawHeader(name, v)
                else:
                    self.addRawHeader(name, value)
        elif isinstance(rawHeaders, dict):
            for name, values in rawHeaders.iteritems():
                for value in values:
                    self.addRawHeader(name, value)

    def removeHeader(self, name):
        for header in self._rawHeaders:
            h_name, _ = header
            if name.lower() == h_name.lower():
                self._rawHeaders.remove(header)

    def setRawHeaders(self, name, values):
        if not isinstance(values, list):
            raise TypeError("Header entry %r should be list or str but found "
                            "instance of %r instead" % (name, type(values)))
        self.removeHeader(name)
        for value in values:
            self._rawHeaders.append((name, values))

    def addRawHeader(self, name, value):
        self._rawHeaders.append((name, value))

    def hasHeader(self, name):
        for h_name, h_value in self._rawHeaders:
            if h_name.lower() == name.lower():
                return True
        return False

    def getAllRawHeaders(self):
        for name, value in self._rawHeaders:
            yield name, [value]

    def getRawHeaders(self, name, default=None):
        values = []
        for h_name, h_value in self._rawHeaders:
            if name.lower() == h_name.lower():
                values.append(h_value)
        if len(values) > 0:
            return values
        return default

    def getDiff(self, headers, ignore=[]):
        """

        Args:

            headers: a TrueHeaders object

            ignore: specify a list of header fields to ignore

        Returns:

            a set containing the header names that are not present in
            header_dict or not present in self.
        """
        diff = set()
        field_names = set()

        headers_a = copy(self)
        headers_b = copy(headers)
        for name_to_ignore in ignore:
            headers_a.removeHeader(name_to_ignore)
            headers_b.removeHeader(name_to_ignore)

        for k, v in itertools.chain(headers_a.getAllRawHeaders(),
                                    headers_b.getAllRawHeaders()):
            field_names.add(k)

        for name in field_names:
            if self.getRawHeaders(name) and headers.getRawHeaders(name):
                pass
            else:
                diff.add(name)
        return diff


class _HTTPClientParser(_newclient.HTTPClientParser):

    def logPrefix(self):
        return 'HTTPClientParser'

    def connectionMade(self):
        """
        Taken from Twisted 14.0.0.

        Use TrueHeaders instead of regular headers.
        """
        from twisted.web._newclient import STATUS
        self.headers = TrueOrderedHeaders()
        self.connHeaders = TrueOrderedHeaders()
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

    def __init__(self, response, request, dns_resolutions, proxy=None):
        self.headers = response.headers
        self.code = response.code
        self.version = response.version
        self.phrase = response.phrase
        self.headers = response.headers
        self.request = request
        self.body = None
        self.proxy = None
        self.failure_string = ""
        self.dns_resolutions = dns_resolutions

        self.body_deferred = defer.Deferred()
        self.body_deferred.addCallback(self._received_body)
        self.previous_response = None

    def pprint(self):
        ret = "Status: %s\n" % self.code
        ret += "Headers:\n"
        for name, value in self.headers.getAllRawHeaders():
            ret += "%s: %s\n" % (name, value)
        if self.dns_resolutions:
            ret += "DNS Resolutions:\n"
            ret += '\n'.join(x.payload.dottedQuad()
                             for x in self.dns_resolutions[0])
        ret += "\n"
        ret += "Body:\n"
        ret += self.body
        ret += "\n"
        return ret

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
    _redirect_codes = (301, 302, 303, 307)
    _query_timeout = [3, 0]

    def __init__(self, reactor=reactor, agent=None, dns_resolver=None):
        self.agent = agent
        self._reactor = reactor
        self.dns_resolver = dns_resolver
        self.dns_resolutions = {}
        if not agent:
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

    def _create_request(self, method, parsed_uri, headers, body):
        headers = TrueOrderedHeaders(headers)
        if not headers.hasHeader('host'):
            headers = headers.copy()
            headers.addRawHeader(
                'Host', self._compute_host_value(parsed_uri)
            )

        bodyProducer = None
        if body:
            bodyProducer = StringProducer(body)

        request = _newclient.Request._construct(
            method, parsed_uri.originForm, headers, bodyProducer, parsed_uri
        )
        request.body = body
        return request

    def _getTLSPolicy(self, host, port):
        if hasattr(self.agent, '_policyForHTTPS'):
            return self.agent._policyForHTTPS.creatorForNetloc(host, port)
        else:
            return self.agent._wrapContextFactory(host, port)

    def _getProxyEndpoint(self, parsed_uri, proxy):
        from twisted.web.client import SchemeNotSupported
        proxy_host, proxy_port = proxy
        proxy_endpoint = endpoints.TCP4ClientEndpoint(self._reactor,
                                                      proxy_host,
                                                      proxy_port)
        if parsed_uri.scheme not in ('http', 'https'):
            raise SchemeNotSupported('unsupported scheme', parsed_uri.scheme)
        endpoint = self.agent.endpointFactory(
            parsed_uri.host, parsed_uri.port,
            proxy_endpoint)
        if parsed_uri.scheme == 'https':
            if hasattr(self.agent, '_wrapContextFactory'):
                tlsPolicy = self.agent._wrapContextFactory(parsed_uri.host, parsed_uri.port)
            elif hasattr(self.agent, '_policyForHTTPS'):
                tlsPolicy = self.agent._policyForHTTPS.creatorForNetloc(parsed_uri.host, parsed_uri.port)
            else:
                raise NotImplementedError("can't figure out how to make a context factory")
            endpoint = self.agent._tlsWrapper(tlsPolicy, endpoint)
        return endpoint

    def _getEndpoint(self, host, scheme, port):
        return self.agent._getEndpoint(scheme, host, port)

    def _resolve(self, parsed_uri):
        if parsed_uri.host in self.dns_resolutions:
            return self.dns_resolutions[parsed_uri.host]

        query = dns.Query(parsed_uri.host, dns.A, dns.IN)
        if self.dns_resolver:
            resolver = Resolver(servers=[self.dns_resolver])
        else:
            resolver = getSystemResolver()
        return resolver.query(query, timeout=self._query_timeout)

    def _handle_resolution(self, result, host, port):
        ip = None
        for answer in result[0]:
            if answer.type is dns.A:
                ip = answer.payload.dottedQuad()
        if not ip:
            raise DNSLookupError(self)

        self.dns_resolutions[host] = result
        return ip

    def connect(self, parsed_uri, proxy):
        factory = _HTTPClientFactory()
        if proxy:
            endpoint = self._getProxyEndpoint(parsed_uri, proxy)
            return endpoint.connect(factory)

        if not isIPAddress(parsed_uri.host):
            d = defer.maybeDeferred(self._resolve, parsed_uri)
            d.addCallback(self._handle_resolution, parsed_uri.host,
                          parsed_uri.port)
        else:
            d = defer.Deferred()
            d.callback(parsed_uri.host)

        d.addCallback(self._getEndpoint, parsed_uri.scheme, parsed_uri.port)
        d.addCallback(lambda endpoint: endpoint.connect(factory))
        return d

    def _handle_response(self, response, host, request, body_receiver,
                         ignore_body, previous_response, proxy):
        try:
            dns_resolution = self.dns_resolutions[host]
        except KeyError:
            dns_resolution = []
        r = Response(response, request, dns_resolution, proxy)

        if ignore_body:
            return r
        if body_receiver:
            response.deliverBody(body_receiver)
            return r
        else:
            response.deliverBody(r.deliverBody())
            return r.body_deferred

    def _handle_redirect(self, response, method, uri, headers, body,
                         body_receiver, ignore_body, redirect_count,
                         proxy):
        if response.code in self._redirect_codes:
            if redirect_count >= self._maximum_redirects:
                raise MaximumRedirects()
            new_location = response.headers.getRawHeaders('location')[0]
            new_uri = urljoin(uri, new_location)
            return self.request(method, new_uri, headers, body, body_receiver,
                                ignore_body, previous_response=response,
                                follow_redirects=True,
                                redirect_count=redirect_count + 1,
                                proxy=proxy)
        return response

    def _set_previous_response(self, response, previous_response):
        response.previous_response = previous_response
        return response

    def request(self, method, uri, headers, body=None,
                body_receiver=None, ignore_body=False,
                follow_redirects=False, previous_response=None,
                redirect_count=0, proxy=None):
        d = defer.Deferred()

        parsed_uri = client._URI.fromBytes(uri)

        ed = self.connect(parsed_uri, proxy)

        request = self._create_request(method, parsed_uri, headers, body)

        @ed.addCallback
        def connected(proto):
            proto.request(request).chainDeferred(d)

            @d.addCallback
            def cb(result):
                if proto.transport:
                    proto.transport.loseConnection()
                return result

            @d.addErrback
            def eb(error):
                d.errback((error, request))

        @ed.addErrback
        def eb(error):
            d.errback((error, request))

        d.addCallback(self._handle_response, parsed_uri.host, request,
                      body_receiver, ignore_body, previous_response, proxy)

        if previous_response:
            d.addCallback(self._set_previous_response, previous_response)

        if follow_redirects:
            d.addCallback(self._handle_redirect, method, uri, headers, body,
                          body_receiver, ignore_body, redirect_count, proxy)

        return d

    def get(self, *args, **kw):
        return self.request("GET", *args, **kw)

    def put(self, *args, **kw):
        return self.request("PUT", *args, **kw)

    def post(self, *args, **kw):
        return self.request("POST", *args, **kw)

    def delete(self, *args, **kw):
        return self.request("DELETE", *args, **kw)
