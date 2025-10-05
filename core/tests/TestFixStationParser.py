import datetime
import io
import os

import pytz
from django.test import tag
from django.conf import settings
from django.utils.translation import gettext as _

from core.parsers.sensor.btl_ros import FixStationParser, validate_file

from core.tests import CoreFactoryFloor as core_factory
from core import models as core_models

from config.tests.DartTestCase import DartTestCase


@tag('parsers', 'parsers_fixstation')
class TestFixStationParser(DartTestCase):

    def setUp(self):
        self.btn_filename = '25667001.btl'
        self.ros_filename = '25667001.ros'
        btl_path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data', 'fixed_stations', self.btn_filename)
        ros_path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data', 'fixed_stations', self.ros_filename)

        btl_sample_file = open(btl_path, mode='rb')
        ros_sample_file = open(ros_path, mode='rb')
        self.btl_data = io.StringIO(btl_sample_file.read().decode("cp1252"))
        self.ros_data = io.StringIO(ros_sample_file.read().decode("cp1252"))

        self.station = core_factory.StationFactory(name='HL_0')
        self.event = core_factory.CTDEventFactoryBlank(event_id=1, station=self.station, sample_id=None, end_sample_id=None)

    @tag('parsers_fixstation_test_parse')
    def test_parse(self):
        parser = FixStationParser(self.event, self.btn_filename, self.btl_data, self.ros_data)
        parser.parse()

    def test_errors(self):
        # if errors exist for a file they should be removed the next time a file of the same name is parsed
        core_models.FileError(mission=self.event.mission, file_name=self.btn_filename, line=0, message=_("test"),
                              type=core_models.ErrorType.bottle).save()

        self.assertEqual(1, core_models.FileError.objects.using('default').filter(file_name=self.btn_filename).count())

        parser = FixStationParser(self.event, self.btn_filename, self.btl_data, self.ros_data)
        parser.parse()

        self.assertEqual(0, core_models.FileError.objects.using('default').filter(file_name=self.btn_filename).count())

    def test_bottle_creation(self):
        # Create bottles for the provided event if present in the BTL file, but don't already exist
        parser = FixStationParser(self.event, self.btn_filename, self.btl_data, self.ros_data)
        parser.parse()

        self.assertEqual(4, self.event.bottles.count())

    @tag('parsers_fixstation_test_bottle_update')
    def test_bottle_update(self):
        # If a bottle already exists then it's closed time and pressure should be updated based on the bottle file
        # **For the current event**
        core_factory.BottleFactory(event=self.event, bottle_id=500853, closed=datetime.datetime.now(pytz.UTC),
                                   pressure=140)

        parser = FixStationParser(self.event, self.btn_filename, self.btl_data, self.ros_data)
        parser.parse()

        dt = datetime.datetime.strptime("2025-01-08 12:57:58 +0000", '%Y-%m-%d %H:%M:%S %z')

        bottle = self.event.bottles.get(bottle_id=500853)
        self.assertEqual(dt, bottle.closed)
        self.assertEqual(1.914, float(bottle.pressure))

    def test_bottom_action(self):
        # a bottom action should be created for when the bottom bottle is closed
        parser = FixStationParser(self.event, self.btn_filename, self.btl_data, self.ros_data)
        parser.parse()

        action = self.event.actions.filter(type=core_models.ActionType.bottom)
        self.assertTrue(action.exists())

    def test_recovery_action(self):
        # a recovery action should be created for when the surface bottle is closed
        parser = FixStationParser(self.event, self.btn_filename, self.btl_data, self.ros_data)
        parser.parse()

        action = self.event.actions.filter(type=core_models.ActionType.recovered)
        self.assertTrue(action.exists())

    def test_event_update(self):
        # event sounding, sample_id and end_sample_id should be created based on the btl file header data
        parser = FixStationParser(self.event, self.btn_filename, self.btl_data, self.ros_data)
        parser.parse()

        self.assertIsNotNone(self.event.sample_id)
        self.assertIsNotNone(self.event.end_sample_id)

    @tag('parser_fixstation_validation', 'parsers_fixstation_test_validate_file_missing_event_id')
    def test_validate_file_missing_event_id(self):
        btl_file_name = "25667001_missing_event_id.btl"
        btl_path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data', 'fixed_stations', btl_file_name)
        btl_sample_file = open(btl_path, mode='rb')
        btl_data = io.StringIO(btl_sample_file.read().decode("cp1252"))

        with self.assertRaises(ValueError) as context:
            validate_file(btl_data)

        self.assertEqual(str(context.exception), "Event ID is missing")

    @tag('parser_fixstation_validation', 'parsers_fixstation_test_validate_file_missing_station_name')
    def test_validate_file_missing_station_name(self):
        btl_file_name = "25667001_missing_station_name.btl"
        btl_path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data', 'fixed_stations', btl_file_name)
        btl_sample_file = open(btl_path, mode='rb')
        btl_data = io.StringIO(btl_sample_file.read().decode("cp1252"))

        with self.assertRaises(ValueError) as context:
            validate_file(btl_data)

        self.assertEqual(str(context.exception), "Station Name is missing")

    @tag('parser_fixstation_validation', 'parsers_fixstation_test_validate_file_missing_station_name')
    def test_validate_file_missing_station_name(self):
        btl_file_name = "25667001_missing_station_name.btl"
        btl_path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data', 'fixed_stations', btl_file_name)
        btl_sample_file = open(btl_path, mode='rb')
        btl_data = io.StringIO(btl_sample_file.read().decode("cp1252"))

        with self.assertRaises(ValueError) as context:
            validate_file(btl_data)

        self.assertEqual(str(context.exception), "Station Name is missing")

    @tag('parser_fixstation_validation', 'parsers_fixstation_test_validate_file_missing_sounding')
    def test_validate_file_missing_sounding(self):
        btl_file_name = "25667001_missing_sounding.btl"
        btl_path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data', 'fixed_stations', btl_file_name)
        btl_sample_file = open(btl_path, mode='rb')
        btl_data = io.StringIO(btl_sample_file.read().decode("cp1252"))

        with self.assertRaises(ValueError) as context:
            validate_file(btl_data)

        self.assertEqual(str(context.exception), "Sounding is missing from the header. Cannot create event")

    @tag('parser_fixstation_validation', 'parsers_fixstation_test_validate_file_missing_latitude')
    def test_validate_file_missing_latitude(self):
        btl_file_name = "25667001_missing_latitude.btl"
        btl_path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data', 'fixed_stations', btl_file_name)
        btl_sample_file = open(btl_path, mode='rb')
        btl_data = io.StringIO(btl_sample_file.read().decode("cp1252"))

        with self.assertRaises(ValueError) as context:
            validate_file(btl_data)

        self.assertEqual(str(context.exception), "Latitude is missing from the header. Cannot create event")

    @tag('parser_fixstation_validation', 'parsers_fixstation_test_validate_file_missing_longitude')
    def test_validate_file_missing_longitude(self):
        btl_file_name = "25667001_missing_longitude.btl"
        btl_path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data', 'fixed_stations', btl_file_name)
        btl_sample_file = open(btl_path, mode='rb')
        btl_data = io.StringIO(btl_sample_file.read().decode("cp1252"))

        with self.assertRaises(ValueError) as context:
            validate_file(btl_data)

        self.assertEqual(str(context.exception), "Longitude is missing from the header. Cannot create event")
