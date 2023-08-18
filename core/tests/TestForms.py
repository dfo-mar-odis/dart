import os

import bs4
from bs4 import BeautifulSoup

from django.test import tag, Client
from django.urls import reverse

from render_block import render_block_to_string

from dart2 import settings
from dart2.tests.DartTestCase import DartTestCase

from core import forms
from core.tests import CoreFactoryFloor as core_factory

import logging

logger = logging.getLogger("dart.test")


@tag('forms', 'form_sample_config')
class TestSampleFileConfiguration(DartTestCase):

    def setUp(self) -> None:
        self.client = Client()
        self.mission = core_factory.MissionFactory()
        self.sample_oxy_xlsx_file = os.path.join(settings.BASE_DIR, 'core/tests/sample_data/sample_oxy.xlsx')
        # if field choices are supplied the sample, value, flag and replicate fields should all be selection fields
        self.field_choices = [(i, f"Choice ({i})") for i in range(10)]

    def test_form_required_initial_args(self):
        try:
            forms.SampleFileConfigurationForm()
            self.fail("An exception should have been raised for missing arguments")
        except KeyError as ex:
            self.assertEquals(ex.args[0]["message"], "missing initial \"file_type\"")

        try:
            forms.SampleFileConfigurationForm(initial={})
            self.fail("An exception should have been raised for missing arguments")
        except KeyError as ex:
            self.assertEquals(ex.args[0]["message"], "missing initial \"file_type\"")

    def test_form_exists(self):
        url = reverse("core:load_sample_type") + f"?mission={self.mission.pk}"
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)
        form = soup.find(id="id_form_load_samples")

        self.assertIsNotNone(form)

        # the form should consist of the hidden mission_id, a row containing the input field
        # a div_id_sample_type object for messages (empty) and a div_id_loaded_sample_type object
        # for loaded configurations (empty
        elm: bs4.Tag = form.findChildren()[0]
        self.assertEquals(elm.attrs['name'], 'mission_id')
        self.assertEquals(elm.attrs['value'], str(self.mission.pk))

        elm = elm.find_next_sibling()
        self.assertEquals(elm.attrs['class'], ['row'])

        elm = elm.find_next_sibling()
        self.assertEquals(elm.attrs['id'], 'div_id_sample_type')

        elm = elm.find_next_sibling()
        self.assertEquals(elm.attrs['id'], 'div_id_loaded_sample_type')

    def test_input_field(self):
        # first action is for a user to choose a file, which should send back an 'alert alert-info' element
        # stating that loading is taking place and will post the file to the 'load_sample_type' url

        url = reverse("core:load_sample_type") + "?sample_file=''"
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)
        message = soup.find(id="div_id_loaded_sample_type_message")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], reverse("core:load_sample_type"))

        alert = message.find('div')
        self.assertEquals(alert.string, "Loading")

    def test_input_file_no_config(self):
        # provided a file, if no configs are available the div_id_sample_type
        # tag should contain a message that no configs were found

        url = reverse("core:load_sample_type")
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        soup = BeautifulSoup(response.content, 'html.parser')
        samples_list = soup.find(id='div_id_sample_type')
        msg_div = samples_list.findChild('div')

        self.assertIsNotNone(msg_div)
        self.assertEquals(msg_div.attrs['class'], ['alert', 'alert-warning', 'mt-2'])
        self.assertEquals(msg_div.string, "No File Configurations Found")

    def test_input_file_with_config(self):
        # provided a file, if a config is available a card with an id like 'id_oxy_1' should be returned
        # with a blank div_id_sample_type. The div_id_sample_type is used to clear the message/new sampletype form
        # the id_oxy_1 card will be swapped into the div_id_loaded_sample_type_list

        oxy_sample_type = core_factory.SampleTypeFactory(short_name="oxy", long_name="Oxygen")
        oxy_file_config = core_factory.SampleFileSettingsFactory(
            sample_type=oxy_sample_type,
            header=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx'
        )

        url = reverse("core:load_sample_type")
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        soup = BeautifulSoup(response.content, 'html.parser')
        samples_type = soup.find(id='div_id_sample_type')
        self.assertIsNotNone(samples_type)
        self.assertIsNone(samples_type.string)

        msg_div = soup.find(id=f'div_id_oxy_{oxy_file_config.pk}')
        self.assertIsNotNone(msg_div)

    def test_new_blank_form_no_file(self):
        # When the 'add' sample_type button is clicked if no file has been selected a message should be
        # swapped into the div_id_sample_type tag saying no file has been selected

        url = reverse("core:new_sample_type")

        # anything that requres accss to a file will need to be a post method
        response = self.client.post(url, {'sample_file': ''})

        soup = BeautifulSoup(response.content, 'html.parser')

        div = soup.find(id="div_id_sample_type")
        self.assertIsNotNone(div)
        msg_div = div.findChild('div')
        self.assertIsNotNone(msg_div)
        self.assertEquals(msg_div.attrs['class'], ['alert', 'alert-warning', 'mt-2'])
        self.assertEquals(msg_div.string, "File is required before adding sample")

    def test_new_blank_form_with_file(self):
        # When the 'add' sample_type button is clicked if no file has been selected a message should be
        # swapped into the div_id_sample_type tag saying no file has been selected

        url = reverse("core:new_sample_type")

        # anything that requres accss to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        soup = BeautifulSoup(response.content, 'html.parser')

        div = soup.find(id="div_id_sample_type")
        self.assertIsNotNone(div)
        msg_div = div.findChild('div')
        self.assertIsNotNone(msg_div)
        self.assertEquals(msg_div.attrs['id'], 'div_id_sample_type_form')

        # I'm only going to test the one field for now to make sure it's blank, might do more later
        input = div.find(id="id_short_name")
        self.assertNotIn('value', input.attrs)

    def test_new_with_config_with_file(self):
        # if the new_sample_type url contains an argument with 'config' the form should load with the
        # existing config. This is called via the load_sample_type url

        oxy_sample_type = core_factory.SampleTypeFactory(short_name="oxy", long_name="Oxygen")
        oxy_file_config = core_factory.SampleFileSettingsFactory(
            sample_type=oxy_sample_type,
            header=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx'
        )
        url = reverse("core:load_sample_type", args=(oxy_file_config.pk,))

        # anything that requres accss to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        soup = BeautifulSoup(response.content, 'html.parser')

        div = soup.find(id="div_id_sample_type")
        self.assertIsNotNone(div)
        msg_div = div.findChild('div')
        self.assertIsNotNone(msg_div)
        self.assertEquals(msg_div.attrs['id'], 'div_id_sample_type_form')

        # I'm only going to test the one field for now to make sure it's blank, might do more later
        input = div.find(id="id_short_name")
        self.assertIn('value', input.attrs)
        self.assertEquals(input.attrs['value'], oxy_file_config.sample_type.short_name)
