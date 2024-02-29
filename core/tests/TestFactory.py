from django.test import tag

from core import models

from dart.tests.DartTestCase import DartTestCase
from . import CoreFactoryFloor as core_factory


@tag("model", "model_mission")
class TestMission(DartTestCase):

    @tag("create", "create_mission")
    def test_create_mission(self):
        mission = core_factory.MissionFactory()

        self.assertIsNotNone(mission.name)


@tag("model", "model_ctd_event")
class TestCTDEvent(DartTestCase):

    @tag("create", "create_ctd_event")
    def test_create_mission(self):
        event = core_factory.CTDEventFactory()

        self.assertIsNotNone(event.mission)
        self.assertIsNotNone(event.station)
        self.assertEquals(event.instrument.type, models.InstrumentType.ctd)
        self.assertIsNotNone(event.sample_id)
        self.assertIsNotNone(event.end_sample_id)

        self.assertGreater(event.end_sample_id, event.sample_id)
