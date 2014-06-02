from twisted.internet import defer
from twisted.trial import unittest
from twisted.web.test.test_agent import FakeReactorAndConnectMixin

from ooni.network import http


class TestNetworkHTTP(unittest.TestCase, FakeReactorAndConnectMixin):
    def setUp(self):
        self.request = http.Request()

    @defer.inlineCallbacks
    def test_get_request(self):
        request = http.Request()
        response = yield request.get('http://httpbin.org/redirect/2',
                                     headers={'Some-Header': ['Value']},
                                     follow_redirects=True)
        print response.headers
        print response.body
        print response.code
        print list(response.responseChain())

    def test_get_headers(self):
        pass

    def test_get_body(self):
        pass
