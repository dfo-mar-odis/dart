from bs4 import BeautifulSoup
from django.template.loader import render_to_string
from django.test import tag, Client
from django.urls import reverse

from core.form_mission_sample_type import BioChemDataType
from dart.tests.DartTestCase import DartTestCase

from core.tests import CoreFactoryFloor as core_factory
from core import models as core_models


class AbstractTestMissionSampleType(DartTestCase):

    def setUp(self) -> None:
        self.mission_sample_type = core_factory.MissionSampleTypeFactory()

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

        biochem_data_type_form = BioChemDataType('default', self.mission_sample_type)
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
        self.assertEquals(int(start_input.attrs['value']), self.start_bottle)

        end_input = soup.find(id="id_end_sample")
        self.assertIsNotNone(end_input)
        self.assertEquals(int(end_input.attrs['value']), self.end_bottle)

    @tag("template_mission_sample_type_test_initial_template_delete_btn")
    def test_initial_template_delete_btn(self):
        # the delete sample type button should point to the delete url in the Form_mission_sample_type module
        # it should have an hx-confirm on it to make sure the user isn't accidentally deleting the sample type
        biochem_data_type_form = BioChemDataType('default', self.mission_sample_type)
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


@tag("forms", "mission_sample_type", "form_biochem_data_type")
class TestFormBioChemDataType(AbstractTestMissionSampleType):

    @tag("form_biochem_data_type_test_default")
    def test_default(self):
        # provided a database and the mission_sample_type the BioChemDataType form should
        # set the default values on the form for the biochem data type, and start/end bottle ids

        biochem_data_type_form = BioChemDataType('default', self.mission_sample_type)

        self.assertEquals(biochem_data_type_form.fields['start_sample'].initial, self.start_bottle)
        self.assertEquals(biochem_data_type_form.fields['end_sample'].initial, self.end_bottle)
        self.assertEquals(biochem_data_type_form.fields['data_type_description'].initial,
                          self.mission_sample_type.datatype.pk)

        self.assertEquals(biochem_data_type_form.fields['data_type_code'].initial,
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
        biochem_data_type_form = BioChemDataType('default', self.mission_sample_type, initial=initial)

        self.assertEquals(biochem_data_type_form.fields['start_sample'].initial, initial['start_sample'])
        self.assertEquals(biochem_data_type_form.fields['end_sample'].initial, initial['end_sample'])
        self.assertEquals(biochem_data_type_form.fields['data_type_description'].initial, initial['data_type_code'])
        self.assertEquals(biochem_data_type_form.fields['data_type_code'].initial, initial['data_type_code'])


@tag("forms", "mission_sample_type", "form_mission_sample_type")
class TestFormMissionSampleType(AbstractTestMissionSampleType):

    def setUp(self) -> None:
        super().setUp()
        self.client = Client()

    @tag("form_mission_sample_type_test_entry_point")
    def test_entry_point(self):
        # a database and sample type a get request should return the initial sample type page
        url = reverse("core:mission_sample_type_details", args=('default', self.mission_sample_type.pk,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")
        self.assertIsNotNone(soup)

        # The page consists of two main portions. The top is the sample type form to apply a Biochem datatype to a
        # mission sample type. The bottom portion of the page consists of a table showing the data table for the
        # selected mission sample type

        form = soup.find(id="div_id_sample_filter")
        self.assertIsNotNone(form)

        # the data gets loaded after the page load so this is just going to be an empty place holder
        # with hx-get=url and hx-trigger='load' attributes
        table_card = soup.find(id="div_id_data_display")
        self.assertIsNotNone(table_card)

        url = reverse("core:mission_sample_type_card", args=('default', self.mission_sample_type.pk))
        self.assertIn('hx-get', table_card.attrs)
        self.assertEquals(table_card.attrs['hx-get'], url)

        self.assertIn('hx-trigger', table_card.attrs)
        self.assertEquals(table_card.attrs['hx-trigger'], 'load')

    @tag("form_mission_sample_type_test_set_row_sample_type_get")
    def test_set_row_sample_type_get(self):
        # give a database and a mission_sample_type id, calling the set row url as a get request should
        # return a save/load alert that contains an hx-post url calling the same url on hx-trigger='load'

        url = reverse("core:form_mission_sample_type_set_row", args=('default', self.mission_sample_type.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        alert = soup.find(id="div_id_data_type_message")
        self.assertIsNotNone(alert)
        self.assertIn('hx-swap-oob', alert.attrs)
        self.assertEquals(alert.attrs['hx-swap-oob'], 'true')

        alert = soup.find(id="div_id_data_type_message_alert")
        self.assertIsNotNone(alert)
        self.assertIn('hx-post', alert.attrs)
        self.assertEquals(alert['hx-post'], url)

    @tag("form_mission_sample_type_test_set_row_sample_type_post")
    def test_set_row_sample_type_post(self):
        # given a database and a mission_sample_type id, calling the set row url as a post request,
        # with a data_type_code should set the BioChem data type for the rows specified by the start - end sample ids

        post_vars = {
            'start_sample': self.start_bottle + 1,
            'end_sample': self.end_bottle - 1,
            'data_type_code': 90000001
        }

        url = reverse("core:form_mission_sample_type_set_row", args=('default', self.mission_sample_type.pk))
        response = self.client.post(url, post_vars)

        # the start and end bottles should be unchanged, they should be none, because the mission_sample_type.data_type
        # will be used for them for the BioChem upload
        start_sample = core_models.DiscreteSampleValue.objects.using('default').get(
            sample__bottle__bottle_id=self.start_bottle)
        self.assertEquals(start_sample.datatype, None)

        end_sample = core_models.DiscreteSampleValue.objects.using('default').get(
            sample__bottle__bottle_id=self.end_bottle)
        self.assertEquals(end_sample.datatype, None)

        start_sample = core_models.DiscreteSampleValue.objects.using('default').get(
            sample__bottle__bottle_id=post_vars['start_sample'])
        self.assertEquals(start_sample.datatype.pk, post_vars['data_type_code'])

        end_sample = core_models.DiscreteSampleValue.objects.using('default').get(
            sample__bottle__bottle_id=post_vars['end_sample'])
        self.assertEquals(end_sample.datatype.pk, post_vars['data_type_code'])

        # the function call itself should return a reloaded sample list
        soup = BeautifulSoup(response.content, 'html.parser')
        soup.find(id="div_id_sample_type_details")

    @tag("form_mission_sample_type_test_set_mission_sample_type_get")
    def test_set_mission_sample_type_get(self):
        # give a database and a mission_sample_type id, calling the set mission url as a get request should
        # return a save/load alert that contains an hx-post url calling the same url on hx-trigger='load'

        url = reverse("core:form_mission_sample_type_set_mission", args=('default', self.mission_sample_type.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        alert = soup.find(id="div_id_data_type_message")
        self.assertIsNotNone(alert)
        self.assertIn('hx-swap-oob', alert.attrs)
        self.assertEquals(alert.attrs['hx-swap-oob'], 'true')

        alert = soup.find(id="div_id_data_type_message_alert")
        self.assertIsNotNone(alert)
        self.assertIn('hx-post', alert.attrs)
        self.assertEquals(alert['hx-post'], url)

    @tag("form_mission_sample_type_test_set_mission_sample_type_post")
    def test_set_mission_sample_type_post(self):
        # given a database and a mission_sample_type id, calling the set mission url as a get request,
        # with a data_type_code should set the BioChem data type for the mission_sample_type

        post_vars = {
            'data_type_code': 90000001
        }

        url = reverse("core:form_mission_sample_type_set_mission", args=('default', self.mission_sample_type.pk))
        response = self.client.post(url, post_vars)

        sample_type = core_models.MissionSampleType.objects.using('default').get(pk=self.mission_sample_type.pk)
        self.assertEquals(sample_type.datatype.pk, post_vars['data_type_code'])

        # the function call itself should return a reloaded sample list
        soup = BeautifulSoup(response.content, 'html.parser')
        soup.find(id="div_id_sample_type_details")

    @tag("form_mission_sample_type_test_delete_sample_type_get")
    def test_delete_sample_type_get(self):
        # provided a database and a mission_sample_type id, this get request should return a save/load alert
        # with hx-post=url and hx-trigger='load'
        url = reverse("core:form_mission_sample_type_delete", args=('default', self.mission_sample_type.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        alert = soup.find(id="div_id_data_type_message")
        self.assertIsNotNone(alert)
        self.assertIn('hx-swap-oob', alert.attrs)
        self.assertEquals(alert.attrs['hx-swap-oob'], 'true')

        alert = soup.find(id="div_id_data_type_message_alert")
        self.assertIsNotNone(alert)
        self.assertIn('hx-post', alert.attrs)
        self.assertEquals(alert['hx-post'], url)

    @tag("form_mission_sample_type_test_delete_sample_type_post")
    def test_delete_sample_type_post(self):
        # provided a database and a mission_sample_type id, this post request should remove the samples and
        # mission_sample_type associated with the mission_sample_type id and then return the user to the
        # All sample view (A.K.A view_mission_sample.py) using an HX-Redirect
        expected_redirect = reverse("core:mission_samples_sample_details",
                                    args=('default', self.mission_sample_type.mission.pk))
        url = reverse("core:form_mission_sample_type_delete", args=('default', self.mission_sample_type.pk))
        response = self.client.post(url)

        samples = core_models.Sample.objects.using('default').filter(type=self.mission_sample_type)
        self.assertFalse(samples.exists())

        sample_type = core_models.MissionSampleType.objects.using('default').filter(pk=self.mission_sample_type.pk)
        self.assertFalse(sample_type.exists())

        self.assertIn('Hx-Redirect', response.headers)
        self.assertEquals(expected_redirect, response.headers['Hx-Redirect'])
