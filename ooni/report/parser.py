from pprint import pprint
import yaml


def http_requests_tampering(entry):
    if entry["body_length_match"] is False:
        return True
    elif entry["headers_match"] is False:
        return True
    return False

tampering_detectors = {
    "http_requests": http_requests_tampering
}


def tampering(report_header, report_entry):
    func = tampering_detectors.get(report_header['test_name'])
    return func(report_entry)


def http_requests_pretty_print(entry, verbosity):
    output = {}
    if verbosity == 0:
        output['input'] = entry['input']
    else:
        output = entry
    pprint(output)

pretty_printers = {
    "http_requests": http_requests_pretty_print
}


def pretty_print_header(header, verbosity=0):
    pprint(header)


def pretty_print(report_header, report_entry, verbosity=0):
    func = pretty_printers.get(report_header['test_name'])
    func(report_entry, verbosity)


class ReportLoader(object):
    _header_keys = (
        'probe_asn',
        'probe_cc',
        'probe_ip',
        'start_time',
        'test_name',
        'test_version',
        'options',
        'input_hashes',
        'software_name',
        'software_version'
    )

    def __init__(self, report_filename):
        self._fp = open(report_filename)
        self._yfp = yaml.safe_load_all(self._fp)

        self.header = self._yfp.next()

    def __iter__(self):
        return self

    def next(self):
        try:
            return self._yfp.next()
        except StopIteration:
            self.close()
            raise StopIteration

    def close(self):
        self._fp.close()
