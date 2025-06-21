import unittest
from unittest.mock import patch, MagicMock

from bs4 import BeautifulSoup
from django.test import RequestFactory, TestCase
from django.http import HttpResponse
from dart.forms import mission_events

class MissionEventsTests(TestCase):
    @patch("dart.forms.mission_events.dart_models.Event")
    def test_list_events_returns_html(self, mock_event):
        # Mock queryset and event objects
        mock_obj = MagicMock()
        mock_obj.pk = 1
        mock_obj.event_id = 42
        mock_obj.station.name = "StationA"
        mock_obj.instrument.get_type_display.return_value = "CTD"
        mock_event.objects.filter.return_value.order_by.return_value.select_related.return_value = [mock_obj]

        request = RequestFactory().get("/fake-url/")
        response = mission_events.list_events(request, mission_id=123)
        self.assertIsInstance(response, HttpResponse)
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.find(id="td_id_event_1"))

    @patch("dart.forms.mission_events.render_to_string")
    @patch("dart.forms.mission_events.dart_models.Event")
    def test_event_selection_select(self, mock_event, mock_render):
        # Mock event object
        mock_obj = MagicMock()
        mock_obj.pk = 2
        mock_obj.event_id = 99
        mock_obj.station.name = "StationB"
        mock_obj.instrument.get_type_display.return_value = "Sensor"
        mock_obj.mission = "MissionObj"
        mock_event.objects.get.return_value = mock_obj
        mock_render.return_value = "<div>Event Details</div>"

        request = RequestFactory().get("/fake-url/")
        response = mission_events.event_selection(request, mission_id=1, event_pk=2)
        self.assertIsInstance(response, HttpResponse)
        self.assertIn("table-success", response.content.decode())
        self.assertEqual(response["HX-Trigger"], "deselect")
        self.assertIn("Event Details", response.content.decode())

    @patch("dart.forms.mission_events.dart_models.Event")
    def test_event_selection_deselect(self, mock_event):
        mock_obj = MagicMock()
        mock_obj.pk = 3
        mock_obj.event_id = 77
        mock_obj.station.name = "StationC"
        mock_obj.instrument.get_type_display.return_value = "CTD"
        mock_obj.mission = "MissionObj"
        mock_event.objects.get.return_value = mock_obj

        request = RequestFactory().get("/fake-url/?deselect=true")
        response = mission_events.event_selection(request, mission_id=1, event_pk=3)
        self.assertIsInstance(response, HttpResponse)
        self.assertNotIn("table-success", response.content.decode())
        self.assertNotIn("HX-Trigger", response.headers)

    @patch("dart.forms.mission_events.render_to_string")
    def test_get_event_details_renders_html(self, mock_render):
        mock_render.return_value = "<div>Event Details Card</div>"
        event = MagicMock()
        event.mission = "MissionObj"
        soup = mission_events.get_event_details(event)
        self.assertIn("Event Details Card", str(soup))