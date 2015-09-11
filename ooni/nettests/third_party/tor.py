# -*- encoding: utf-8 -*-
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint

from ooni import nettest
from ooni.errors import handleAllFailures
from ooni.utils import log


class TCPFactory(Factory):
    def buildProtocol(self, addr):
        return Protocol()


class TorDirectoryAuthorityConnect(nettest.NetTestCase):
    name = "Tor Directory Authority Connect"
    description = "Does a TCP connection to Tor directory authorities"

    author = "Arturo Filastò"
    version = "0.1"
    inputFile = [
        'file', 'f', None,
        'dir_auths.csv file generated from the citizenlab '
        'test lists tor/dir_auths service'
    ]

    requiresTor = False
    requiresRoot = False
    requiredOptions = ['file']

    def test_connect(self):
        host, port = self.input

        def connectionSuccess(protocol):
            protocol.transport.loseConnection()
            log.debug("Got a connection to %s" % self.input)
            self.report["connection"] = 'success'

        def connectionFailed(failure):
            self.report['connection'] = handleAllFailures(failure)

        from twisted.internet import reactor
        point = TCP4ClientEndpoint(reactor, host, int(port))
        d = point.connect(TCPFactory())
        d.addCallback(connectionSuccess)
        d.addErrback(connectionFailed)
        return d

    def inputProcessor(self, filename=None):
        if filename is not None:
            print "Filename %s" % filename
            with open(filename) as f:
                import csv
                csv_reader = csv.reader(f)
                for row in csv_reader:
                    yield (row[1], int(row[6]))
        else:
            pass
