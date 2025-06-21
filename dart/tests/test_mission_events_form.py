from bs4 import BeautifulSoup
from django.test import RequestFactory, TestCase, tag
from django.urls import reverse

import user_settings.models
from dart import models as dart_models
from dart.tests import DartModelFactoryFloor
from dart.forms import mission_event_detail_form
from dart.forms.mission_event_detail_form import get_form, new_station, new_instrument, delete_event


@tag('event_detail_form')
class TestEventDetailForm(TestCase):

    def setUp(self):
        self.mission = DartModelFactoryFloor.MissionFactory(name="EventDetailTest")

    def test_new_event_returns_oob_form(self):
        url = reverse('dart:form_events_new', args=[self.mission.pk])
        response = self.client.get(url, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 200)
        self.assertIn('hx-swap-oob="true"', response.content.decode())
        self.assertIn('<form', response.content.decode())

    def test_new_event_returns_oob_elements(self):
        url = reverse('dart:form_events_new', args=[self.mission.pk])
        response = self.client.get(url, HTTP_HX_REQUEST='true')

        soup = BeautifulSoup(response.content, 'html.parser')

        event_input = soup.find('input', id="id_event_id")
        self.assertIsNotNone(event_input)
        self.assertEqual(event_input.attrs['type'], 'number')

        # Station select
        station_select = soup.find('select', id="id_global_station")
        self.assertIsNotNone(station_select)
        station_options = station_select.find_all('option')
        self.assertGreaterEqual(len(station_options), 2)
        self.assertEqual(station_options[0].text.strip(), "--------")
        self.assertEqual(station_options[1]['value'], "0")
        self.assertEqual(station_options[1].text.strip(), "New")

        # Instrument select
        instrument_select = soup.find('select', id="id_instrument")
        self.assertIsNotNone(instrument_select)
        instrument_options = instrument_select.find_all('option')
        self.assertGreaterEqual(len(instrument_options), 2)
        self.assertEqual(instrument_options[0].text.strip(), "--------")
        self.assertEqual(instrument_options[1]['value'], "0")
        self.assertEqual(instrument_options[1].text.strip(), "New")

    def test_new_form_get_returns_deselect_hx_trigger(self):
        # when the new_event function is called provided an event_id for an event that doesn't exist and HTML
        # event form should be returned in the response.content that has a hidden mission input with the mision.pk
        # and an event_id input with the provided event id
        url = reverse('dart:form_events_new', args=[self.mission.pk])
        response = self.client.get(url, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertIn('HX-Trigger', response)
        self.assertIn('deselect', response['HX-Trigger'])

    def test_new_event_without_event_id_returns_form_with_mission_and_event_id_1(self):
        # when no event id is provided the form should be returned with a mission field containing the mission.pk
        # and the event_id field should be 1
        url = reverse('dart:form_events_new', args=[self.mission.pk])
        response = self.client.get(url, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        mission_input = soup.find('input', {'name': 'mission', 'type': 'hidden'})
        event_id_input = soup.find('input', {'id': 'id_event_id', 'name': 'event_id'})
        self.assertIsNotNone(mission_input)
        self.assertEqual(str(mission_input['value']), str(self.mission.pk))
        self.assertIsNotNone(event_id_input)
        self.assertEqual(str(event_id_input['value']), "1")

    def test_new_event_without_event_id_sets_event_id_to_max_plus_one(self):
        # when multiple events exist the event_id field should be the maximum event ID of the existing events plus one.

        # Create two events with event_id 1 and 2
        event1 = DartModelFactoryFloor.EventFactory(mission=self.mission, event_id=1)
        event2 = DartModelFactoryFloor.EventFactory(mission=self.mission, event_id=2)

        url = reverse('dart:form_events_new', args=[self.mission.pk])
        response = self.client.get(url, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        event_id_input = soup.find('input', {'id': 'id_event_id', 'name': 'event_id'})
        self.assertIsNotNone(event_id_input)
        # Should be max event_id (2) + 1 = 3
        self.assertEqual(str(event_id_input['value']), "3")

    def test_new_event_with_existing_event_id_prefills_fields(self):
        # When an event ID is provided for an existing event the event_ID field should be equal to the provided
        # event ID. The station field should be equal to the station of the provided event and the instrument id
        # should be equal to that of the event as well.

        # Create related objects
        station_name = "AR7W_02"
        station = DartModelFactoryFloor.StationFactory(name=station_name)
        glb_station = user_settings.models.GlobalStation.objects.get(name=station_name)
        instrument = DartModelFactoryFloor.NetInstrumentFactory()
        event = DartModelFactoryFloor.EventFactory(
            mission=self.mission,
            event_id=5,
            station=station,
            instrument=instrument
        )

        url = reverse('dart:form_events_update', args=[self.mission.pk, event.pk])
        response = self.client.get(url, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Check event_id field
        event_id_input = soup.find('input', {'id': 'id_event_id', 'name': 'event_id'})
        self.assertIsNotNone(event_id_input)
        self.assertEqual(str(event_id_input['value']), str(event.event_id))

        # Check station field
        station_select = soup.find('select', id="id_global_station")
        self.assertIsNotNone(station_select)
        self.assertEqual(station_select.find('option', selected=True)['value'], str(glb_station.pk))

        # Check instrument field
        instrument_select = soup.find('select', id="id_instrument")
        self.assertIsNotNone(instrument_select)
        self.assertEqual(instrument_select.find('option', selected=True)['value'], str(instrument.pk))

    def test_post_creates_event_with_given_event_id_station_and_instrument(self):
        #When provided an event_id, user_settings.models.GlobalStation id, and exsting dart.models.Instrument id
        # in a POST request an event matching the provided details should be created
        # Setup: create station and instrument
        station_name = "AR7W_02"
        station = DartModelFactoryFloor.StationFactory(name=station_name)
        glb_station = user_settings.models.GlobalStation.objects.get(name=station_name)
        instrument = DartModelFactoryFloor.NetInstrumentFactory()
        event_id = 42

        url = reverse('dart:form_events_new', args=[self.mission.pk])
        post_data = {
            'mission': self.mission.pk,
            'event_id': event_id,
            'global_station': glb_station.pk,
            'instrument': instrument.pk,
        }
        response = self.client.post(url, post_data, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)

        # Check that the event was created with the correct details
        from dart.models import Event
        event = Event.objects.get(mission=self.mission, event_id=event_id)
        self.assertEqual(event.station.pk, station.pk)
        self.assertEqual(event.instrument.pk, instrument.pk)

    def test_post_missing_station_and_instrument_returns_field_errors(self):
        # when provided an event_id and no station or instrument in a POST request the request.content should
        # contain error objects for the mission station and instrument fields.

        # Only provide mission and event_id, omit station and instrument
        event_id = 99
        url = reverse('dart:form_events_new', args=[self.mission.pk])
        post_data = {
            'mission': self.mission.pk,
            'event_id': event_id,
            # 'station' and 'instrument' are intentionally omitted
        }
        response = self.client.post(url, post_data, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check for error messages for required fields
        self.assertIn('This field is required', content)
        self.assertIn('name="station"', content)
        self.assertIn('name="instrument"', content)
        self.assertIn('name="mission"', content)


class MissionEventDetailFormTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.mission = DartModelFactoryFloor.MissionFactory(name="Test Mission")
        self.global_station = DartModelFactoryFloor.GlobalStationFactory(name="Test Station")
        self.station = DartModelFactoryFloor.StationFactory(name="Test Station")
        self.instrument = DartModelFactoryFloor.NetInstrumentFactory(name="Test Instrument")
        self.event = DartModelFactoryFloor.EventFactory(mission=self.mission, station=self.station)

    def test_get_form(self):
        request = self.factory.get(reverse('dart:form_events_new', args=[self.mission.pk]))
        response = get_form(request, self.mission.pk)
        self.assertEqual(response.status_code, 200)

    def test_new_station_post(self):
        request = self.factory.post(reverse('dart:form_events_new_station'), {'global_station': self.global_station.pk})
        response = new_station(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(dart_models.Station.objects.filter(name__iexact=self.global_station.name).exists())

    def test_new_instrument_post(self):
        request = self.factory.post(reverse('dart:form_events_new_instrument'), {'instrument': 'New Instrument', 'type': dart_models.InstrumentType.net})
        response = new_instrument(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(dart_models.Instrument.objects.filter(name__iexact='New Instrument').exists())

    def test_delete_event(self):
        request = self.factory.post(reverse('dart:form_events_delete', args=[self.mission.pk, self.event.pk]))
        response = delete_event(request, self.mission.pk, self.event.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(dart_models.Event.objects.filter(pk=self.event.pk).exists())