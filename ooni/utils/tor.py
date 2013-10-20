from twisted.internet import defer, reactor, interfaces
from twisted.internet.endpoints import TCP4ClientEndpoint, _WrappingFactory
from twisted.web.client import SchemeNotSupported
from txsocksx.client import SOCKS5ClientFactory
from txsocksx.tls import TLSWrapClientEndpoint
from txtorcon import CircuitListenerMixin, IStreamAttacher, StreamListenerMixin
from zope.interface import implementer

from ooni.utils import log
from ooni.utils.trueheaders import TrueHeadersAgent
from ooni.settings import config
import random

@implementer(interfaces.IStreamClientEndpoint)
class TorCircuitContextFactory(object):
    def __init__(self, torState, streamAttacher):
        """
        @param torState: An instance of L{txtorcon.torstate.TorState}
        @param streamAttacher: An instance of L{txtorcon.IStreamAttacher}
        """
        self.state = torState
        self.streamAttacher = streamAttacher

@implementer(interfaces.IStreamClientEndpoint)
class OnionRoutedTCPClientEndpoint(object):
    def __init__(self, reactor, host, port, torCircuitContextFactory):
        """
        @param reactor: An L{IReactorTCP} provider

        @param host: A hostname, used when connecting
        @type host: str

        @param port: The port number, used when connecting
        @type port: int

        @param torCircuitContextFactory: An instance of
            L{TorCircuitContextFactory}

        This endpoint will be routed through Tor over a circuit whose construction is defined by the torCircuitContextFactory.
        STREAM events 
        """
        self.host = host
        self.port = port
        self.torCircuitContextFactory = torCircuitContextFactory

    def connect(self, protocolFactory):
        """
        Implements L{IStreamClientEndpoint.connect} to connect via TCP, after
        SOCKS5 negotiation and Tor circuit construction is done.

        The WrappingFactory is used so that the addLocalStream method of the
        relavent streamAttacher is called first, and the local socket can
        then be used to match the stream_id from Tor.
        """

        proxyEndpoint = TCP4ClientEndpoint(reactor, '127.0.0.1', config.tor.socks_port)
        proxyFac = _WrappingFactory(SOCKS5ClientFactory(self.host, self.port, protocolFactory))
        sA = self.torCircuitContextFactory.streamAttacher
        proxyFac._onConnection.addCallback(
                        lambda proto: sA.addLocalStream(proto.transport))
        d = proxyEndpoint.connect(proxyFac)
        d.addCallback(lambda proto: proxyFac._wrappedFactory.deferred)
        return d

class OnionRoutedTrueHeadersAgent(TrueHeadersAgent):
    _tlsWrapper = TLSWrapClientEndpoint

    def __init__(self, *args, **kw):
        self.torCircuitContextFactory = kw.pop('torCircuitContextFactory')
        super(OnionRoutedTrueHeadersAgent, self).__init__(*args, **kw)

    def _getEndpoint(self, scheme, host, port):
        if scheme not in ('http', 'https'):
            raise SchemeNotSupported('unsupported scheme', scheme)
        endpoint = OnionRoutedTCPClientEndpoint(reactor, host, port,
                self.torCircuitContextFactory)
        if scheme == 'https':
            if hasattr(self, '_wrapContextFactory'):
                tlsPolicy = self._wrapContextFactory(host, port)
            elif hasattr(self, '_policyForHTTPS'):
                tlsPolicy = self._policyForHTTPS.creatorForNetloc(host, port)
            else:
                raise NotImplementedError("can't figure out how to make a context factory")
            endpoint = self._tlsWrapper(tlsPolicy , endpoint)
        return endpoint

@implementer(IStreamAttacher)
class MetaAttacher(CircuitListenerMixin, StreamListenerMixin):
    """
    txtorcon supports a single attacher.

    This MUST be instanced in order to proxy attach_stream calls to instanced
    subclasses.

    FIXME: Maybe there's a better way to do this...
    """
    _streamToAttacherMap = {}
    def __init__(self, state):
        self.state = state
        self.state.set_attacher(self, reactor)

    def attach_stream(self, stream, circuits):
        try:
            key = (str(stream.source_addr), int(stream.source_port))
            return self._streamToAttacherMap[key].attach_stream(stream, circuits)
        except KeyError:
            # No streamAttachers have claimed this stream; default to Tor.
            return None

class StreamAttacher(MetaAttacher):
    """
    An instance of this StreamAttacher will attach all streams to randomly
    selected (unweighted) circuits.  Not guarranteed to work, as we do not know
    the ExitPolicy of the chosen exit.

    FIXME: How do we get the ExitPolicy?
    """
    def __init__(self, state):
        self.state = state
        self.waiting_circuits = {}
        self.expected_streams = {}
        self.built_circuits = {}
        self.state.add_stream_listener(self)
        self.state.add_circuit_listener(self)

    def addLocalStream(self, transport):
        """
        Add a locally initiated stream to this StreamAttacher.
        """
        getHost = transport.getHost()
        key = (str(getHost.host),int(getHost.port))
        MetaAttacher._streamToAttacherMap[key] = self
        d = defer.Deferred()
        self.expected_streams[key] = d
        self.request_circuit_build(d)

    def request_circuit_build(deferred_to_callback):
        """
        This example just picks a random path, and will callback the deferred
        when the circuit is created or errback if the circuit fails.
        """
        path = [ random.choice(self.state.entry_guards.values()),
                 random.choice(self.state.routers.values()),
                 random.choice(self.state.exits.values()) ]
        
        def addToWaitingCircs(circ):
            self.waiting_circuits[circ.id] = (circ, deferred_to_callback)

        d = self.state.build_circuit(path)
        d.addCallback(addToWaitingCircs)

    def attach_stream(self, stream, circuits):
        try:
            key = (str(stream.source_addr), int(stream.source_port))
            log.debug(str(stream))
            return self.expected_streams[key]
        except KeyError:
            # We didn't expect this stream, so let Tor handle it
            return None

    def circuit_built(self, circuit):
        if circuit.purpose != "GENERAL":
            return
        try:
            log.debug(str(circuit))
            (circ, d) = self.waiting_circuits.pop(circuit.id)
            self.built_circuits[circuit.id] = (circuit, d)
            d.callback(circuit)
        except KeyError:
            pass

    def circuit_closed(self, circuit, **kw):
        try:
            (circ, d) = self.waiting_circuits.pop(circuit.id)
            log.debug(str(circuit))
        except KeyError:
            pass
        try:
            (circ, d) = self.built_circuits.pop(circuit.id)
        except KeyError:
            pass

    def circuit_failed(self, circuit, **kw):
        try:
            (circ, d) = self.waiting_circuits.pop(circuit.id)
            log.debug(str(circuit))
        except KeyError:
            pass
        try:
            (circ, d) = self.built_circuits.pop(circuit.id)
            log.debug(str(circuit))
        except KeyError:
            pass
    def stream_closed(self, stream, **kw):
        try:
            key = (str(stream.source_addr), int(stream.source_port))
            d = self.expected_streams.pop(key)
            log.debug(str(stream))
            MetaAttacher._streamToAttacherMap.pop(key)
        except KeyError:
            pass

    def stream_detach(self, stream, **kw):
        # Should we reattach the stream? Log error?
        # close the stream and circuit?
        try:
            key = (str(stream.source_addr), int(stream.source_port))
            d = self.expected_streams.pop(key)
            log.debug(str(stream))
            MetaAttacher._streamToAttacherMap.pop(key)
            stream.close()
        except KeyError:
            pass

    def stream_failed(self, stream, reason='', remote_reason='', **kw):
        try:
            key = (str(stream.source_addr), int(stream.source_port))
            d = self.expected_streams.pop(key)
            log.debug(str(stream))
            MetaAttacher._streamToAttacherMap.pop(key)
        except KeyError:
            pass

    def __del__(self):
        # Clean up all of the circuits we created
        #XXX: requires txtorcon 0.9.0 (git master)
        try:
            for circ, d in self.built_circuits.values():
                circ.close(ifUnused=True)
        except AttributeError:
            pass

class SingleExitStreamAttacher(StreamAttacher):
    """
    An instance of this StreamAttacher will attach all streams to
    circuits with the same exit (or fail).
    """
    def __init__(self, state, exit):
        self.exit = exit
        super(SingleExitStreamAttacher, self).__init__(state)

    def request_circuit_build(self, deferred_to_callback):
        # see if we already have a circuit
        #for circ in self.state.circuits.values():
        #    if (len(circ.path) >= 3) and (circ.path[-1].id_hex == self.exit.id_hex)  and (circ.state == 'BUILT'):
        #        log.debug("Re-Using circ %s" % circ)
        #        deferred_to_callback.callback(circ)
        #        return

        path = [ random.choice(self.state.entry_guards.values()),
                 random.choice(self.state.routers.values()),
                 self.exit ]
        
        def addToWaitingCircs(circ):
            self.waiting_circuits[circ.id] = (circ, deferred_to_callback)

        self.state.build_circuit(path).addCallback(addToWaitingCircs)

    def circuit_built(self, circuit):
        if circuit.purpose != "GENERAL":
            return
        try:
            (circ, d) = self.waiting_circuits.pop(circuit.id)
            assert circuit.path[-1] is self.exit
            self.built_circuits[circuit.id] = (circuit, d)
            d.callback(circuit)
        except KeyError:
            pass
