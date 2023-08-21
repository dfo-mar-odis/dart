import os

import bs4
from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form

from django.test import tag, Client
from django.urls import reverse

from render_block import render_block_to_string

import core.models
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

        self.expected_headers = ["Sample", "Bottle#", "O2_Concentration(ml/l)", "O2_Uncertainty(ml/l)",
                                 "Titrant_volume(ml)", "Titrant_uncertainty(ml)", "Analysis_date", "Data_file",
                                 "Standards(ml)", "Blanks(ml)", "Bottle_volume(ml)", "Initial_transmittance(%%)",
                                 "Standard_transmittance0(%%)", "Comments"]
        self.expected_headers = [(h.lower(), h) for h in self.expected_headers]

    def test_form_required_initial_args(self):
        try:
            forms.SampleTypeForm()
            self.fail("An exception should have been raised for missing arguments")
        except KeyError as ex:
            self.assertEquals(ex.args[0]["message"], "missing initial \"file_type\"")

        try:
            forms.SampleTypeForm(initial={})
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

        url = reverse("core:load_sample_type")
        response = self.client.get(url+"?sample_file=''")

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)
        message = soup.find(id="div_id_loaded_sample_type_message")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], url)

        alert = message.find('div')
        self.assertEquals(alert.text, "Loading")

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

    def test_new_blank_loading_msg(self):
        # When the 'add' sample_type button is clicked an alert dialog should be swapped in indicating that a loading
        # operation is taking place, this is a get request so no file is needed. The alert will then call
        # new_sample_type with a post request to retrieve the details
        url = reverse("core:new_sample_type")

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')

        message = soup.find(id="div_id_loaded_sample_type_message")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], reverse("core:new_sample_type"))

        alert = message.find('div')
        self.assertEquals(alert.text, "Loading")

    def test_new_blank_form_no_file(self):
        # When the 'add' sample_type button is clicked if no file has been selected a message should be
        # swapped into the div_id_sample_type tag saying no file has been selected

        url = reverse("core:new_sample_type")

        # anything that requires access to a file will need to be a post method
        response = self.client.post(url, {'sample_file': ''})

        soup = BeautifulSoup(response.content, 'html.parser')

        div = soup.find(id="div_id_sample_type")
        self.assertIsNotNone(div)
        msg_div = div.findChild('div')
        self.assertIsNotNone(msg_div)
        self.assertEquals(msg_div.attrs['class'], ['alert', 'alert-warning', 'mt-2'])
        self.assertEquals(msg_div.string, "File is required before adding sample")

    def test_new_blank_form_with_file(self):
        # When the 'add' sample_type button is clicked if a file has been selected
        # the SampleTypeForm should be swapped into the div_id_sample_type tag
        file_initial = {"file_type": "xlsx", "skip": 9, "tab": 0}
        expected_form = forms.SampleTypeForm(field_choices=self.expected_headers, initial=file_initial)

        expected_form_html = render_crispy_form(expected_form)

        url = reverse("core:new_sample_type")

        # anything that requres accss to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        returned_content = response.content.decode('utf-8')
        self.assertEquals(returned_content, expected_form_html)

    def test_submit_new_sample_type(self):
        # After the form has been filled out and the user clicks the submit button the 'save_sample_type' url
        # should be called with a get request to get the saving alert

        url = reverse("core:save_sample_type")

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)

        message = soup.find(id="div_id_loaded_sample_type_message")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], url)

        alert = message.find('div')
        self.assertEquals(alert.text, "Saving")

    def test_submit_new_sample_type_invalid(self):
        # If a submitted form is invalid the form should be returned with errors

        # required post variables that the form would have previously setup without user input
        file_type = 'xlsx'
        header = 9
        tab = 0
        post_vars = {"file_type": file_type, "skip": header, "tab": tab}
        expected_form = forms.SampleTypeForm(post_vars, field_choices=self.expected_headers)
        expected_form.is_valid()

        expected_form_html = render_crispy_form(expected_form)

        url = reverse("core:save_sample_type")

        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp, "file_type": file_type, "skip": header, "tab": tab,
                                              'mission_id': self.mission.pk})

        self.assertEquals(response.content.decode('utf-8'), str(expected_form_html))

    def test_submit_new_sample_type_valid(self):
        # If a submitted form is valid a div#div_id_loaded_samples_list element should be returned
        # with a HTML forms.SampleTypeLoadForm() to be swapped into the #div_id_loaded_samples_list section
        # of the 'core/partials/form_sample_type.html' template

        # required post variables that the form would have previously setup without user input
        file_type = 'xlsx'
        header = 9
        tab = 0
        priority = 1
        short_name = 'oxy'
        sample_field = 'sample'
        value_field = 'o2_concentration(ml/l)'

        expected_sample_type_load_form_id = f'div_id_{1}'

        url = reverse("core:save_sample_type")

        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp, 'mission_id': self.mission.pk, 'file_type': file_type,
                                              'skip': header, 'tab': tab, 'short_name': short_name,
                                              'priority': priority, 'sample_field': sample_field,
                                              'value_field': value_field, })

        soup = BeautifulSoup(response.content, 'html.parser')
        div_id_loaded_samples_list = soup.find(id="div_id_loaded_samples_list")
        self.assertIsNotNone(div_id_loaded_samples_list)

        sample_type_load_card = div_id_loaded_samples_list.find(id=expected_sample_type_load_form_id)
        self.assertIsNotNone(sample_type_load_card)
        self.assertEquals(len(sample_type_load_card.find_next_siblings()), 0)

    def test_input_file_with_config(self):
        # If a config exists for a selected file it should be presented as a SampleTypeLoadForm in the
        # div_id_loaded_samples_list. This is populated by an out of band select on the file input on the
        # 'core/partials/form_sample_type.html' template. So the 'load_sample_type' method should
        # return an empty 'div_id_sample_type' element to clear the 'loading' alert and the
        # 'div_id_loaded_samples_list' to swap in the list of SampleTypeLoadForms

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        expected = render_crispy_form(forms.SampleTypeLoadForm(instance=oxy_sample_type))
        expected_soup = BeautifulSoup(f'<div id="div_id_loaded_samples_list">{expected}</div>', 'html.parser')

        url = reverse("core:load_sample_type")
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        soup = BeautifulSoup(response.content, 'html.parser')
        samples_type = soup.find(id='div_id_sample_type')
        self.assertIsNotNone(samples_type)
        self.assertIsNone(samples_type.string)

        list_div = soup.find(id=f'div_id_loaded_samples_list').find('div')
        self.assertIsNotNone(list_div)

        self.assertEquals(len(list_div.find_next_siblings()), 0)

    def test_edit_sample_type(self):
        # if the new_sample_type url contains an argument with a 'sample_type' id the form should load with the
        # existing config.

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:new_sample_type", args=(oxy_sample_type.pk,))

        expected_form = forms.SampleTypeForm(instance=oxy_sample_type, field_choices=self.expected_headers)

        expected_form_html = render_crispy_form(expected_form)

        # anything that requres accss to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        returned_content = response.content.decode('utf-8')
        self.assertEquals(returned_content, expected_form_html)

    def test_edit_sample_type_update_message(self):
        # if the new_sample_type url contains an argument with a 'sample_type' id the form should load with the
        # existing config.

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:save_sample_type", args=(oxy_sample_type.pk,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)

        message = soup.find(id="div_id_loaded_sample_type_message")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], url)

        alert = message.find('div')
        self.assertEquals(alert.text, "Saving")

    def test_edit_sample_type_update(self):
        # if the new_sample_type url contains an argument with a 'sample_type' id the form should load with the
        # existing config.

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:save_sample_type", args=(oxy_sample_type.pk,))

        # anything that requres accss to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url,
                                        {'sample_file': fp, 'mission_id': self.mission.pk,
                                         'file_type': oxy_sample_type.file_type,
                                         'skip': oxy_sample_type.skip, 'tab': oxy_sample_type.tab,
                                         'short_name': 'oxy2',
                                         'priority': oxy_sample_type.priority,
                                         'sample_field': oxy_sample_type.sample_field,
                                         'value_field': oxy_sample_type.value_field, })


        sample_type = core.models.SampleType.objects.get(pk=oxy_sample_type.pk)
        self.assertEquals(sample_type.short_name, 'oxy2')

    def test_load_samples(self):
        # clicking the load button should add a loading alert to the SampleTypeLoadForm message area
        # to indicate that the file is being loaded.

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:load_samples", args=(oxy_sample_type.pk,))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)

        message = soup.find(id=f"div_id_loading_div_id_{oxy_sample_type.pk}")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], url)

        alert = message.find('div')
        self.assertEquals(alert.text, "Loading")

    def test_load_samples_with_errors(self):
        # once the loading alert has become active the load_samples post is called with the file
        # in this case no bottles have been loaded so there should be a bunch of missing bottle file errors
        # that should be posted in the SampleTypeLoadForm's message area, and the folder icon should
        # appear with the btn-warning class on it

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        message_div_id = f'div_id_{oxy_sample_type.pk}'
        url = reverse("core:load_samples", args=(oxy_sample_type.pk,))

        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp, 'mission_id': self.mission.pk})

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)

        button = soup.find(id=f"{message_div_id}_load_button")

        self.assertIsNotNone(button)
        self.assertIn('btn-warning', button.attrs['class'])

        errors = soup.find(id=f"{message_div_id}_message")

        self.assertIsNotNone(errors)
