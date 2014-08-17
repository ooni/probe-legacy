
"""
Here goes code related to network interface controllers.
"""

from ooni.utils import log
from ooni import errors
from ooni.arch import PLATFORMS


def getSystemResolver():
    """
    XXX implement a function that returns the resolver that is currently
    default on the system.
    """


def getClientPlatform(platform_name=None):
    for name, test in PLATFORMS.items():
        if not platform_name or platform_name.upper() == name:
            if test:
                return name, test


def getPosixIfaces():
    from twisted.internet.test import _posixifaces

    log.msg("Attempting to discover network interfaces...")
    ifaces = _posixifaces._interfaces()
    # XXX this function is not defined anywhere.
    #     check if this code is even used anywhere.
    ifup = tryInterfaces(ifaces)
    return ifup


def getWindowsIfaces():
    from twisted.internet.test import _win32ifaces

    log.msg("Attempting to discover network interfaces...")
    ifaces = _win32ifaces._interfaces()
    # XXX same as above.
    ifup = tryInterfaces(ifaces)
    return ifup


def getIfaces(platform_name=None):
    client, test = getClientPlatform(platform_name)
    if client:
        if client == ('LINUX' or 'DARWIN') or client[-3:] == 'BSD':
            return getPosixIfaces()
        elif client == 'WINDOWS':
            return getWindowsIfaces()
        # XXX fixme figure out how to get iface for Solaris
        else:
            return None
    else:
        raise errors.UnsupportedPlatform


def checkInterfaces(ifaces=None, timeout=1):
    """
    @param ifaces:
        A dictionary in the form of ifaces['if_name'] = 'if_addr'.
    """
    try:
        from scapy.all import IP, ICMP
        from scapy.all import sr1  # we want this check to be blocking
    except:
        log.msg(("Scapy required: www.secdev.org/projects/scapy"))

    ifup = {}
    if not ifaces:
        log.debug("checkInterfaces(): no interfaces specified!")
        return None

    for iface in ifaces:
        for ifname, ifaddr in iface:
            log.debug("checkInterfaces(): testing iface {} by pinging"
                      + " local address {}".format(ifname, ifaddr))
            try:
                pkt = IP(dst=ifaddr) / ICMP()
                ans, unans = sr1(pkt, iface=ifname, timeout=5, retry=3)
            except Exception as e:
                raise errors.PermissionsError if e.find(
                    "Errno 1") else log.err(e)
            else:
                if ans.summary():
                    log.debug("checkInterfaces(): got answer on interface %s"
                              + ":\n%s".format(ifname, ans.summary()))
                    ifup.update(ifname, ifaddr)
                else:
                    log.debug("Interface test packet was unanswered:\n%s"
                              % unans.summary())
    if len(ifup) > 0:
        log.msg("Discovered working network interfaces: %s" % ifup)
        return ifup
    else:
        raise errors.IfaceError


def getNonLoopbackIfaces(platform_name=None):
    try:
        ifaces = getIfaces(platform_name)
    except errors.UnsupportedPlatform as up:
        log.err(up)

    if not ifaces:
        log.msg("Unable to discover network interfaces...")
        return None
    else:
        found = [{i[0]: i[2]} for i in ifaces if i[0] != 'lo']
        log.debug("getNonLoopbackIfaces: Found non-loopback interfaces: %s"
                  % found)
        try:
            interfaces = checkInterfaces(found)
        except errors.IfaceError as ie:
            log.err(ie)
            return None
        else:
            return interfaces
