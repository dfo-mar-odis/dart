import decimal
from http.client import responses

from bs4 import BeautifulSoup

from django.urls import reverse
from django.test import TestCase, tag

from dart.tests import DartModelFactoryFloor as dart_factory
from dart import models

@tag('event_actions_form')
class TestActionsDetailForm(TestCase):
    def setUp(self):
        # Create a mission and event for testing
        self.mission = dart_factory.MissionFactory(name="TestMission")
        self.event = dart_factory.EventFactory(mission=self.mission)

    @tag('event_actions_form_test_action_form_returns_form_with_event_id')
    def test_action_form_returns_form_with_event_id(self):
        # Should return the form when event id is provided
        url = reverse('dart:form_event_action_new', args=[self.event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.content.decode().lower())
        self.assertIn('action', response.content.decode().lower())

    @tag('event_actions_form_test_action_form_fields_present')
    def test_action_form_fields_present(self):
        url = reverse('dart:form_event_action_new', args=[self.event.pk])
        response = self.client.get(url)
        soup = BeautifulSoup(response.content, "html.parser")

        form = soup.find("div", id="div_id_action_form")
        self.assertIsNotNone(form, "Form not found in response")

        # Hidden input for event pk
        hidden_event = form.find("input", {"type": "hidden", "value": str(self.event.pk)})
        self.assertIsNotNone(hidden_event, "Hidden input for event pk not found")

        # Select for action type
        select_type = form.find("select", {"name": "type"})
        self.assertIsNotNone(select_type, "Select field for action type not found")

        # Date/time field
        datetime_field = form.find("input", {"name": "date_time"})
        self.assertIsNotNone(datetime_field, "Date/time field not found")

        # Latitude field
        latitude_field = form.find("input", {"name": "latitude"})
        self.assertIsNotNone(latitude_field, "Latitude field not found")

        # Longitude field
        longitude_field = form.find("input", {"name": "longitude"})
        self.assertIsNotNone(longitude_field, "Longitude field not found")

        # Sounding field
        sounding_field = form.find("input", {"name": "sounding"})
        self.assertIsNotNone(sounding_field, "Sounding field not found")

    @tag('event_actions_form_test_action_form_post_creates_new_action')
    def test_action_form_post_creates_new_action(self):
        url = reverse('dart:form_event_action_new', args=[self.event.pk])
        action = dart_factory.ActionFactory.build(event=self.event)
        post_vars = {
            'event': action.event.pk,
            'type': action.type,
            'date_time': action.date_time,
            'latitude': action.latitude,
            'longitude': action.longitude,
            'sounding': action.sounding
        }
        response = self.client.post(url, post_vars)

        actions = self.event.actions.all()
        self.assertIsNotNone(actions)
        self.assertEqual(len(actions), 1)
        new_action = actions.first()
        self.assertEqual(new_action.event.pk, action.event.pk)
        self.assertEqual(new_action.type, action.type)
        self.assertEqual(new_action.date_time, action.date_time)
        self.assertEqual(new_action.latitude, action.latitude)
        self.assertEqual(new_action.longitude, action.longitude)
        self.assertEqual(new_action.sounding, action.sounding)

    @tag('event_actions_form_test_action_form_with_action')
    def test_action_form_with_action(self):
        action = dart_factory.ActionFactory(event=self.event)
        url = reverse('dart:form_event_action_update', args=[self.event.pk, action.pk])
        response = self.client.get(url)
        soup = BeautifulSoup(response.content, "html.parser")

        form = soup.find("div", id="div_id_action_form")
        self.assertIsNotNone(form, "Form not found in response")

        # Hidden input for event pk
        hidden_event = form.find("input", {"type": "hidden", "value": str(self.event.pk)})
        self.assertIsNotNone(hidden_event, "Hidden input for event pk not found")

        # Select for action type
        select_type = form.find("select", {"name": "type"})
        self.assertIsNotNone(select_type, "Select field for action type not found")
        self.assertEqual(select_type.find("option", {"selected": True}).get("value"), str(action.type), "Action type not populated correctly")

        # Date/time field
        datetime_field = form.find("input", {"name": "date_time"})
        self.assertIsNotNone(datetime_field, "Date/time field not found")
        self.assertEqual(datetime_field.get("value"), action.date_time.strftime("%Y-%m-%d %H:%M:%S"), "Date/time not populated correctly")

        # Latitude field
        latitude_field = form.find("input", {"name": "latitude"})
        self.assertIsNotNone(latitude_field, "Latitude field not found")
        self.assertEqual(decimal.Decimal(latitude_field.get("value")), action.latitude, "Latitude not populated correctly")

        # Longitude field
        longitude_field = form.find("input", {"name": "longitude"})
        self.assertIsNotNone(longitude_field, "Longitude field not found")
        self.assertEqual(decimal.Decimal(longitude_field.get("value")), action.longitude, "Longitude not populated correctly")

        # Sounding field
        sounding_field = form.find("input", {"name": "sounding"})
        self.assertIsNotNone(sounding_field, "Sounding field not found")
        self.assertEqual(sounding_field.get("value"), str(action.sounding), "Sounding not populated correctly")

    @tag('event_actions_form_test_action_form_post_updates_action')
    def test_action_form_post_updates_action(self):
        action = dart_factory.ActionFactory.create(event=self.event)
        url = reverse('dart:form_event_action_update', args=[self.event.pk, action.pk])
        post_vars = {
            'event': action.event.pk,
            'type': (action.type + 1),
            'date_time': action.date_time,
            'latitude': action.latitude,
            'longitude': action.longitude,
            'sounding': action.sounding
        }
        response = self.client.post(url, post_vars)

        actions = self.event.actions.all()
        self.assertIsNotNone(actions)
        self.assertEqual(len(actions), 1)
        new_action = actions.first()
        self.assertEqual(new_action.event.pk, action.event.pk)
        self.assertEqual(new_action.type, (action.type + 1))
        self.assertEqual(new_action.date_time, action.date_time)
        self.assertEqual(new_action.latitude, action.latitude)
        self.assertEqual(new_action.longitude, action.longitude)
        self.assertEqual(new_action.sounding, action.sounding)