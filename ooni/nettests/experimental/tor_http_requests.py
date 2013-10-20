from twisted.internet import reactor
from twisted.web.client import RedirectAgent, readBody

from ooni.settings import config
from ooni.templates.tort import TorTest
from ooni.utils.trueheaders import TrueHeaders
from ooni.utils.tor import OnionRoutedTrueHeadersAgent, TorCircuitContextFactory
from ooni.utils.tor import SingleExitStreamAttacher
from ooni.errors import handleAllFailures

class TorHTTPRequests(TorTest):
    name = "Tor HTTP Requests Test"
    version = "0.1"
    description = "Fetches a list of URLs over each exit"

    inputFile = ['file', 'f', None,
            'List of URLS to perform GET requests to']
    requiredOptions = ['file']

    def getInputProcessor(self):
        #XXX: doesn't seem that we have any of the exitpolicy available :\
        #XXX: so the circuit might fail if port 80 isn't allowed
        if self.inputFileSpecified:
            self.inputFilename = self.localOptions[self.inputFile[0]]
            urls = open(self.inputFilename)
            for exit in self.exits:
                for url in urls:
                    yield (exit.id_hex, url.strip())      
                urls.seek(0)

    def test_get(self):
        user_agent = "Mozilla/5.0 (Windows NT 6.1; rv:24.0) Gecko/20100101 Firefox/24.0"
        exit_hex, url = self.input
        try:
            exit = self.state.routers[exit_hex]
        except KeyError:
            # Router not in consensus, sorry
            self.report['failure'] = "Router %s not in consensus." % self.input
            return

        if 'requests' not in self.report:
            self.report['requests'] = []

        request = {'method': "GET", 'url': url,
                'headers': {'User-Agent':[ user_agent ]}}
        self.report['request'] = request
        headers = TrueHeaders(request['headers'])

        # follow redirects
        agent = RedirectAgent(OnionRoutedTrueHeadersAgent(reactor,
            torCircuitContextFactory=TorCircuitContextFactory(self.state,
                SingleExitStreamAttacher(self.state, exit))))
        d = agent.request("GET", url, headers=headers)

        def errback(failure):
            self.report['failure'] = handleAllFailures(failure)
            return failure

        def addToReport(response):
            self.report['response'] = {
                    'headers': list(response.headers.getAllRawHeaders()),
                    'code': response.code
                    }
            return response

        def addBodyToReport(body):
            self.report['response']['body'] = body

        d.addCallback(addToReport)
        d.addCallback(readBody)
        d.addCallback(addBodyToReport)
        d.addErrback(errback)
        return d
