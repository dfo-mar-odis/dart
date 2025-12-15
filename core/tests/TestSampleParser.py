import os.path

from django.test import tag
from config.tests.DartTestCase import DartTestCase
from core.parsers.samples import sample_parser
from core.tests.CoreFactoryFloor import MissionFactory


@tag('sample_parser')
class TestSampleParser(DartTestCase):

    def setUp(self):
        file_name = "sample_oxy.xlsx"
        sample_file = os.path.join('.', 'core', 'tests', 'sample_data', file_name)
        mission = MissionFactory.create()
        with open(sample_file, 'rb') as f:
            self.parser = sample_parser.SampleParser(mission.pk, file_name, 'XLSX', f.read())


    def test_get_tabs(self):
        # For XLS files, parser.get_tabs() should return an uppercase list of tabs in the file
        tabs = self.parser.get_tabs()
        self.assertEqual(tabs, ['HUD2021-185'])

    def test_get_header(self):
        # The sample parser should be able to detect the line containing the header and should set the skip and
        # return the headers as they appear in the file.
        expected_headers = ["Sample", "Bottle#", "O2_Concentration(ml/l)", "O2_Uncertainty(ml/l)",
                            "Titrant_volume(ml)", "Titrant_uncertainty(ml)", "Analysis_date", "Data_file",
                            "Standards(ml)", "Blanks(ml)", "Bottle_volume(ml)", "Initial_transmittance(%%)",
                            "Standard_transmittance0(%%)", "Comments"]
        headers = self.parser.get_headers()
        skip = self.parser.get_skip()

        self.assertEqual(skip, 9)
        self.assertEqual(headers, expected_headers)

    def test_set_skip_get_header(self):
        # If the skip value is set by the user then the row set should be returned.
        expected_headers = ["HUD2021185"]
        self.parser.set_skip(0)
        headers = self.parser.get_headers()
        skip = self.parser.get_skip()

        self.assertEqual(skip, 0)
        self.assertEqual(headers, expected_headers)