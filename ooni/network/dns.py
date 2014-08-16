from twisted.python.runtime import platform
from twisted.names import client, dns, root

from twisted.internet import reactor
from twisted.internet.base import ThreadedResolver

class DNSAnswer(object):
    pass


class DNSError(Exception):
    pass


class InvalidRDType(DNSError):
    pass


class InvalidRDClass(DNSError):
    pass

def createResolver(servers=None):
    if platform.getType() == 'posix':
        resolver = client.Resolver(servers=servers)
        with open('/etc/resolv.conf') as resolv_conf:
            resolver.parseConfig(resolv_conf)
    else:
        resolver = root.bootstrap(ThreadedResolver(reactor))
    return resolver

def getSystemResolver():
    try:
        resolver = createResolver()
    except ValueError:
        resolver = createResolver(servers=[('127.0.0.1', 53)])
    return resolver

class DNS(object):
    protocol = 'UDP'
    timeout = [1]

    def __init__(self, report):
        self.report = report

    def query(self, qname, rdtype="A", rdclass="IN", dns_server=None):
        def callback(message):
            answers = []
            name = ''
            for answer in message.answers:
                if answer.type is 12:
                    name = str(answer.payload.name)
                answers.append(representAnswer(answer))
            return name

        def errback(failure):
            failure.trap(gaierror, TimeoutError)
            DNSTest.addToReport(self, query, resolver=dns_server,
                                query_type='PTR', failure=failure)
            return None

        try:
            rdtype = getattr(dns, rdtype)
        except AttributeError:
            raise InvalidRDType

        try:
            rdclass = getattr(dns, rdclass)
        except AttributeError:
            raise InvalidRDClass

        q = [dns.Query(qname, rdtype, rdclass)]
        resolver = Resolver(servers=[dns_server])
        if self.protocol == 'UDP':
            d = resolver.queryUDP(query, timeout=self.timeout)
        elif self.protocol == 'TCP':
            d = resolver.queryTCP(query, timeout=self.timeout)
        else:
            raise InvalidProtocol
        d.addCallback(callback)
        d.addErrback(errback)
        return d

    def a(self, name, dns_server=None):
        return self.query(name, 'A', 'IN', dns_server)

    def aaaa(self, name, dns_server=None):
        return self.query(name, 'AAAA', 'IN', dns_server)

    def reverse(self, name, dns_server=None):
        ptr = '.'.join(name.split('.')[::-1]) + '.in-addr.arpa'
        return self.ptr(ptr, dns_server)

    def ptr(self, name, dns_server=None):
        return self.query(name, 'PTR', 'IN', dns_server)

    def ns(self, name, dns_server=None):
        return self.query(name, 'NS', 'IN', dns_server)

    def cname(self, name, dns_server=None):
        return self.query(name, 'CNAME', 'IN', dns_server)

    def mx(self, name, dns_server=None):
        return self.query(name, 'MX', 'IN', dns_server)

    def txt(self, name, dns_server=None):
        return self.query(name, 'TXT', 'IN', dns_server)

    def soa(self, name, dns_server=None):
        return self.query(name, 'SOA', 'IN', dns_server)
