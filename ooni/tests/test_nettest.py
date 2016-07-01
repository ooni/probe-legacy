import os
import yaml
import random
from tempfile import mkstemp

from .mocks import MockReporter, MockOReporter
from mock import MagicMock

from twisted.internet import defer, reactor
from twisted.python.usage import UsageError

from ooni.settings import config
from ooni.errors import MissingRequiredOption, OONIUsageError, IncoherentOptions
from ooni.nettest import NetTest, NetTestLoader, NetTestCase
from ooni.managers import MeasurementManager, ReportEntryManager
from ooni.reporter import Report

from ooni.director import Director

from ooni.tests.bases import ConfigTestCase

net_test_string = """
from twisted.python import usage
from ooni.nettest import NetTestCase

class UsageOptions(usage.Options):
    optParameters = [['spam', 's', None, 'ham']]

class DummyTestCase(NetTestCase):

    usageOptions = UsageOptions

    def test_a(self):
        self.report['bar'] = 'bar'

    def test_b(self):
        self.report['foo'] = 'foo'
"""

double_net_test_string = """
from twisted.python import usage
from ooni.nettest import NetTestCase

class UsageOptions(usage.Options):
    optParameters = [['spam', 's', None, 'ham']]

class DummyTestCaseA(NetTestCase):

    usageOptions = UsageOptions

    def test_a(self):
        self.report['bar'] = 'bar'


class DummyTestCaseB(NetTestCase):

    usageOptions = UsageOptions

    def test_b(self):
        self.report['foo'] = 'foo'
"""

double_different_options_net_test_string = """
from twisted.python import usage
from ooni.nettest import NetTestCase

class UsageOptionsA(usage.Options):
    optParameters = [['spam', 's', None, 'ham']]

class UsageOptionsB(usage.Options):
    optParameters = [['spam', 's', None, 'ham']]

class DummyTestCaseA(NetTestCase):

    usageOptions = UsageOptionsA

    def test_a(self):
        self.report['bar'] = 'bar'


class DummyTestCaseB(NetTestCase):

    usageOptions = UsageOptionsB

    def test_b(self):
        self.report['foo'] = 'foo'
"""

net_test_root_required = net_test_string + """
    requiresRoot = True
"""

net_test_string_with_file = """
from twisted.python import usage
from ooni.nettest import NetTestCase

class UsageOptions(usage.Options):
    optParameters = [['spam', 's', None, 'ham']]

class DummyTestCase(NetTestCase):
    inputFile = ['file', 'f', None, 'The input File']

    usageOptions = UsageOptions

    def test_a(self):
        self.report['bar'] = 'bar'

    def test_b(self):
        self.report['foo'] = 'foo'
"""

net_test_string_with_required_option = """
from twisted.python import usage
from ooni.nettest import NetTestCase

class UsageOptions(usage.Options):
    optParameters = [['spam', 's', None, 'ham'],
                     ['foo', 'o', None, 'moo'],
                     ['bar', 'o', None, 'baz'],
    ]

class DummyTestCase(NetTestCase):
    inputFile = ['file', 'f', None, 'The input File']

    requiredOptions = ['foo', 'bar']
    usageOptions = UsageOptions

    def test_a(self):
        self.report['bar'] = 'bar'

    def test_b(self):
        self.report['foo'] = 'foo'
"""

http_net_test = """
from twisted.internet import defer
from twisted.python import usage, failure

from ooni.utils import log
from ooni.utils.net import userAgents
from ooni.templates import httpt
from ooni.errors import failureToString, handleAllFailures

class UsageOptions(usage.Options):
    optParameters = [
                     ['url', 'u', None, 'Specify a single URL to test.'],
                    ]

class HTTPBasedTest(httpt.HTTPTest):
    usageOptions = UsageOptions
    def test_get(self):
        return self.doRequest(self.localOptions['url'], method="GET",
                              use_tor=False)
"""

generator_net_test = """
from twisted.python import usage
from ooni.nettest import NetTestCase

class UsageOptions(usage.Options):
    optParameters = [['spam', 's', None, 'ham']]

def input_generator():
    # Generates a list of numbers
    # The first value sent back is appended to the list.
    received = False
    numbers = [i for i in range(10)]
    while numbers:
        i = numbers.pop()
        result = yield i
        # Place sent value back in numbers
        if result is not None and received is False:
            numbers.append(result)
            received = True
            yield i

class TestSendGen(NetTestCase):
    usageOptions = UsageOptions
    inputs = input_generator()

    def test_input_sent_to_generator(self):
        # Sends a single value back to the generator
        if self.input == 5:
            self.inputs.send(self.input)
"""

generator_id_net_test = """
from twisted.python import usage
from ooni.nettest import NetTestCase

class UsageOptions(usage.Options):
    optParameters = [['spam', 's', None, 'ham']]

class DummyTestCaseA(NetTestCase):

    usageOptions = UsageOptions

    def test_a(self):
        self.report.setdefault("results", []).append(id(self.inputs))

    def test_b(self):
        self.report.setdefault("results", []).append(id(self.inputs))

    def test_c(self):
        self.report.setdefault("results", []).append(id(self.inputs))

class DummyTestCaseB(NetTestCase):

    usageOptions = UsageOptions

    def test_a(self):
        self.report.setdefault("results", []).append(id(self.inputs))
"""

dummyInputs = range(1)
dummyArgs = ('--spam', 'notham')
dummyOptions = {'spam': 'notham'}
dummyInvalidArgs = ('--cram', 'jam')
dummyInvalidOptions = {'cram': 'jam'}
dummyArgsWithRequiredOptions = ('--foo', 'moo', '--bar', 'baz')
dummyRequiredOptions = {'foo': 'moo', 'bar': 'baz'}
dummyArgsWithFile = ('--spam', 'notham', '--file', 'dummyInputFile.txt')
dummyInputFile = 'dummyInputFile.txt'
dummyTestDetails = {
    'probe_asn': 'AS0',
    'probe_cc': 'ZZ',
    'probe_ip': '127.0.0.1',
    'probe_city': None,
    'software_name': 'ooniprobe',
    'software_version': '0.0.0',
    'options': {},
    'annotations': {},
    'data_format_version': '0.2.0',
    'test_name': 'dummy_test',
    'test_version': '0.0.0',
    'test_helpers': {},
    'test_start_time': '2016-07-01 08:29:17',
    'input_hashes': [],
    'report_id': 'XXXX'
}



class TestNetTest(ConfigTestCase):
    timeout = 1

    def setUp(self):
        self.filename = ""
        with open(dummyInputFile, 'w') as f:
            for i in range(10):
                f.write("%s\n" % i)
        super(TestNetTest, self).setUp()

    def tearDown(self):
        os.remove(dummyInputFile)
        if self.filename != "":
            os.remove(self.filename)
        super(TestNetTest, self).tearDown()

    def assertCallable(self, thing):
        self.assertIn('__call__', dir(thing))

    def verifyMethods(self, testCases):
        uniq_test_methods = set()
        for test_class, test_methods in testCases:
            instance = test_class()
            for test_method in test_methods:
                c = getattr(instance, test_method)
                self.assertCallable(c)
                uniq_test_methods.add(test_method)
        self.assertEqual(set(['test_a', 'test_b']), uniq_test_methods)

    def test_load_net_test_from_file(self):
        """
        Given a file verify that the net test cases are properly
        generated.
        """
        __, net_test_file = mkstemp()
        with open(net_test_file, 'w') as f:
            f.write(net_test_string)
        f.close()

        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestFile(net_test_file)

        self.verifyMethods(ntl.getTestCases())
        os.unlink(net_test_file)

    def test_load_net_test_from_str(self):
        """
        Given a file like object verify that the net test cases are properly
        generated.
        """
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(net_test_string)

        self.verifyMethods(ntl.getTestCases())

    def test_load_net_test_multiple(self):
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(double_net_test_string)
        test_cases = ntl.getTestCases()
        self.verifyMethods(test_cases)
        ntl.checkOptions()

    def test_load_net_test_multiple_different_options(self):
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(double_different_options_net_test_string)

        test_cases = ntl.getTestCases()
        self.verifyMethods(test_cases)
        self.assertRaises(IncoherentOptions, ntl.checkOptions)

    def test_load_with_option(self):
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(net_test_string)

        self.assertIsInstance(ntl, NetTestLoader)
        for test_klass, test_meth in ntl.getTestCases():
            for option in dummyOptions.keys():
                self.assertIn(option, test_klass.usageOptions())

    def test_load_with_invalid_option(self):
        ntl = NetTestLoader(dummyInvalidArgs)
        ntl.loadNetTestString(net_test_string)
        self.assertRaises(UsageError, ntl.checkOptions)
        self.assertRaises(OONIUsageError, ntl.checkOptions)

    def test_load_with_required_option(self):
        ntl = NetTestLoader(dummyArgsWithRequiredOptions)
        ntl.loadNetTestString(net_test_string_with_required_option)

        self.assertIsInstance(ntl, NetTestLoader)

    def test_load_with_missing_required_option(self):
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(net_test_string_with_required_option)
        self.assertRaises(MissingRequiredOption, ntl.checkOptions)

    @defer.inlineCallbacks
    def test_net_test_inputs(self):
        ntl = NetTestLoader(dummyArgsWithFile)
        ntl.loadNetTestString(net_test_string_with_file)
        ntl.checkOptions()
        nt = NetTest(ntl.getTestCases(), ntl.getTestDetails(), None)
        yield nt.initialize()

        for test_class, test_methods in nt.testCases:
            self.assertEqual(len(list(test_class.inputs)), 10)

    def test_setup_local_options_in_test_cases(self):
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(net_test_string)

        ntl.checkOptions()
        self.assertEqual(dict(ntl.localOptions), dummyOptions)

    @defer.inlineCallbacks
    def test_generate_measurements_size(self):
        ntl = NetTestLoader(dummyArgsWithFile)
        ntl.loadNetTestString(net_test_string_with_file)
        ntl.checkOptions()

        net_test = NetTest(ntl.getTestCases(), ntl.getTestDetails(), None)

        yield net_test.initialize()
        measurements = list(net_test.generateMeasurements())
        self.assertEqual(len(measurements), 20)

    def test_net_test_completed_callback(self):
        ntl = NetTestLoader(dummyArgsWithFile)
        ntl.loadNetTestString(net_test_string_with_file)

        ntl.checkOptions()
        director = Director()

        self.filename = 'dummy_report.yamloo'
        d = director.startNetTest(ntl, self.filename)

        @d.addCallback
        def complete(result):
            self.assertEqual(result, None)
            self.assertEqual(director.successfulMeasurements, 20)

        return d

    def test_require_root_succeed(self):
        # XXX: will require root to run
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(net_test_root_required)

        for test_class, methods in ntl.getTestCases():
            self.assertTrue(test_class.requiresRoot)

    def test_singular_input_processor(self):
        """
        Verify that all measurements use the same object as their input processor.
        """
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(generator_id_net_test)
        ntl.checkOptions()

        director = Director()
        self.filename = 'dummy_report.yamloo'
        d = director.startNetTest(ntl, self.filename)

        @d.addCallback
        def complete(result):
            with open(self.filename) as report_file:
                all_report_entries = yaml.safe_load_all(report_file)
                header = all_report_entries.next()
                results_case_a = all_report_entries.next()
                aa_test, ab_test, ac_test = results_case_a.get('results', [])
                results_case_b = all_report_entries.next()
                ba_test = results_case_b.get('results', [])[0]
            # Within a NetTestCase an inputs object will be consistent
            self.assertEqual(aa_test, ab_test, ac_test)
            # An inputs object will be different between different NetTestCases
            self.assertNotEqual(aa_test, ba_test)

        return d

    def test_send_to_inputs_generator(self):
        """
        Verify that a net test can send information back into an inputs generator.
        """
        ntl = NetTestLoader(dummyArgs)
        ntl.loadNetTestString(generator_net_test)
        ntl.checkOptions()

        director = Director()
        self.filename = 'dummy_report.yamloo'
        d = director.startNetTest(ntl, self.filename)

        @d.addCallback
        def complete(result):
            with open(self.filename) as report_file:
                all_report_entries = yaml.safe_load_all(report_file)
                header = all_report_entries.next()
                results = [x['input'] for x in all_report_entries]
            self.assertEqual(results, [9, 8, 7, 6, 5, 5, 3, 2, 1, 0])

        return d

class TestNettestTimeout(ConfigTestCase):

    @defer.inlineCallbacks
    def setUp(self):
        super(TestNettestTimeout, self).setUp()
        from twisted.internet.protocol import Protocol, Factory
        from twisted.internet.endpoints import TCP4ServerEndpoint

        class DummyProtocol(Protocol):

            def dataReceived(self, data):
                pass

        class DummyFactory(Factory):

            def __init__(self):
                self.protocols = []

            def buildProtocol(self, addr):
                proto = DummyProtocol()
                self.protocols.append(proto)
                return proto

            def stopFactory(self):
                for proto in self.protocols:
                    proto.transport.loseConnection()

        self.factory = DummyFactory()
        endpoint = TCP4ServerEndpoint(reactor, 8007)
        self.port = yield endpoint.listen(self.factory)

        config.advanced.measurement_timeout = 2

    def tearDown(self):
        super(TestNettestTimeout, self).tearDown()
        self.factory.stopFactory()
        self.port.stopListening()
        os.remove(self.filename)

    def test_nettest_timeout(self):
        ntl = NetTestLoader(('-u', 'http://localhost:8007/'))
        ntl.loadNetTestString(http_net_test)

        ntl.checkOptions()
        director = Director()

        self.filename = 'dummy_report.yamloo'
        d = director.startNetTest(ntl, self.filename)

        @d.addCallback
        def complete(result):
            assert director.failedMeasurements == 1

        return d


class TestNetTestScheduling(ConfigTestCase):
    def test_generate_measurements(self):
        d = defer.Deferred()
        input_count = 200
        self.config.advanced.measurement_timeout = 0.3
        self.config.advanced.debug = True
        self.config.logging = False

        class MockTestClass(NetTestCase):
            inputs = range(input_count)
            def test_foo(self):
                d = defer.Deferred()
                delay = random.random()
                self.report["failure"] = self.report.get("failure", 0) + 1
                print("Running %s %f" % (self.input, delay))

                def callback():
                    return d.callback(42)
                    if random.randint(0, 1) == 0:
                        return d.callback(42)
                    return d.errback(Exception("Failure in measurement"))

                #callback()
                if random.randint(0, 3) == 0:
                    reactor.callLater(delay, callback)
                else:
                    callback()
                return d

        mock_director = MagicMock()
        mock_test_cases = [
            (MockTestClass, ('test_foo',))
        ]

        measurementManager = MeasurementManager()
        measurementManager.director = mock_director
        measurementManager.concurrency = 30
        measurementManager.retries = 2

        measurementManager.start()

        reportEntryManager = ReportEntryManager()
        reportEntryManager.directory = mock_director
        reportEntryManager.concurrency = 4
        reportEntryManager.retries = 2

        reportEntryManager.start()

        measurementManager.child = reportEntryManager
        reportEntryManager.parent = measurementManager

        mock_report = Report(
            test_details=dummyTestDetails,
            report_filename="dummy",
            reportEntryManager=reportEntryManager
        )
        mock_report.report_log = MagicMock()
        mock_report.yaml_reporter = MagicMock()
        mock_report.oonib_reporter = MagicMock()
        tested_inputs = []

        def writeReportEntryFlaky(entry, *args, **kw):
            tested_inputs.append(entry['input'])
            print("Writing %s %s %s" % (entry, args, kw))
            if random.randint(0, 10) == 0:
                return defer.fail(Exception("Writing report failed"))
            return defer.succeed(42)
        mock_report.oonib_reporter.writeReportEntry = writeReportEntryFlaky
        mock_report.yaml_reporter.writeReportEntry = writeReportEntryFlaky

        net_test = NetTest(test_cases=mock_test_cases,
                           test_details=dummyTestDetails,
                           report=mock_report)
        net_test.director = mock_director

        measurementManager.schedule(net_test.generateMeasurements())

        @net_test.done.addBoth
        def finish(result):
            tested_inputs.sort()
            self.assertEqual(set(tested_inputs), set(range(input_count)))
            reactor.callLater(10, d.callback, None)

        return d
