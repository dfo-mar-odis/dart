import io
import os

from django.test import tag
from django.conf import settings

from core.tests import CoreFactoryFloor as core_factory
from core.parsers import FixStationParser

from dart.tests.DartTestCase import DartTestCase


@tag('parsers', 'parsers_fixstation')
class TestFixStationParser(DartTestCase):

    def setUp(self):
        self.filename = 'FixStationTemplate_HL_02.xlsx'
        path = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data', self.filename)

        sample_file_pointer = open(path, mode='rb')
        self.data = io.BytesIO(sample_file_pointer.read())

    def test_parse(self):
        trip = core_factory.TripFactory()

        FixStationParser.parse_fixstation(trip, self.filename, self.data)

        # three events should have been created
        self.assertEquals(trip.events.count(), 3)

        # each event should have 3 actions
        for event in trip.events.all():
            self.assertEquals(event.actions.count(), 3)

        # 18 bottles should have been created for the CTD event
        event = trip.events.get(event_id=137)
        self.assertEquals(event.bottles.count(), 18)

