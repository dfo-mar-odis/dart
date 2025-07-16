from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.template.loader import render_to_string
from django.test import tag, Client
from django.urls import reverse

from core.form_mission_sample_type import BioChemDataType, MissionSampleTypeFilter
from config.tests.DartTestCase import DartTestCase

from core.tests import CoreFactoryFloor as core_factory
from core import models as core_models


class AbstractTestMissionSampleType(DartTestCase):

    def setUp(self) -> None:
        self.mission_sample_type = core_factory.MissionSampleTypeFactory.create()

        event = core_factory.CTDEventFactory(mission=self.mission_sample_type.mission)

        number_of_bottles = 20
        self.start_bottle = 400000
        self.end_bottle = self.start_bottle + (number_of_bottles - 1)  # -1 because the first bottle is zero

        core_factory.BottleFactory.reset_sequence(self.start_bottle)
        self.bottles = core_factory.BottleFactory.create_batch(number_of_bottles, event=event)

        self.samples = {}
        for bottle in self.bottles:
            self.samples[bottle.bottle_id] = core_factory.SampleFactory(bottle=bottle, type=self.mission_sample_type)
            core_factory.DiscreteValueFactory(sample=self.samples[bottle.bottle_id])


@tag("templates", "mission_sample_type", "template_mission_sample_type")
class TestTemplateMissionSampleType(AbstractTestMissionSampleType):

    def setUp(self) -> None:
        super().setUp()
        self.template = "core/mission_sample_type.html"

    @tag("template_mission_sample_type_test_initial_template")
    def test_initial_template(self):

        biochem_data_type_form = BioChemDataType(self.mission_sample_type)
        context = {
            'database': 'default',
            'mission_sample_type': self.mission_sample_type,
            'biochem_form': biochem_data_type_form
        }

        html = render_to_string(self.template, context)
        soup = BeautifulSoup(html, "html.parser")

        # initially the start and end bottle should be filled in
        start_input = soup.find(id="id_start_sample")
        self.assertIsNotNone(start_input)
        self.assertEqual(int(start_input.attrs['value']), self.start_bottle)

        end_input = soup.find(id="id_end_sample")
        self.assertIsNotNone(end_input)
        self.assertEqual(int(end_input.attrs['value']), self.end_bottle)

    # Todo: The delete button was removed from the Datatype form and will be placed on the filter form
    @tag("template_mission_sample_type_test_initial_template_delete_btn")
    def test_initial_template_delete_btn(self):
        # the delete sample type button should point to the delete url in the Form_mission_sample_type module
        # it should have an hx-confirm on it to make sure the user isn't accidentally deleting the sample type
        biochem_data_type_form = BioChemDataType(self.mission_sample_type)
        context = {
            'database': 'default',
            'mission_sample_type': self.mission_sample_type,
            'biochem_form': biochem_data_type_form
        }

        html = render_to_string(self.template, context)
        soup = BeautifulSoup(html, "html.parser")

        delete_btn = soup.find('button', attrs={'name': "delete"})
        self.assertIsNotNone(delete_btn)
        self.assertIn('hx-confirm', delete_btn.attrs)


@tag("forms", "mission_sample_type", "form_filter_data_type")
class TestMissionSampleTypeFilter(DartTestCase):

    def setUp(self) -> None:
        self.mission_sample_type = core_factory.MissionSampleTypeFactory.create()
        self.form = MissionSampleTypeFilter(self.mission_sample_type)
        self.expected_url = reverse('core:mission_sample_type_sample_list', args=[self.mission_sample_type.pk])
        context = {
        }

        form_crispy = render_crispy_form(self.form, context=context)
        self.form_soup = BeautifulSoup(form_crispy, 'html.parser')

    def test_initial(self):
        # test that the form was initialized with the title
        title = self.form_soup.find(id="div_id_card_title_missing_sample_type_filter").findChildren()[0]
        self.assertEqual(title.string, "Sample Type Filter")

    def test_button_delete(self):
        # test that the card header has a button to delete filtered samples
        header = self.form_soup.find(id="div_id_card_header_missing_sample_type_filter")
        input = header.find('button', id='btn_id_delete_mission_samples')
        self.assertIsNotNone(input)

    def test_hidden_mission_sample_type_input(self):
        # test that a hidden input field with the name 'mission_sample_type' exists in the body of the card
        body = self.form_soup.find(id="div_id_card_body_missing_sample_type_filter")
        input = body.find('input', id='input_id_mission_sample_type')
        self.assertIsNotNone(input)
        self.assertEqual(input.attrs['name'], 'mission_sample_type')
        self.assertEqual(input.attrs['type'], 'hidden')
        self.assertEqual(input.attrs['value'], str(self.mission_sample_type.pk))

    def test_sample_start_input(self):
        # test that an input field with the name 'sample_id_start' exists in the body of the card
        body = self.form_soup.find(id="div_id_card_body_missing_sample_type_filter")
        input = body.find('input', id='input_id_sample_id_start')
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'sample_id_start')
        self.assertEqual(attrs['type'], 'number')

        # needs some HTMX calls to update the visible samples on the page
        self.assertEqual(attrs['hx-target'], "#div_id_card_mission_sample_type_samples")
        self.assertEqual(attrs['hx-post'], self.expected_url)
        self.assertEqual(attrs['hx-swap'], 'outerHTML')

    def test_sample_end_input(self):
        # test that an input field with the name 'sample_id_end' exists in the body of the card
        body = self.form_soup.find(id="div_id_card_body_missing_sample_type_filter")
        input = body.find('input', id='input_id_sample_id_end')
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'sample_id_end')
        self.assertEqual(attrs['type'], 'number')

        # needs some HTMX calls to update the visible samples on the page
        self.assertEqual(attrs['hx-target'], "#div_id_card_mission_sample_type_samples")
        self.assertEqual(attrs['hx-post'], self.expected_url)
        self.assertEqual(attrs['hx-swap'], 'outerHTML')


@tag("forms", "mission_sample_type", "form_biochem_data_type")
class TestFormBioChemDataType(AbstractTestMissionSampleType):

    @tag("form_biochem_data_type_test_default")
    def test_default(self):
        # provided a database and the mission_sample_type the BioChemDataType form should
        # set the default values on the form for the biochem data type, and start/end bottle ids

        biochem_data_type_form = BioChemDataType(self.mission_sample_type)

        self.assertEqual(biochem_data_type_form.fields['start_sample'].initial, self.start_bottle)
        self.assertEqual(biochem_data_type_form.fields['end_sample'].initial, self.end_bottle)
        self.assertEqual(biochem_data_type_form.fields['data_type_description'].initial,
                          self.mission_sample_type.datatype.pk)

        self.assertEqual(biochem_data_type_form.fields['data_type_code'].initial,
                          self.mission_sample_type.datatype.pk)

    @tag("form_biochem_data_type_test_initial")
    def test_initial(self):
        # provided a database and the mission_sample_type, and initial values, the BioChemDataType form should
        # set the initial values on the form for the biochem data type, and start/end bottle ids

        initial = {
            'start_sample': (self.start_bottle + 2),
            'end_sample': (self.end_bottle - 2),
            'data_type_code': 90000000
        }
        biochem_data_type_form = BioChemDataType(self.mission_sample_type, initial=initial)

        self.assertEqual(biochem_data_type_form.fields['start_sample'].initial, initial['start_sample'])
        self.assertEqual(biochem_data_type_form.fields['end_sample'].initial, initial['end_sample'])
        self.assertEqual(biochem_data_type_form.fields['data_type_description'].initial, initial['data_type_code'])
        self.assertEqual(biochem_data_type_form.fields['data_type_code'].initial, initial['data_type_code'])


@tag("forms", "mission_sample_type", "form_mission_sample_type")
class TestFormMissionSampleType(AbstractTestMissionSampleType):

    def setUp(self) -> None:
        super().setUp()
        self.client = Client()

    # Todo: This test needs to be rewritten. The sample type page will now have three sections. The top will be a
    #       filter form allowing the user to filter samples for a provided mission sample type in multiple ways.
    #       The middle section will be a form that allows the user to apply a biochem datatype. The bottom
    #       section will be a table displaying samples based on the filter form criteria.
    @tag("form_mission_sample_type_test_entry_point")
    def test_entry_point(self):
        # a database and sample type a get request should return the initial sample type page
        url = reverse("core:mission_sample_type_details", args=('default', self.mission_sample_type.pk,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")
        self.assertIsNotNone(soup)

        # The page consists of three main portions.
        # The top is a sample type filter form used to manipulate what samples certian actions are preformed on.
        # The middle is the sample type form to apply a Biochem datatype to a mission sample type.
        # The bottom portion is a table showing the data filtered from the sample type filter.

        data_type_form = soup.find(id="div_id_card_mission_sample_type_filter")
        self.assertIsNotNone(data_type_form)

        data_type_form = soup.find(id="div_id_card_collapse_biochem_data_type_form")
        self.assertIsNotNone(data_type_form)

        # the data gets loaded after the page load so this is just going to be an empty placeholder
        # with hx-get=url and hx-trigger='load' attributes
        table_card = soup.find(id="table_id_sample_table")
        self.assertIsNotNone(table_card)

        url = reverse("core:mission_sample_type_card", args=(self.mission_sample_type.pk,))
        self.assertIn('hx-get', table_card.attrs)
        self.assertEqual(table_card.attrs['hx-get'], url)

        self.assertIn('hx-trigger', table_card.attrs)
        self.assertEqual(table_card.attrs['hx-trigger'], 'load')

    @tag("form_mission_sample_type_test_set_row_sample_type_get")
    def test_set_row_sample_type_get(self):
        # give a database and a mission_sample_type id, calling the set row url as a get request should
        # return a save/load alert that contains an hx-post url calling the same url on hx-trigger='load'

        url = reverse("core:form_mission_sample_type_set_row", args=(self.mission_sample_type.pk,))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        alert = soup.find(id="div_id_data_type_message")
        self.assertIsNotNone(alert)
        self.assertIn('hx-swap-oob', alert.attrs)
        self.assertEqual(alert.attrs['hx-swap-oob'], 'true')

        alert = soup.find(id="div_id_data_type_message_alert")
        self.assertIsNotNone(alert)
        self.assertIn('hx-post', alert.attrs)
        self.assertEqual(alert['hx-post'], url)

    @tag("form_mission_sample_type_test_set_row_sample_type_post")
    def test_set_row_sample_type_post(self):
        # given a database and a mission_sample_type id, calling the set row url as a post request,
        # with a data_type_code should set the BioChem data type for the rows specified by the start - end sample ids

        post_vars = {
            'start_sample': self.start_bottle + 1,
            'end_sample': self.end_bottle - 1,
            'data_type_code': 90000001
        }

        url = reverse("core:form_mission_sample_type_set_row", args=(self.mission_sample_type.pk,))
        response = self.client.post(url, post_vars)

        # the start and end bottles should be unchanged, they should be none, because the mission_sample_type.data_type
        # will be used for them for the BioChem upload
        start_sample = core_models.DiscreteSampleValue.objects.get(
            sample__bottle__bottle_id=self.start_bottle)
        self.assertEqual(start_sample.datatype, None)

        end_sample = core_models.DiscreteSampleValue.objects.get(
            sample__bottle__bottle_id=self.end_bottle)
        self.assertEqual(end_sample.datatype, None)

        start_sample = core_models.DiscreteSampleValue.objects.get(
            sample__bottle__bottle_id=post_vars['start_sample'])
        self.assertEqual(start_sample.datatype.pk, post_vars['data_type_code'])

        end_sample = core_models.DiscreteSampleValue.objects.get(
            sample__bottle__bottle_id=post_vars['end_sample'])
        self.assertEqual(end_sample.datatype.pk, post_vars['data_type_code'])

        # the function call itself should return a reloaded sample list
        soup = BeautifulSoup(response.content, 'html.parser')
        soup.find(id="div_id_sample_type_details")

    @tag("form_mission_sample_type_test_set_mission_sample_type_get")
    def test_set_mission_sample_type_get(self):
        # give a database and a mission_sample_type id, calling the set mission url as a get request should
        # return a save/load alert that contains an hx-post url calling the same url on hx-trigger='load'

        url = reverse("core:form_mission_sample_type_set_mission", args=(self.mission_sample_type.pk,))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        alert = soup.find(id="div_id_data_type_message")
        self.assertIsNotNone(alert)
        self.assertIn('hx-swap-oob', alert.attrs)
        self.assertEqual(alert.attrs['hx-swap-oob'], 'true')

        alert = soup.find(id="div_id_data_type_message_alert")
        self.assertIsNotNone(alert)
        self.assertIn('hx-post', alert.attrs)
        self.assertEqual(alert['hx-post'], url)

    @tag("form_mission_sample_type_test_set_mission_sample_type_post")
    def test_set_mission_sample_type_post(self):
        # given a database and a mission_sample_type id, calling the set mission url as a get request,
        # with a data_type_code should set the BioChem data type for the mission_sample_type

        post_vars = {
            'data_type_code': 90000001
        }

        url = reverse("core:form_mission_sample_type_set_mission", args=(self.mission_sample_type.pk,))
        response = self.client.post(url, post_vars)

        sample_type = core_models.MissionSampleType.objects.get(pk=self.mission_sample_type.pk)
        self.assertEqual(sample_type.datatype.pk, post_vars['data_type_code'])

        # the function call itself should return a reloaded sample list
        soup = BeautifulSoup(response.content, 'html.parser')
        soup.find(id="div_id_sample_type_details")

    @tag("form_mission_sample_type_test_delete_sample_type_get")
    def test_delete_sample_type_get(self):
        # provided a database and a mission_sample_type id, this get request should return a save/load alert
        # with hx-post=url and hx-trigger='load'
        url = reverse("core:form_mission_sample_type_delete", args=(self.mission_sample_type.pk,))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        alert = soup.find(id="div_id_data_type_message")
        self.assertIsNotNone(alert)
        self.assertIn('hx-swap-oob', alert.attrs)
        self.assertEqual(alert.attrs['hx-swap-oob'], 'true')

        alert = soup.find(id="div_id_data_type_message_alert")
        self.assertIsNotNone(alert)
        self.assertIn('hx-post', alert.attrs)
        self.assertEqual(alert['hx-post'], url)

    @tag("form_mission_sample_type_test_delete_sample_type_post")
    def test_delete_sample_type_post(self):
        # provided a database and a mission_sample_type id, this post request should remove the samples and
        # mission_sample_type associated with the mission_sample_type id and then return the user to the
        # All sample view (A.K.A view_mission_sample.py) using an HX-Redirect
        expected_redirect = reverse("core:mission_samples_sample_details",
                                    args=('default', self.mission_sample_type.mission.pk))
        url = reverse("core:form_mission_sample_type_delete", args=(self.mission_sample_type.pk,))
        response = self.client.post(url)

        samples = core_models.Sample.objects.filter(type=self.mission_sample_type)
        self.assertFalse(samples.exists())

        sample_type = core_models.MissionSampleType.objects.filter(pk=self.mission_sample_type.pk)
        self.assertFalse(sample_type.exists())

        self.assertIn('Hx-Redirect', response.headers)
        self.assertEqual(expected_redirect, response.headers['Hx-Redirect'])
