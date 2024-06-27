import logging
from datetime import datetime

from bs4 import BeautifulSoup
from django.test import tag, Client
from django.urls import reverse
from django.utils.translation import gettext as _

from core import form_validation_biochem
from core import models as core_models
from core.tests import CoreFactoryFloor as core_factory

from dart.tests.DartTestCase import DartTestCase

logger = logging.getLogger(f'dart.test.{__name__}')


@tag('forms', 'form_validation_biochem')
class TestFormBioChemDatabase(DartTestCase):
    expected_validation_mission_name = "Validation"

    run_validation_url = "core:form_biochem_validation_run"
    get_errors_url = "core:form_validation_get_validation_errors"

    def setUp(self):
        self.client = Client()
        start_date = datetime.strptime("2020-02-01", "%Y-%m-%d")
        end_date = datetime.strptime("2020-01-01", "%Y-%m-%d")
        self.mission = core_factory.MissionFactory(name=self.expected_validation_mission_name,
                                                   start_date=start_date, end_date=end_date)

    # The backend will communcate with the user though the use of the notification logger.
    @tag('form_validation_biochem_test_notification_logger')
    def test_notification_logger(self):
        class MockHandler(logging.StreamHandler):
            date_notification_received = False

            def emit(self, record):
                if record.msg == _("Validating Mission Dates"):
                    self.date_notification_received = True

        handler = MockHandler()
        form_validation_biochem.logger_notifications.addHandler(handler)

        form_validation_biochem.validate_mission(self.mission)

        self.assertTrue(handler.date_notification_received)

    @tag('form_validation_biochem_test_initial_get_errors_url_get')
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

    @tag('form_validation_biochem_test_initial_validate_url_get')
    def test_initial_validate_url_get(self):
        # on the first call to the form_biochem_validation_run url a websocket message dialog should be sent
        # back that contains hx-trigger=='load' and hx-post attributes to trigger the actual validation process
        response = self.client.get(reverse(self.run_validation_url, args=('default', self.mission.pk)))
        logger.debug(response.headers)

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(alert := soup.find("div", {"id": "div_id_biochem_validation_details_alert"}))
        div = alert.find('div')
        self.assertIn('hx-trigger', div.attrs)
        self.assertIn('hx-post', div.attrs)

    @tag('form_validation_biochem_test_initial_validate_url_post')
    def test_initial_validate_url(self):
        # Upon completion the form_biochem_validation_run url called as a post method, should return a
        # hx-trigger=='biochem_validation_update' action to notify listeners they should update their
        # list of BioChem validation issues
        response = self.client.post(reverse(self.run_validation_url, args=('default', self.mission.pk)))
        logger.debug(response.headers)

        self.assertIn('HX-Trigger', response.headers)
        self.assertEquals(response.headers['HX-Trigger'], 'biochem_validation_update')

    @tag('form_validation_biochem_test_validate_missing_dates')
    def test_validate_missing_dates(self):
        bad_mission = core_models.Mission(start_date=None, end_date=None)
        errors: [core_models.Error] = form_validation_biochem._validate_mission_dates(bad_mission)

        self.assertIsNotNone(errors)

        self.assertIsInstance(errors[0], core_models.Error)
        self.assertEquals(errors[0].mission, bad_mission)
        self.assertEquals(errors[0].type, core_models.ErrorType.biochem)
        self.assertEquals(errors[0].message, _("Missing start date"))
        self.assertEquals(errors[0].code, form_validation_biochem.BIOCHEM_CODES.DATE_MISSING.value)

        self.assertIsInstance(errors[1], core_models.Error)
        self.assertEquals(errors[1].mission, bad_mission)
        self.assertEquals(errors[1].type, core_models.ErrorType.biochem)
        self.assertEquals(errors[1].message, _("Missing end date"))
        self.assertEquals(errors[0].code, form_validation_biochem.BIOCHEM_CODES.DATE_MISSING.value)


    @tag('form_validation_biochem_test_validate_bad_dates')
    def test_validate_bad_dates(self):
        start_date = datetime.strptime("2020-02-01", "%Y-%m-%d")
        end_date = datetime.strptime("2020-01-01", "%Y-%m-%d")

        bad_mission = core_models.Mission(start_date=start_date, end_date=end_date)
        errors: [core_models.Error] = form_validation_biochem._validate_mission_dates(bad_mission)

        self.assertIsNotNone(errors)

        self.assertIsInstance(errors[0], core_models.Error)
        self.assertEquals(errors[0].mission, bad_mission)
        self.assertEquals(errors[0].type, core_models.ErrorType.biochem)
        self.assertEquals(errors[0].message, _("End date comes before Start date"))
        self.assertEquals(errors[0].code, form_validation_biochem.BIOCHEM_CODES.DATE_BAD_VALUES.value)

    @tag('form_validation_biochem_test_mission_descriptor', 'git_issue_144')
    def test_mission_descriptor(self):
        # provided a mission with no name (used as the mission descriptor) to the _validation_mission_descriptor
        # function an error should be reported.

        bad_mission = core_factory.MissionFactory()
        errors: [core_models.Error] = form_validation_biochem._validation_mission_descriptor(bad_mission)

        self.assertIsNotNone(errors)

        self.assertIsInstance(errors[0], core_models.Error)
        self.assertEquals(errors[0].mission, bad_mission)
        self.assertEquals(errors[0].type, core_models.ErrorType.biochem)
        self.assertEquals(errors[0].message, _("Mission descriptor doesn't exist"))
        self.assertEquals(errors[0].code, form_validation_biochem.BIOCHEM_CODES.DESCRIPTOR_MISSING.value)

    @tag('form_validation_biochem_test_mission_descriptor', 'git_issue_144')
    def test_validate_mission_descriptor_mission(self):
        # ensure the _validate_mission_descriptor function is called through the validation_mission function
        bad_mission = core_factory.MissionFactory()
        errors: [core_models.Error] = form_validation_biochem.validate_mission(bad_mission)

        self.assertIsNotNone(errors)

        self.assertIsInstance(errors[0], core_models.Error)
        self.assertEquals(errors[0].mission, bad_mission)
        self.assertEquals(errors[0].type, core_models.ErrorType.biochem)
        self.assertEquals(errors[0].message, _("Mission descriptor doesn't exist"))
        self.assertEquals(errors[0].code, form_validation_biochem.BIOCHEM_CODES.DESCRIPTOR_MISSING.value)

    @tag('form_validation_biochem_test_bottle_date_no_location_fail', 'git_issue_147')
    def test_bottle_date_no_location_fail(self):
        # given an event with no location and a series of bottles with no location validation should return an error
        event = core_factory.CTDEventFactoryBlank(mission=self.mission)
        bottles = core_factory.BottleFactory.create_batch(10, event=event)

        errors: [core_models.Error] = form_validation_biochem._validate_bottles(self.mission)

        self.assertIsInstance(errors[0], core_models.Error)
        self.assertEquals(errors[0].mission, self.mission)
        self.assertEquals(errors[0].type, core_models.ErrorType.biochem)
        self.assertEquals(errors[0].message, _("Event is missing a position. Event ID : ") + str(event.event_id))
        self.assertEquals(errors[0].code, form_validation_biochem.BIOCHEM_CODES.POSITION_MISSING.value)

