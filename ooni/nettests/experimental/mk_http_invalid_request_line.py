from ooni.templates import mk
from ooni.utils import log
# from twisted.internet import defer, protocol, reactor
from twisted.python import usage


class UsageOptions(usage.Options):
    optParameters = [
        [
            'backend', 'b', None, 'The OONI backend that runs a TCP echo server.'
        ],
        [
            'backendport', 'p', 80, 'Specify the port that the TCP echo server is running '
         '(should only be set for debugging).']
    ]

class MKHTTPInvalidRequestLine(mk.MKTest):
    name = "HTTP Invalid Request Line"
    version = "0.1.0"

    usageOptions = UsageOptions
    requiresRoot = False
    requiresTor = False

    requiredOptions = ['backend']
    requiredTestHelpers = {'backend': 'tcp-echo'}

    def test_run(self):
        log.msg("Running http invalid request line")
        options = {
            'backend': 'http://' + self.localOptions['backend'] + '/'
        }
        return self.run("HttpInvalidRequestLine", options)
