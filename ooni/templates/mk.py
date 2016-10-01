import json

import measurement_kit as mk

from ooni.utils import log
from ooni.nettest import NetTestCase


class TestNotFound(Exception):
    pass


def create_mk_test(test_name):
    try:
        return getattr(mk, test_name)()
    except AttributeError:
        raise TestNotFound


class MKTest(NetTestCase):
    name = "Base MeasurementKit Test"
    version = "0.1.0"

    requiresRoot = False

    def _got_entry(self, entry_str):
        # XXX this should probably happen in MK
        entry = json.loads(entry_str)
        for key, value in entry['test_keys'].items():
            self.report[key] = value

    def run(self, test_name, options={}, test_input=None):
        mk_test = create_mk_test(test_name)
        for key, value in options.items():
            mk_test.set_options(key, value)

        # mk_test.set_verbosity(mk.MK_LOG_DEBUG2)
        mk_test.set_options("no_collector", "yes")
        mk_test.set_options("no_file_report", "yes")
        # mk_test.on_log(lambda _, s: log.msg(s))
        mk_test.on_entry(self._got_entry)
        return mk_test.run_deferred()
