from twisted.internet import defer
from twisted.trial import unittest

from twisted.test import proto_helpers
from twisted.web.test.test_agent import FakeReactorAndConnectMixin
from twisted.web.client import Agent
from twisted.web._newclient import Response

from ooni.network import http

import twisted.internet.base
twisted.internet.base.DelayedCall.debug = True

class TestHTTPAgentWithFakeTransport(unittest.TestCase, FakeReactorAndConnectMixin):
    def setUp(self):
        self.reactor = proto_helpers.MemoryReactorClock()
        self.agent = Agent(self.reactor)
        self.agent._getEndpoint = lambda *args: self

    def test_get_request_header_list(self):
        headers = [('SoMe-Header', ['SomeValue']),
                   ('HosT', ['example.com'])]
        request = http.Request(self.reactor, self.agent)
        request.get('http://127.0.0.1/',
                    headers=headers)
        request = self.protocol.requests[0][0]
        self.assertEqual(list(request.headers.getAllRawHeaders()),
                         headers)
        self.assertEqual(request.method, "GET")

    def test_get_request_header_dict(self):
        headers = {
            'SoMe-Header': ['SomeValue'],
            'HosT': ['example.com']
        }
        request = http.Request(self.reactor, self.agent)
        request.get('http://127.0.0.1/',
                    headers=headers)
        request = self.protocol.requests[0][0]
        for name, value in headers.items():
            self.assertEqual(request.headers.getRawHeaders(name), value)
        self.assertEqual(request.method, "GET")

    @defer.inlineCallbacks
    def test_get_with_body(self):
        headers = {
            'SoMe-Header': ['SomeValue'],
            'HosT': ['example.com']
        }
        request = http.Request(self.reactor, self.agent)
        deferred = request.get('http://127.0.0.1/',
                               headers=headers)
        req, res = self.protocol.requests.pop()

        headers = http.TrueOrderedHeaders({
            'Content-length': [4]
        })
        tr = proto_helpers.StringTransport()
        response = Response(('HTTP', 1, 1), 200, 'OK', headers, tr)
        res.callback(response)
        response._bodyDataReceived("SPAM")
        response._bodyDataFinished()
        result = yield deferred
        self.assertEqual(result.body, "SPAM")

    @defer.inlineCallbacks
    def test_get_and_redirect(self):
        headers = {
            'SoMe-Header': ['SomeValue'],
            'HosT': ['example.com']
        }
        request = http.Request(self.reactor, self.agent)
        deferred = request.get('http://127.0.0.1/',
                               headers=headers,
                               follow_redirects=True)
        req, res = self.protocol.requests.pop()

        headers = http.TrueOrderedHeaders({
            'Location': ['/ham']
        })
        tr = proto_helpers.StringTransport()
        response = Response(('HTTP', 1, 1), 301, 'Moved Permanently', headers, tr)
        res.callback(response)
        response._bodyDataFinished()

        headers = http.TrueOrderedHeaders({
            'Good-Job': ['Jane']
        })
        req, res = self.protocol.requests.pop()
        self.assertEqual(req.uri, '/ham')
        response = Response(('HTTP', 1, 1), 200, 'OK', headers, tr)
        res.callback(response)
        response._bodyDataFinished()

        result = yield deferred
        responses = list(result.responseChain())
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0].headers.getRawHeaders('Good-Job'),
                         ['Jane'])
