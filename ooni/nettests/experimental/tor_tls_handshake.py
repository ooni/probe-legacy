from ooni.errors import handleAllFailures
from ooni.templates.tort import TorTest
from ooni.utils.tor import OnionRoutedTCPClientEndpoint, TorCircuitContextFactory
from ooni.utils.tor import SingleExitStreamAttacher

from twisted.internet import interfaces, defer, reactor
from twisted.internet.protocol import ClientFactory, Protocol
from twisted.internet.ssl import ClientContextFactory
from twisted.protocols import tls

from txsocksx.tls import TLSWrapClientEndpoint

from zope.interface import implementer

from OpenSSL import crypto, SSL

firefox_ciphers = ["ECDHE-ECDSA-AES256-SHA",
                   "ECDHE-RSA-AES256-SHA",
                   "DHE-RSA-CAMELLIA256-SHA",
                   "DHE-DSS-CAMELLIA256-SHA",
                   "DHE-RSA-AES256-SHA",
                   "DHE-DSS-AES256-SHA",
                   "ECDH-ECDSA-AES256-CBC-SHA",
                   "ECDH-RSA-AES256-CBC-SHA",
                   "CAMELLIA256-SHA",
                   "AES256-SHA",
                   "ECDHE-ECDSA-RC4-SHA",
                   "ECDHE-ECDSA-AES128-SHA",
                   "ECDHE-RSA-RC4-SHA",
                   "ECDHE-RSA-AES128-SHA",
                   "DHE-RSA-CAMELLIA128-SHA",
                   "DHE-DSS-CAMELLIA128-SHA",]

class TorSSLObservatory(TorTest):
    name = "Tor SSL Observatory"
    version = "0.1"
    description = "Fetch the certificate chain of HTTPS URLs over Tor exits"

    inputFile = ['file', 'f', None,
            'List of URLS to perform GET requests to']
    requiredOptions = ['file']

    tofu = {}

    def test_fetch_cert_chain(self):
        exit_hex, url = self.input

        try:
            exit = self.state.routers[exit_hex]
        except KeyError:
            # Router not in consensus, sorry
            self.report['failure'] = "Router %s not in consensus." % exit_hex
            return

        if "https" in url.split(":")[0]: port = 443
        else: port = 80
            
        host = url.split("//")[1].strip()
        addr = (host,port)
        
        ciphersuite = ":".join(firefox_ciphers)

        endpoint = TLSWrapClientEndpoint(ClientContextFactory(),
                OnionRoutedTCPClientEndpoint(reactor, host, port,
                    TorCircuitContextFactory(self.state,
                        SingleExitStreamAttacher(self.state, exit))))

        gotCertChain = defer.Deferred()

        report = self.report
        tofu = self.tofu
        class DropCertChainProto(Protocol):
            def connectionMade(self):
                #XXX: Calling set_cipher_list here seems to actually change the list of
                # ciphers. Why?
                self.transport.getHandle().get_context().set_cipher_list(ciphersuite)
                #self.transport.getHandle().renegotiate()
                #XXX: send some plausible noise, because OpenSSL doesn't start the handshake
                # until we call write()
                self.transport.write(
"""GET / HTTP/1.1
Host: %s
User-Agent: Mozilla/5.0 (Windows NT 6.1; rv:24.0) Gecko/20100101 Firefox/24.0
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: en-us,en;q=0.5
Accept-Encoding: gzip, deflate
Connection: keep-alive

""" % host)
            def dataReceived(self, data):
                if gotCertChain.called:
                    return
                sslConnection = self.transport.getHandle()
                report['cipher_list'] = sslConnection.get_cipher_list()
                report['cert_chain'] = [ crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
                        for cert in sslConnection.get_peer_cert_chain() ]

                # See if we get the same certificate chain as the first request.
                report['tofu'] = True
                try:
                    assert tofu[url] == report['cert_chain']
                except KeyError:
                    tofu[url] = report['cert_chain']
                except AssertionError:
                    report['tofu'] = False

                self.transport.loseConnection()
                gotCertChain.callback(None)

        class DropCertChain(ClientFactory):
            protocol = DropCertChainProto

        d = endpoint.connect(DropCertChain())
        d.addErrback(gotCertChain.errback)

        def errback(failure):
            self.report['failure'] = handleAllFailures(failure)
            return failure

        gotCertChain.addErrback(errback)
        return gotCertChain

    def getInputProcessor(self):
        if self.inputFileSpecified:
            self.inputFilename = self.localOptions[self.inputFile[0]]
            urls = open(self.inputFilename)

            for url in urls:
                for r in self.exits:
                    yield (r.id_hex, url.strip())
