import os
from io import StringIO

from django.test import TestCase, tag

from core.tests import CoreFactoryFloor as core_factory
from core.parsers.sensor.qat import QATParser
from core.models import Event


sample_file_path = ['core', 'tests', 'sample_data']
sample_file_name = '25002102_Fake.QAT'
sample_file = os.path.join(*sample_file_path, sample_file_name)


@tag('qat_parser')
class TestQATParser(TestCase):
    fixtures = ['default_biochem_fixtures']

    def setUp(self):
        self.mission = core_factory.MissionFactory.create(name='QATMission')
        self.file_data = None
        with open(sample_file, 'r') as file:
            self.file_data = StringIO(file.read())

    def test_init(self):
        QATParser(self.mission, sample_file_name, self.file_data)

    def test_parse_with_event_exception(self):
        qatparser = QATParser(self.mission, sample_file_name, self.file_data)
        with self.assertRaises(Event.DoesNotExist):
            qatparser.parse()

    def test_parse_create_bottles(self):

        core_factory.CTDEventFactory.create(mission=self.mission, event_id=97)

        qatparser = QATParser(self.mission, sample_file_name, self.file_data)
        qatparser.parse()

        bottles = self.mission.events.get(event_id=97).bottles.filter(bottle_id__gte=510137, bottle_id__lte=510141)
        self.assertEqual(len(bottles), 5),

        expected_pressure = [172.9, 100.0, 50.0, 25.0, 5.0]
        for pressure in expected_pressure:
            self.assertIsNotNone(bottles.get(pressure=pressure))

        expected_latitude = 43.3262
        self.assertEqual(len(bottles.filter(latitude=expected_latitude)), 5)

        expected_longitude = -63.6211
        self.assertEqual(len(bottles.filter(longitude=expected_longitude)), 5)

    def test_parse_update_bottles(self):
        event = core_factory.CTDEventFactory.create(mission=self.mission, event_id=97)
        core_factory.BottleFactory(event=event, bottle_id=510137)
        core_factory.BottleFactory(event=event, bottle_id=510138)
        core_factory.BottleFactory(event=event, bottle_id=510139)
        core_factory.BottleFactory(event=event, bottle_id=510140)
        core_factory.BottleFactory(event=event, bottle_id=510141)

        qatparser = QATParser(self.mission, sample_file_name, self.file_data)
        qatparser.parse()

        bottles = self.mission.events.get(event_id=97).bottles.filter(bottle_id__gte=510137, bottle_id__lte=510141)
        self.assertEqual(len(bottles), 5),

        expected_pressure = [172.9, 100.0, 50.0, 25.0, 5.0]
        for pressure in expected_pressure:
            self.assertIsNotNone(bottles.get(pressure=pressure))

        expected_latitude = 43.3262
        self.assertEqual(len(bottles.filter(latitude=expected_latitude)), 5)

        expected_longitude = -63.6211
        self.assertEqual(len(bottles.filter(longitude=expected_longitude)), 5)

