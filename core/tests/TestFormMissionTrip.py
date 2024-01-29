import os

from bs4 import BeautifulSoup

from django.urls import reverse
from django.conf import settings
from django.test import tag, Client

from dart2.tests.DartTestCase import DartTestCase

from core import models
from core.tests import CoreFactoryFloor as core_factory


@tag('forms', 'form_mission_trip')
class TestMissionTripForm(DartTestCase):

    def setUp(self) -> None:
        self.client = Client()

    @tag('form_mission_events_test_entry_point')
    def test_entry_point(self):
        # When loading the Mission events page if no trip exists the -- New -- option should
        # be selected in the Trip entry form

        mission = core_factory.MissionFactory()
        url = reverse("core:form_trip_card", args=('default', mission.pk))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")
        trip_card = soup.find(id="div_id_card_mission_trips")

        trip_select = trip_card.find(id="control_id_trip_select_mission_trips")
        selected = trip_select.find("option", selected=True)
        self.assertEquals(selected.string, "--- New ---")

    @tag('form_mission_events_test_entry_point_get_add')
    def test_entry_point_get_add(self):
        # using the add button should return an information alert that will in turn call the form's POST method
        # When loading the Mission events page if no trip exists the -- New -- option should
        # be selected in the Trip entry form

        mission = core_factory.MissionFactory()
        url = reverse("core:form_trip_save", args=('default', mission.pk))

        response = self.client.get(url)
        soup = BeautifulSoup(response.content, "html.parser")

        trip_alert = soup.find(id="div_id_trip_alert")
        self.assertIn('hx-post',  trip_alert.attrs)
        self.assertEquals(trip_alert.attrs['hx-post'], url)

    @tag('form_mission_events_test_entry_point_post_add')
    def test_entry_point_post_add(self):
        # calling the form_trip_save url as a POST action with variables should create
        # a new trip and return the elements to be swapped on to the page

        mission = core_factory.MissionFactory()
        url = reverse("core:form_trip_save", args=('default', mission.pk))

        post_vars = {
            'mission': mission.pk,
            'start_date': "2024-01-24",
            'end_date': "2024-01-24",
            'platform': "N/A",
            'protocol': "N/A"
        }

        response = self.client.post(url, post_vars)
        soup = BeautifulSoup(response.content, "html.parser")

        form = soup.find(id="form_id_mission_trips")
        self.assertIn('hx-swap-oob', form.attrs)

        trip_card = form.find(id="div_id_card_mission_trips")
        self.assertIsNotNone(trip_card)

        trip_select = trip_card.find(id="control_id_trip_select_mission_trips")
        selected = trip_select.find("option", selected=True)
        self.assertEquals(selected.string, "2024-01-24 - 2024-01-24")

        event_card = soup.find(id="div_events_id")
        self.assertIsNotNone(event_card)

        event_details_card = soup.find(id="div_id_card_event_details")
        self.assertIsNotNone(event_details_card)

    @tag('form_mission_events_test_elog_get')
    def test_elog_get(self):
        # Provided a trip id, when the create events from elog button is pressed it calls the import elog url using
        # a get request the request should return an alert containing a hx-post using the same url on hx-trigger='load'
        trip = core_factory.TripFactory()
        url = reverse("core:form_trip_import_events_elog", args=("default", trip.pk))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content)
        alert = soup.find(id="div_id_event_alert_alert")
        self.assertIsNotNone(alert)
        self.assertIn('hx-post', alert.attrs)
        self.assertEquals(alert.attrs['hx-post'], url)
        self.assertIn('hx-trigger', alert.attrs)
        self.assertEquals(alert.attrs['hx-trigger'], 'load')

    @tag('form_mission_events_test_elog_post')
    def test_elog_post(self):
        # Provided a trip id and a "good" file, when the import elog url is called as a post request it should process
        # the file creating and adding the parsed events from the file to the provide trip
        mission = core_factory.MissionFactory(lead_scientist="N/A")
        trip = core_factory.TripFactory(mission=mission, platform="N/A", protocol="N/A")
        url = reverse("core:form_trip_import_events_elog", args=("default", trip.pk))

        self.sample_elog_file = os.path.join(settings.BASE_DIR, 'core/tests/sample_data/good.log')
        with open(self.sample_elog_file, 'rb') as fp:
            response = self.client.post(url, {'event': [fp]})

        mission = models.Mission.objects.get(pk=mission.pk)
        trip = models.Trip.objects.get(pk=trip.pk)

        # Lead Scientists, platform and protocol as specified in the sample log file
        self.assertEquals(mission.lead_scientist, "Lindsay Beazley")
        self.assertEquals(trip.platform, "James Cook")
        self.assertEquals(trip.protocol, "AZMP")

        # Once processed the post request should return a new Trip form, because some details might have been updated,
        # and a new alert area that calls the url to update the event selection and event detail cards
        soup = BeautifulSoup(response.content)
        trip_card = soup.find(id="form_id_mission_trips")
        self.assertIsNotNone(trip_card)

        alert = soup.find(id="div_id_event_alert")
        self.assertIsNotNone(alert)
