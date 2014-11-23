from twisted.python import usage
from twisted.internet import reactor
from twisted.web.client import readBody

from ooni.templates.tort import TorTest
from ooni.utils import log
from ooni.utils.tor import OnionRoutedAgent, TorCircuitContextFactory
from ooni.utils.trueheaders import TrueHeaders
from ooni.utils.tor import SpecificPathStreamAttacher
from ooni.errors import handleAllFailures
import random
import time

"""
Fetch the Tor Network Consensus
Sort relays by advertised bandwidth (or consensus weight?)
Select a (local) relay as a first hop
Build circuit

"""
class BwScanTest(TorTest):
    name = "Tor Bandwidth Scan"
    version = "0.1"
    description = "Measures the throughput of relays in the Tor Network Consensus"

    inputFile = ['file', 'f', None, 'List of URLs to fetch']
    requiredOptions = ['file']

    # shared state for all instances of this test
    _stream_bw_timer = {}
    circuits = {}

    def setUp(self):
        super(BwScanTest, self).setUp()
        # Add a bw event listener
        self.state.protocol._set_valid_events('STREAM_BW')
        self.state.protocol.add_event_listener('STREAM_BW', self.streamEventHandler)

    def getInputProcessor(self):
        if self.inputFileSpecified:
            self.inputFilename = self.localOptions[self.inputFile[0]]
            urls = open(self.inputFilename)

            for relay in self.relays:
                for url in urls:
                    yield relay.id_hex, url.strip()
                urls.seek(0)

    def test_stream_bw(self):
        relay_hex, url = self.input
        if relay_hex not in self.state.routers:
            self.report['failure'] = "Router %s not in consensus." % relay_hex
            return

        exit = relay = self.state.routers[relay_hex]
        while exit == relay:
            #XXX: should be above what bw value?
            exit = random.choice(self.exits)

        #XXX: may/should? be a local relay
        guard = random.choice(self.guards)
        path = [ guard, relay, exit ]

        user_agent = "Mozilla/5.0 (Windows NT 6.1; rv:24.0) Gecko/20100101 Firefox/24.0"
        headers = TrueHeaders({'User-Agent': [user_agent]})
        agent = OnionRoutedAgent(reactor,
            torCircuitContextFactory=TorCircuitContextFactory(self.state,
                SpecificPathStreamAttacher(self.state, path)))
        d = agent.request("GET", url)

        def addBwToReport(result):
            self.report['r_bw'], self.report['w_bw'] = self.getRouterAvgBw(relay)
            return result

        def errback(failure):
            self.report['failure'] = handleAllFailures(failure)
            return failure

        d.addCallback(readBody)
        d.addCallback(addBwToReport)
        d.addErrback(errback)
        return d

    def streamEventHandler(self, event):
        now = time.time()
        streamid, bytes_wrote, bytes_read = [ int(x) for x in event.split() ]

        try:
            last = self._stream_bw_timer[streamid]
            self._stream_bw_timer[streamid] = now
            interval = now - last
            r_bs, w_bs = bytes_read / interval, bytes_wrote / interval
            circuit = self.state.streams[streamid].circuit
            if circuit not in self.circuits:
                self.circuits[circuit] = [(interval, r_bs, w_bs)]
            else:
                self.circuits[circuit].append((interval, r_bs, w_bs))

        except KeyError:
            self._stream_bw_timer[streamid] = now
        except Exception:
            import pdb;pdb.set_trace()

    def getRouterAvgBw(self, router):
        try:
            num_paths = r_bw_avg = w_bw_avg = 0
            for c in self.circuits.keys():
                if c and router in c.path:
                    bws = self.circuits[c]
                    for bw in bws:
                        r_bw_avg += bw[1]
                        w_bw_avg += bw[2]
                        num_paths += 1
            if num_paths:
                return (r_bw_avg / num_paths, w_bw_avg / num_paths)
            else:
                return (0,0)
        except Exception:
            import pdb;pdb.set_trace()
