from random import randint
import socket


def randomFreePort(addr="127.0.0.1"):
    """
    Args:

        addr (str): the IP address to attempt to bind to.

    Returns an int representing the free port number at the moment of calling

    Note: there is no guarantee that some other application will attempt to
    bind to this port once this function has been called.
    """
    free = False
    while not free:
        port = randint(1024, 65535)
        s = socket.socket()
        try:
            s.bind((addr, port))
            free = True
        except:
            pass
        s.close()
    return port


def isIPAddress(addr):
    try:
        parts = addr.split('.')
        if len(parts) == 4 and all(int(x) < 256 for x in parts):
            return True
    except: pass
    # XXX improve ipv6 detection
    if ':' in addr:
        return True
    return False
