import logging
from datetime import datetime

from bs4 import BeautifulSoup
from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError

from django.test import tag, Client, SimpleTestCase
from django.urls import reverse
from django.utils.translation import gettext as _

from core import form_biochem_pre_validation, views_mission_sample
from core import models as core_models
from core.tests import CoreFactoryFloor as core_factory
from core.form_biochem_batch import get_mission_batch_id

from dart.tests.DartTestCase import DartTestCase

from biochem import models as bio_models

logger = logging.getLogger(f'dart.test.{__name__}')

biochem_db = 'biochem'


@tag('view', 'view_mission_sample_validation')
class TestViewMissionSampleValidation(SimpleTestCase):

    fixtures = ['default_biochem_fixtures']
    test_name = '18te2409'

    def setUp(self):
        self.mission = core_factory.MissionFactory(mission_descriptor=self.test_name)

    def setup_connection(self):
        self.databases = settings.DATABASES
        self.databases[biochem_db] = self.databases['default'].copy()
        self.databases[biochem_db]['NAME'] = 'file:memorydb_biochem?mode=memory&cache=shared'

    def get_batches_model(self):
        try:
            bio_models.Bcbatches.objects.using(biochem_db).exists()
        except OperationalError as ex:
            with connections[biochem_db].schema_editor() as editor:
                editor.create_model(bio_models.Bcbatches)

    # I've found when running this test class All Tests it's required to add the biochem_db to the databases first
    # otherwise you get a django.
    @classmethod
    def setUpClass(cls):
        # databases = settings.DATABASES
        # databases[biochem_db] = databases['default'].copy()
        # databases[biochem_db]['NAME'] = 'file:memorydb_biochem?mode=memory&cache=shared'
        pass

    @classmethod
    def tearDownClass(cls):
        if biochem_db in settings.DATABASES:
            settings.DATABASES.pop(biochem_db)

    def test_get_batch_id_no_model(self):
        # if there is no connection or model available to get the batch ID then 1 should be returned
        batch_id = get_mission_batch_id()

        self.assertEqual(1, batch_id)

    def test_get_batch_id_with_connection(self):
        # if the connection exists, but there is no batches table, return 1
        self.setup_connection()

        batch_id = get_mission_batch_id()
        self.assertEqual(1, batch_id)

    def test_get_batch_id_with_model(self):
        # if the connection exists and there is a batches table, get the lowest batch ID, which should be 1
        # if the table is empty
        self.setup_connection()
        self.get_batches_model()

        batch_id = get_mission_batch_id()
        self.assertEqual(1, batch_id)

    def test_get_batch_id_with_model_with_mission(self):
        # if the connection exists and there is a batches table and there are missions, get the lowest free batch ID
        self.setup_connection()
        self.get_batches_model()

        bio_models.Bcbatches.objects.using(biochem_db).create(batch__batch_seq=1, name=self.test_name)
        bio_models.Bcbatches.objects.using(biochem_db).create(batch__batch_seq=5, name=self.test_name)
        batch_id = get_mission_batch_id()
        self.assertEqual(2, batch_id)


@tag('forms', 'form_biochem_pre_validation')
class TestFormBioChemDatabase(DartTestCase):
    expected_validation_mission_name = "Validation"

    run_validation_url = "core:form_biochem_pre_validation_run"
    get_errors_url = "core:form_biochem_pre_validation_get_validation_errors"

    def setUp(self):
        self.client = Client()
        start_date = datetime.strptime("2020-02-01", "%Y-%m-%d")
        end_date = datetime.strptime("2020-01-01", "%Y-%m-%d")
        self.mission = core_factory.MissionFactory(name=self.expected_validation_mission_name,
                                                   start_date=start_date, end_date=end_date)

    # The backend will communcate with the user though the use of the notification logger.
    @tag('form_biochem_pre_validation_test_notification_logger')
    def test_notification_logger(self):
        class MockHandler(logging.StreamHandler):
            date_notification_received = False

            def emit(self, record):
                if record.msg == _("Validating Mission Dates"):
                    self.date_notification_received = True

        handler = MockHandler()
        form_biochem_pre_validation.logger_notifications.addHandler(handler)

        form_biochem_pre_validation.validate_mission(self.mission)

        self.assertTrue(handler.date_notification_received)

    @tag('form_biochem_pre_validation_test_initial_get_errors_url_get')
    def test_initial_get_errors_url_get(self):
        # call to get_errors_url should retrun an un-ordered list of issues if any issues exist the calling element
        # has an hx-swap=='innerHTML' so just the <ul> tag and lower is required or nothing if there are no errors
        #
        # The mission object has its start and end dates reversed so a UL element should be returned.
        core_models.Error.objects.create(mission=self.mission, message="Something went wrong",
                                         type=core_models.ErrorType.biochem)

        response = self.client.get(reverse(self.get_errors_url, args=('default', self.mission.pk)))
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.find("ul"))

    @tag('form_biochem_pre_validation_test_initial_validate_url_get')
    def test_initial_validate_url_get(self):
        # on the first call to the form_biochem_pre_validation_run url a websocket message dialog should be sent
        # back that contains hx-trigger=='load' and hx-post attributes to trigger the actual validation process
        response = self.client.get(reverse(self.run_validation_url, args=('default', self.mission.pk)))
        logger.debug(response.headers)

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(alert := soup.find("div", {"id": "div_id_biochem_validation_details_alert"}))
        div = alert.find('div')
        self.assertIn('hx-trigger', div.attrs)
        self.assertIn('hx-post', div.attrs)

    @tag('form_biochem_pre_validation_test_initial_validate_url_post')
    def test_initial_validate_url(self):
        # Upon completion the form_biochem_pre_validation_run url called as a post method, should return a
        # hx-trigger=='biochem_validation_update' action to notify listeners they should update their
        # list of BioChem validation issues
        response = self.client.post(reverse(self.run_validation_url, args=('default', self.mission.pk)))
        logger.debug(response.headers)

        self.assertIn('HX-Trigger', response.headers)
        self.assertEqual(response.headers['HX-Trigger'], 'biochem_validation_update')

    @tag('form_biochem_pre_validation_test_validate_missing_dates')
    def test_validate_missing_dates(self):
        bad_mission = core_models.Mission(start_date=None, end_date=None)
        errors: [core_models.Error] = form_biochem_pre_validation._validate_mission_dates(bad_mission)

        self.assertIsNotNone(errors)

        self.assertIsInstance(errors[0], core_models.Error)
        self.assertEqual(errors[0].mission, bad_mission)
        self.assertEqual(errors[0].type, core_models.ErrorType.biochem)
        self.assertEqual(errors[0].message, _("Missing start date"))
        self.assertEqual(errors[0].code, form_biochem_pre_validation.BIOCHEM_CODES.DATE_MISSING.value)

        self.assertIsInstance(errors[1], core_models.Error)
        self.assertEqual(errors[1].mission, bad_mission)
        self.assertEqual(errors[1].type, core_models.ErrorType.biochem)
        self.assertEqual(errors[1].message, _("Missing end date"))
        self.assertEqual(errors[0].code, form_biochem_pre_validation.BIOCHEM_CODES.DATE_MISSING.value)


    @tag('form_biochem_pre_validation_test_validate_bad_dates')
    def test_validate_bad_dates(self):
        start_date = datetime.strptime("2020-02-01", "%Y-%m-%d")
        end_date = datetime.strptime("2020-01-01", "%Y-%m-%d")

        bad_mission = core_models.Mission(start_date=start_date, end_date=end_date)
        errors: [core_models.Error] = form_biochem_pre_validation._validate_mission_dates(bad_mission)

        self.assertIsNotNone(errors)

        self.assertIsInstance(errors[0], core_models.Error)
        self.assertEqual(errors[0].mission, bad_mission)
        self.assertEqual(errors[0].type, core_models.ErrorType.biochem)
        self.assertEqual(errors[0].message, _("End date comes before Start date"))
        self.assertEqual(errors[0].code, form_biochem_pre_validation.BIOCHEM_CODES.DATE_BAD_VALUES.value)

    @tag('form_biochem_pre_validation_test_mission_descriptor', 'git_issue_144')
    def test_mission_descriptor(self):
        # provided a mission with no name (used as the mission descriptor) to the _validation_mission_descriptor
        # function an error should be reported.

        bad_mission = core_factory.MissionFactory()
        errors: [core_models.Error] = form_biochem_pre_validation._validation_mission_descriptor(bad_mission)

        self.assertIsNotNone(errors)

        self.assertIsInstance(errors[0], core_models.Error)
        self.assertEqual(errors[0].mission, bad_mission)
        self.assertEqual(errors[0].type, core_models.ErrorType.biochem)
        self.assertEqual(errors[0].message, _("Mission descriptor doesn't exist"))
        self.assertEqual(errors[0].code, form_biochem_pre_validation.BIOCHEM_CODES.DESCRIPTOR_MISSING.value)

    @tag('form_biochem_pre_validation_test_mission_descriptor', 'git_issue_144')
    def test_validate_mission_descriptor_mission(self):
        # ensure the _validate_mission_descriptor function is called through the validation_mission function
        bad_mission = core_factory.MissionFactory()
        errors: [core_models.Error] = form_biochem_pre_validation.validate_mission(bad_mission)

        self.assertIsNotNone(errors)

        self.assertIsInstance(errors[0], core_models.Error)
        self.assertEqual(errors[0].mission, bad_mission)
        self.assertEqual(errors[0].type, core_models.ErrorType.biochem)
        self.assertEqual(errors[0].message, _("Mission descriptor doesn't exist"))
        self.assertEqual(errors[0].code, form_biochem_pre_validation.BIOCHEM_CODES.DESCRIPTOR_MISSING.value)

    @tag('form_biochem_pre_validation_test_bottle_date_no_location_fail', 'git_issue_147')
    def test_bottle_date_no_location_fail(self):
        # given an event with no location and a series of bottles with no location validation should return an error
        event = core_factory.CTDEventFactoryBlank(mission=self.mission)
        bottles = core_factory.BottleFactory.create_batch(10, event=event)

        errors: [core_models.Error] = form_biochem_pre_validation._validate_bottles(self.mission)

        self.assertIsInstance(errors[0], core_models.Error)
        self.assertEqual(errors[0].mission, self.mission)
        self.assertEqual(errors[0].type, core_models.ErrorType.biochem)
        self.assertEqual(errors[0].message, _("Event is missing a position. Event ID : ") + str(event.event_id))
        self.assertEqual(errors[0].code, form_biochem_pre_validation.BIOCHEM_CODES.POSITION_MISSING.value)

