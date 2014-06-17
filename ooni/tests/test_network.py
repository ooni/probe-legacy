from twisted.internet import defer
from twisted.trial import unittest
from twisted.web.test.test_agent import FakeReactorAndConnectMixin

from ooni.network import http


class TestNetworkHTTP(unittest.TestCase, FakeReactorAndConnectMixin):
    def setUp(self):
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
