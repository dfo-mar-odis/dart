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
        self.url = reverse_lazy('core:form_trip_import_events_elog', args=('default', self.trip.pk,))
        self.client = Client()

    def test_elog_uplaod_missing_mid(self):
        logger.info("Running test_elog_uplaod_missing_mid")

        file_name = 'missing_mid_bad.log'

        with open(self.file_location+file_name, 'rb') as fp:
            self.client.post(self.url, {'event': fp})

        errors = self.mission.file_errors.all()
        self.assertTrue(errors.exists())
        self.assertEquals(errors[0].type, models.ErrorType.event)

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
