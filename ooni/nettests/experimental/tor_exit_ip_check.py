from twisted.web.client import readBody
from twisted.internet import reactor

from ooni.templates.tort import TorTest
from ooni.utils import log
from ooni.utils.tor import OnionRoutedTrueHeadersAgent, TorCircuitContextFactory
from ooni.utils.tor import SingleExitStreamAttacher
from ooni.errors import handleAllFailures

class TorExitIPTest(TorTest):
    name = "Tor Exit IP Test"
    version = "0.1"
    description = "Fetch the egress IP of Tor Exits"

    def getInputProcessor(self):
        #XXX: doesn't seem that we have any of the exitpolicy available :\
        #XXX: so the circuit might fail if port 80 isn't allowed
        log.debug("%d exits in consensus" % len(self.exits))
        for exit in self.exits:
            yield exit.id_hex

    def test_fetch_exit_ip(self):
        try:
            exit = self.state.routers[self.input]
            self.report['exit_ip'] = exit.ip
            log.debug("Selecting exit (%s)" % exit.ip)
        except KeyError:
            # Router not in consensus, sorry
            self.report['failure'] = "Router %s not in consensus." % self.input
            return

        agent = OnionRoutedTrueHeadersAgent(reactor,
                torCircuitContextFactory=TorCircuitContextFactory(self.state,
                    SingleExitStreamAttacher(self.state, exit)))

        d = agent.request('GET', 'http://icanhazip.com')
        d.addCallback(readBody)

        def addResultToReport(result):
            self.report['external_exit_ip'] = result.strip()
            log.debug("Found external IP %s" % self.report['external_exit_ip'])

        def addFailureToReport(failure):
            self.report['failure'] = handleAllFailures(failure)

        return d.addCallbacks(addResultToReport, errback=addFailureToReport)
