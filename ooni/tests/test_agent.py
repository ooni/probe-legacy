from twisted.internet.defer import succeed, Deferred
from twisted.internet.protocol import Protocol
from twisted.trial import unittest
from twisted.test.proto_helpers import StringTransport, MemoryReactorClock

from ooni.utils import trueheaders

class StubHTTPProtocol(Protocol):
    """
    A protocol like L{HTTP11ClientProtocol} but which does not actually know
    HTTP/1.1 and only collects requests in a list.

    @ivar requests: A C{list} of two-tuples.  Each time a request is made, a
        tuple consisting of the request and the L{Deferred} returned from the
        request method is appended to this list.
    """
    def __init__(self):
        self.requests = []
        self.state = 'QUIESCENT'


    def request(self, request):
        """
        Capture the given request for later inspection.

        @return: A L{Deferred} which this code will never fire.
        """
        result = Deferred()
        self.requests.append((request, result))
        return result

class FakeReactorAndConnectMixin:
    """
    A test mixin providing a testable C{Reactor} class and a dummy C{connect}
    method which allows instances to pretend to be endpoints.
    """
    Reactor = MemoryReactorClock

    def connect(self, factory):
        """
        Fake implementation of an endpoint which synchronously
        succeeds with an instance of L{StubHTTPProtocol} for ease of
        testing.
        """
        transport = StringTransport()
        protocol = StubHTTPProtocol()
        protocol.makeConnection(transport)
        self.protocol = protocol
        self.transport = transport
        return succeed(protocol)


class TestAgent(unittest.TestCase, FakeReactorAndConnectMixin):
    def setUp(self):
        self.reactor = self.Reactor()
        self.agent = trueheaders.TrueHeadersAgent(self.reactor)

    def test_headerOrder(self):
        sorted_headers = (
            ('X-First', [1]),
            ('X-Second', [2]),
            ('X-Third', [3]),
            ('X-Fourth', [4]),
        )
        headers = trueheaders.TrueHeaders()
        for i in range(4):
            headers.setRawHeaders(sorted_headers[i][0], sorted_headers[i][1])
        self.agent._getEndpoint = lambda *args: self
        self.agent.request('GET', 'http://example.com/foo', headers)
        self.assertEqual(len(self.protocol.requests), 1)
        self.protocol.requests[0][0]._writeHeaders(self.transport, None)
        idx = 0
        for line in self.transport.value().split('\n'):
            if line.lower().startswith('x-'):
                self.assertEqual(line.split(':')[0], sorted_headers[idx][0])
