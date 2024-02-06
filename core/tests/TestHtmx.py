import os

from django.test import tag, Client
from django.urls import reverse_lazy

from core import models

from dart.tests.DartTestCase import DartTestCase
from . import CoreFactoryFloor as core_factory

import logging

logger = logging.getLogger("dart.test")


@tag('utils', 'utils_elog_upload')
class TestElogUpload(DartTestCase):

    def setUp(self) -> None:
        self.file_location = r'core/tests/sample_data/'
        self.mission = core_factory.MissionFactory(name="TestMission")
        self.trip = core_factory.TripFactory(mission=self.mission)
        self.url = reverse_lazy('core:form_trip_import_events_elog', args=(self.trip.pk,))
        self.client = Client()

    def test_elog_uplaod_missing_mid(self):
        logger.info("Running test_elog_uplaod_missing_mid")

        file_name = 'missing_mid_bad.log'

        with open(self.file_location+file_name, 'rb') as fp:
            self.client.post(self.url, {'event': fp})

        errors = self.mission.file_errors.all()
        self.assertTrue(errors.exists())
        self.assertEquals(errors[0].type, models.ErrorType.missing_id)

        for error in errors:
            logger.info(error)

    def test_elog_uplaod_missing_fields(self):
        # Errors should be reported if a message object is missing the instrument and/or station field
        logger.info("Running test_elog_uplaod_missing_mid")

        file_name = 'bad.log'

        with open(os.path.join(self.file_location, file_name), 'rb') as fp:
            self.client.post(self.url, {'event': fp})

        errors = self.mission.file_errors.all()
        self.assertTrue(errors.exists())

        for error in errors:
            logger.info(error)


@tag('utils', 'utils_hx_mission_delete')
class TestMissionDelete(DartTestCase):

    def setUp(self) -> None:
        self.mission_1 = core_factory.MissionFactory(name="test1")
        self.mission_2 = core_factory.MissionFactory(name="test2")
        self.client = Client()

    def test_hx_mission_delete(self):
        logger.info("Running test_hx_mission_delete")

        # Mission 1 and 2 should exist
        self.assertTrue(models.Mission.objects.filter(pk=self.mission_1.pk).exists())
        self.assertTrue(models.Mission.objects.filter(pk=self.mission_2.pk).exists())

        url = reverse_lazy('core:hx_mission_delete', args=(self.mission_1.pk,))
        logger.info(f"URL: {url}")

        response = self.client.post(url, {"mission_id": self.mission_1.pk})
        logger.info(response)

        content = response.content.decode('utf-8')
        self.assertTrue(content.strip().startswith('<tr class="table-row">\n'))
        self.assertFalse(models.Mission.objects.filter(pk=self.mission_1.pk).exists(),
                         "Mission 1 should have been deleted")

        self.assertTrue(models.Mission.objects.filter(pk=self.mission_2.pk).exists(),
                        "Mission 2 should NOT have been deleted")
