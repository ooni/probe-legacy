from twisted.internet import defer, reactor
from twisted.trial import unittest

from twisted.web.test.test_agent import FakeReactorAndConnectMixin

from ooni.network import http, randomFreePort

import twisted.internet.base
twisted.internet.base.DelayedCall.debug = True

from ooni.tests import is_internet_connected
from ooni.tests.network_helpers import returnHeadersSite

class BaseNetworkTest(unittest.TestCase):
    def setUp(self):
        self.portNumber = randomFreePort()
        self.httpServer = reactor.listenTCP(self.portNumber, returnHeadersSite)
        self.baseUrl = 'http://127.0.0.1:%d' % self.portNumber

    def tearDown(self):
        return self.httpServer.stopListening()

class TestNetworkOffline(BaseNetworkTest):
    @defer.inlineCallbacks
    def test_get_request(self):
        request = http.Request()
        response = yield request.get(self.baseUrl + '/redirect/2',
                                     headers={'Some-Header': ['Value']},
                                     follow_redirects=True)
        print response.headers
        print response.body
        print response.code
        for r in response.responseChain():
            print r.pprint()

class TestNetworkViaInternetHTTP(unittest.TestCase, FakeReactorAndConnectMixin):

    def setUp(self):
        if not is_internet_connected():
            self.skipTest(
                "You must be connected to the internet to run this test"
            )
        self.request = http.Request()

    @defer.inlineCallbacks
    def test_get_request_google(self):
        request = http.Request()
        response = yield request.get('http://google.com/',
                                     headers={'Some-Header': ['Value']},
                                     follow_redirects=True)
        print response.headers
        print response.body
        print response.code
        for r in response.responseChain():
            print r.pprint()

    @defer.inlineCallbacks
    def test_get_request(self):
        request = http.Request()
        response = yield request.get('http://httpbin.org/redirect/2',
                                     headers={'Some-Header': ['Value']},
                                     follow_redirects=True)
        print response.headers
        print response.body
        print response.code
        for r in response.responseChain():
            print r.pprint()

    @defer.inlineCallbacks
    def test_get_request_proxy(self):
        request = http.Request()
        response = yield request.get('http://httpbin.org/redirect/2',
                                     headers={'Some-Header': ['Value']},
                                     follow_redirects=True,
                                     proxy=('127.0.0.1', 9050))
        print response.headers
        print response.body
        print response.code
        for r in response.responseChain():
            print r.pprint()

    def test_get_headers(self):
        pass

    def test_get_body(self):
        pass
