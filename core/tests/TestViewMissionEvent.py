from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.test import TestCase, tag
from django.http import HttpRequest
from django.urls import reverse

from unittest.mock import patch, MagicMock

from core.tests import CoreFactoryFloor as CoreFactory
from core import models as core_models
from core import views_mission_event


@tag('views', 'view_mission_event')
class TestViewMissionEvent(TestCase):

    def setUp(self):
        self.mission = CoreFactory.MissionFactory.create(name="TestMission")

    @patch('core.views_mission_event.render_crispy_form')
    def test_get_validation_card(self, mock_render_crispy_form):
        mock_request = HttpRequest()
        mock_render_crispy_form.return_value = '<div>Validation Card</div>'

        response = views_mission_event.get_validation_card(mock_request, mission_id=1)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Validation Card', response.content.decode())

    @patch('core.views_mission_event.render_crispy_form')
    def test_get_file_validation_card(self, mock_render_crispy_form):
        mock_request = HttpRequest()
        mock_render_crispy_form.return_value = '<div>File Validation Card</div>'

        response = views_mission_event.get_file_validation_card(mock_request, mission_id=1)

        self.assertEqual(response.status_code, 200)
        self.assertIn('File Validation Card', response.content.decode())

    @patch('core.views_mission_event.models.EventError.objects.filter')
    def test_get_event_error_count_gt_0(self, mock_filter):
        mock_request = HttpRequest()
        mock_filter.return_value.count.return_value = 5

        response = views_mission_event.get_event_error_count(mock_request, mission_id=1)

        self.assertEqual(response.status_code, 200)
        card = BeautifulSoup(response.content, 'html.parser')
        error_count_div = card.find(id='div_id_event_error_count')

        self.assertEqual(error_count_div.string, '5')
        self.assertIn('bg-danger', error_count_div.attrs['class'])

    @patch('core.views_mission_event.models.EventError.objects.filter')
    def test_get_event_error_count_0(self, mock_filter):
        mock_request = HttpRequest()
        mock_filter.return_value.count.return_value = 0

        response = views_mission_event.get_event_error_count(mock_request, mission_id=1)

        self.assertEqual(response.status_code, 200)
        card = BeautifulSoup(response.content, 'html.parser')
        error_count_div = card.find(id='div_id_event_error_count')

        self.assertEqual(error_count_div.string, '0')
        self.assertIn('bg-success', error_count_div.attrs['class'])


    @patch('core.views_mission_event.models.Mission.objects.get')
    def test_get_file_error_count_gt_0(self, mock_get_mission):
        mock_request = HttpRequest()

        mock_filter = MagicMock()
        mock_filter.count.return_value = 5

        mock_mission = MagicMock()
        mock_mission.file_errors.filter.return_value = mock_filter

        mock_get_mission.return_value = mock_mission

        response = views_mission_event.get_file_error_count(mock_request, mission_id=1)

        self.assertEqual(response.status_code, 200)
        card = BeautifulSoup(response.content, 'html.parser')
        error_count_div = card.find(id='div_id_event_file_count')

        self.assertEqual(error_count_div.string, '5')
        self.assertIn('bg-danger', error_count_div.attrs['class'])

    @patch('core.views_mission_event.models.Mission.objects.get')
    def test_get_file_error_count_0(self, mock_get_mission):
        mock_request = HttpRequest()

        mock_filter = MagicMock()
        mock_filter.count.return_value = 0

        mock_mission = MagicMock()
        mock_mission.file_errors.filter.return_value = mock_filter

        mock_get_mission.return_value = mock_mission

        response = views_mission_event.get_file_error_count(mock_request, mission_id=1)

        self.assertEqual(response.status_code, 200)
        card = BeautifulSoup(response.content, 'html.parser')
        error_count_div = card.find(id='div_id_event_file_count')

        self.assertEqual(error_count_div.string, '0')
        self.assertIn('bg-success', error_count_div.attrs['class'])

    def test_revalidate_events_get(self):
        mock_request = HttpRequest()
        mock_request.method = "GET"

        response = views_mission_event.revalidate_events(mock_request, mission_id=1)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Revalidating', response.content.decode())

    @patch('core.views_mission_event.models.Mission.objects.get')
    def test_revalidate_events_post(self, mock_get_mission):
        mock_request = HttpRequest()
        mock_request.method = "POST"

        mock_get_mission.return_value = self.mission

        response = views_mission_event.revalidate_events(mock_request, mission_id=1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['HX-Trigger'], 'event_updated')

        card = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(card)

    @patch('core.views_mission_event.models.FileError.objects.filter')
    def test_delete_log_file_errors(self, mock_filter):
        mock_request = HttpRequest()
        mock_filter.return_value.delete.return_value = None

        response = views_mission_event.delete_log_file_errors(mock_request, file_name="test_file")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Trigger'], 'recount_file_errors')

    @patch('core.views_mission_event.models.EventError.objects.filter')
    def test_delete_event_errors(self, mock_filter):
        mock_request = HttpRequest()
        mock_filter.return_value.delete.return_value = None

        response = views_mission_event.delete_event_errors(mock_request, event_id=1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Trigger'], 'recount_event_errors')

    def test_delete_log_file_error_no_more_errors(self):
        file_error = CoreFactory.FileErrorFactory.create(mission=self.mission)
        mock_request = HttpRequest()

        count = core_models.FileError.objects.count()
        self.assertEqual(count, 1)

        response = views_mission_event.delete_log_file_error(mock_request, file_error.pk, 'uuid123')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Trigger'], 'recount_file_errors')

        # if there are no errors left then a hx-swap-oob: delete attribute should be returned
        # to remove the card from the page
        card = BeautifulSoup(response.content, 'html.parser')
        div = card.find(id=f'div_id_card_file_validation_uuid123')
        self.assertIsNotNone(div)
        self.assertEqual(div.attrs['hx-swap-oob'], 'delete')

        count = core_models.FileError.objects.count()
        self.assertEqual(count, 0)

    def test_delete_log_file_error_more_errors(self):
        file_errors = CoreFactory.FileErrorFactory.create_batch(2, file_name="testfile.csv", mission=self.mission)
        mock_request = HttpRequest()

        count = core_models.FileError.objects.count()
        self.assertEqual(count, 2)

        response = views_mission_event.delete_log_file_error(mock_request, file_errors[0].pk, 'uuid')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Trigger'], 'recount_file_errors')

        # The response should be empty if there are still file errors related to the same file name
        self.assertEqual(response.content, b'')

        count = core_models.FileError.objects.count()
        self.assertEqual(count, 1)

    def test_delete_event_error_no_more_errors(self):
        event = CoreFactory.CTDEventFactory.create(mission=self.mission)
        event_error = CoreFactory.ValidationError.create(event=event)
        mock_request = HttpRequest()

        count = core_models.EventError.objects.count()
        self.assertEqual(count, 1)

        response = views_mission_event.delete_event_error(mock_request, event_error.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Trigger'], 'recount_event_errors')

        # if there are no errors left then a hx-swap-oob: delete attribute should be returned
        # to remove the card from the page
        card = BeautifulSoup(response.content, 'html.parser')
        div = card.find(id=f'div_id_card_event_validation_{event.pk}')
        self.assertIsNotNone(div)
        self.assertEqual(div.attrs['hx-swap-oob'], 'delete')

        count = core_models.EventError.objects.count()
        self.assertEqual(count, 0)

    def test_delete_event_error_more_errors(self):
        event = CoreFactory.CTDEventFactory.create(mission=self.mission)
        event_error = CoreFactory.ValidationError.create_batch(2, event=event)
        mock_request = HttpRequest()

        count = core_models.EventError.objects.count()
        self.assertEqual(count, 2)

        response = views_mission_event.delete_event_error(mock_request, event_error[0].pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Trigger'], 'recount_event_errors')

        # The response should be empty if there are still errors related to the same file name
        self.assertEqual(response.content, b'')

        count = core_models.EventError.objects.count()
        self.assertEqual(count, 1)


@tag('forms', 'view_mission_event', 'form_validation_file_card')
class TestFormValidationFileCard(TestCase):

    def setUp(self):
        self.expected_file_name = "test_file.csv"
        self.expected_UUID = '1'
        self.mission = CoreFactory.MissionFactory(name="TestMission")
        CoreFactory.FileErrorFactory.create_batch(2, file_name=self.expected_file_name, mission=self.mission)
        self.form = views_mission_event.ValidationFileCard(
            mission=self.mission, file_name=self.expected_file_name, uuid=self.expected_UUID
        )
        html = render_crispy_form(self.form)
        self.card = BeautifulSoup(html, 'html.parser')

    def test_initial(self):
        # test that the validation form is properly initialized with card, card_head and card_body ids
        self.assertIsNotNone(self.card)

        card = self.card.find(id=f'div_id_card_file_validation_{self.expected_UUID}')
        self.assertIsNotNone(card)

        card_head = self.card.find(id=f'div_id_card_header_file_validation_{self.expected_UUID}')
        self.assertIsNotNone(card_head)

        card_body = self.card.find(id=f'div_id_card_body_file_validation_{self.expected_UUID}')
        self.assertIsNotNone(card_body)


@tag('forms', 'view_mission_event', 'form_validation_event_card')
class TestFormValidationEventCard(TestCase):

    def setUp(self):
        self.mission = CoreFactory.MissionFactory(name="TestMission")
        self.event = CoreFactory.CTDEventFactory.create(mission=self.mission)
        CoreFactory.ValidationError.create_batch(2, event=self.event)
        self.form = views_mission_event.ValidationEventCard(
            event=self.event,
        )
        html = render_crispy_form(self.form)
        self.card = BeautifulSoup(html, 'html.parser')

    def test_initial(self):
        # test that the validation form is properly initialized with card, card_head and card_body ids
        self.assertIsNotNone(self.card)

        card = self.card.find(id=f'div_id_card_event_validation_{self.event.pk}')
        self.assertIsNotNone(card)

        card_head = self.card.find(id=f'div_id_card_header_event_validation_{self.event.pk}')
        self.assertIsNotNone(card_head)

        card_body = self.card.find(id=f'div_id_card_body_event_validation_{self.event.pk}')
        self.assertIsNotNone(card_body)


@tag('forms', 'view_mission_event', 'event_details')
class TestEventDetailsView(TestCase):

    def setUp(self):
        self.mission = CoreFactory.MissionFactory.create(name="TestMission")
        self.event = CoreFactory.CTDEventFactory.create(mission=self.mission)
        self.url = reverse("core:mission_events_details", args=['default', self.event.pk])

    def test_event_details_view_get(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)