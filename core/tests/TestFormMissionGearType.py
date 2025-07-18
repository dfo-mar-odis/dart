from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.test import tag
from django.urls import reverse

from config.tests.DartTestCase import DartTestCase
from core.form_mission_gear_type import GearTypeFilterForm
from core.tests import CoreFactoryFloor as core_factory

@tag("forms", "mission_gear_type", "form_filter_data_type")
class TestMissionGearTypeFilter(DartTestCase):

    def setUp(self) -> None:
        self.mission_sample_type = core_factory.MissionSampleTypeFactory.create()
        self.form = GearTypeFilterForm(self.mission_sample_type)
        self.expected_url = reverse('core:mission_gear_type_sample_list', args=[self.mission_sample_type.pk])
        context = {
        }

        form_crispy = render_crispy_form(self.form, context=context)
        self.form_soup = BeautifulSoup(form_crispy, 'html.parser')

    def test_initial(self):
        # test that the form was initialized with the title
        title = self.form_soup.find(id=self.form.get_id_builder().get_card_title_id())
        self.assertEqual(title.string, "Sample Type Filter")

    def test_button_clear(self):
        # test that the card header has a button to clear filtered samples
        header = self.form_soup.find(id=self.form.get_id_builder().get_card_header_id())
        input = header.find('button', id=self.form.get_id_builder().get_button_clear_filters_id())
        self.assertIsNotNone(input)

    def test_hidden_mission_sample_type_input(self):
        # test that a hidden input field with the name 'mission_sample_type' exists in the body of the card
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('input', id=self.form.get_id_builder().get_input_hidden_refresh_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'refresh_samples')
        self.assertEqual(attrs['type'], 'hidden')

        # when a datatype, limit or flag is updated this element should make a request to update the visible samples
        self.assertEqual(attrs['hx-target'], f"#{samples_card_id}")
        self.assertEqual(attrs['hx-trigger'], 'reload_samples from:body')
        self.assertEqual(attrs['hx-post'], self.expected_url)
        self.assertEqual(attrs['hx-swap'], 'outerHTML')

    def test_sample_start_input(self):
        # test that an input field with the name 'sample_id_start' exists in the body of the card
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('input', id=self.form.get_id_builder().get_input_sample_id_start_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'sample_id_start')
        self.assertEqual(attrs['type'], 'number')

        # needs some HTMX calls to update the visible samples on the page
        self.assertEqual(attrs['hx-target'], f"#{samples_card_id}")
        self.assertEqual(attrs['hx-trigger'], "keyup changed delay:500ms")
        self.assertEqual(attrs['hx-post'], self.expected_url)
        self.assertEqual(attrs['hx-swap'], 'outerHTML')

    def test_sample_end_input(self):
        # test that an input field with the name 'sample_id_end' exists in the body of the card
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('input', id=self.form.get_id_builder().get_input_sample_id_end_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'sample_id_end')
        self.assertEqual(attrs['type'], 'number')

        # needs some HTMX calls to update the visible samples on the page
        self.assertEqual(attrs['hx-target'], f"#{samples_card_id}")
        self.assertEqual(attrs['hx-trigger'], "keyup changed delay:500ms")
        self.assertEqual(attrs['hx-post'], self.expected_url)
        self.assertEqual(attrs['hx-swap'], 'outerHTML')
