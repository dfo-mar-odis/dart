import os
import io

from django.conf import settings
from django.test import tag
from django.test import TestCase

from core.parsers import FilterLogParser
from core.tests import CoreFactoryFloor as core_factory
from core import models as core_models


@tag('parsers', 'FilterLogParser')
class TestFilterLogParser(TestCase):
    fixtures = ['biochem_fixtures', 'default_settings_fixtures']

    def setUp(self):
        self.station_hl_2 = core_factory.StationFactory(name="HL_02")
        self.event = core_factory.CTDEventFactory(event_id=1, station=self.station_hl_2)
        self.test_data_path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        self.sample_file = "FilterLog.xlsx"
        fp = open(os.path.join(self.test_data_path, self.sample_file), 'rb')
        FilterLogParser.parse(self.event, self.sample_file, io.BytesIO(fp.read()))

    @tag('FilterLogParser_test_bottle_creation')
    def test_bottle_creation(self):
        # the sample file contains 19 bottles for HL_02
        self.assertEquals(19, core_models.Bottle.objects.using('default').count())

    @tag('FilterLogParser_test_oxygen_exists')
    def test_oxygen_exists(self):
        # the sample file contains 2 oxygen bottles for HL_02 so there should be an oxygen mission sample type
        self.assertTrue(core_models.MissionSampleType.objects.using('default').filter(name='oxy').exists())


@tag('parsers', 'FilterLogParser')
class TestFilterLogParser(TestCase):
    fixtures = ['biochem_fixtures', 'default_settings_fixtures']

    def setUp(self):
        self.station_sv = core_factory.StationFactory(name="Shediac Valley")
        self.event = core_factory.CTDEventFactory(event_id=1, station=self.station_sv)
        self.test_data_path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        self.sample_file = "FilterLog.xlsx"
        fp = open(os.path.join(self.test_data_path, self.sample_file), 'rb')
        FilterLogParser.parse(self.event, self.sample_file, io.BytesIO(fp.read()))

    @tag('FilterLogParser_test_missing_bottle_ids')
    def test_missing_bottle_ids(self):
        # if bottle IDs are missing there should be FileErrors reported of the type
        # models.ErrorType.event

        file_errors = core_models.FileError.objects.using('default')
        self.assertTrue(file_errors.filter(type=core_models.ErrorType.event).exists())
