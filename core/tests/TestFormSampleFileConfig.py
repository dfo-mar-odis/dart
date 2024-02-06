import os

import bs4
from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.template.loader import render_to_string
from django.test import tag, Client
from django.urls import reverse

from core import form_sample_type_config
from core import forms
from core.tests import CoreFactoryFloor as core_factory
from core.tests.TestForms import logger

from dart2 import settings
from dart2.tests.DartTestCase import DartTestCase

from settingsdb import models as settings_models
from settingsdb.tests import SettingsFactoryFloor as settings_factory


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

    @tag('form_sample_config_test_form_exists')
    def test_form_exists(self):
        url = reverse("core:form_sample_config_load", args=('default',)) + f"?mission={self.mission.pk}"
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)
        form = soup.find(id="id_form_load_samples")

        self.assertIsNotNone(form)

        # the form should consist of the hidden mission_id, a row containing the input field
        # a div_id_sample_type_holder object for messages (empty) and a div_id_loaded_sample_type object
        # for loaded configurations (empty
        elm: bs4.Tag = form.findChildren()[0]
        self.assertEquals(elm.attrs['name'], 'mission_id')
        self.assertEquals(elm.attrs['value'], str(self.mission.pk))

        elm = elm.find_next_sibling()
        self.assertEquals(elm.attrs['class'], ['row'])

        elm = elm.find_next_sibling()
        self.assertEquals(elm.attrs['id'], 'div_id_sample_type_holder')

        elm = elm.find_next_sibling()
        self.assertEquals(elm.attrs['id'], 'div_id_loaded_sample_type')

    def test_input_field(self):
        # first action is for a user to choose a file, which should send back an 'alert alert-info' element
        # stating that loading is taking place and will post the file to the 'load_sample_config' url

        url = reverse("core:form_sample_config_load", args=('default',))
        response = self.client.get(url + "?sample_file=''")

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)
        message = soup.find(id="div_id_loaded_sample_type_message")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], url)

        alert = message.find('div')
        self.assertEquals(alert.text, "Loading")

    def test_input_file_no_config(self):
        # provided a file, if no configs are available the div_id_sample_type_holder
        # tag should contain a message that no configs were found and an empty div_id_loaded_samples_list

        url = reverse("core:form_sample_config_load", args=('default',))
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp, 'mission_id': self.mission.pk})

        soup = BeautifulSoup(response.content, 'html.parser')
        samples_list = soup.find(id='div_id_loaded_samples_alert')
        msg_div = samples_list.findChild('div')

        self.assertIsNotNone(msg_div)
        self.assertEquals(msg_div.attrs['class'], ['alert', 'alert-info', 'mt-2'])
        self.assertEquals(msg_div.string, "No File Configurations Found")

    def test_new_blank_loading_msg(self):
        # When the 'add' sample_type button is clicked an alert dialog should be swapped in indicating that a loading
        # operation is taking place, this is a get request so no file is needed. The alert will then call
        # new_sample_config with a post request to retrieve the details
        url = reverse("core:form_sample_config_new", args=('default',))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')

        message = soup.find(id="div_id_loaded_sample_type_message")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], reverse("core:form_sample_config_new",
                                                            args=('default',)))

        alert = message.find('div')
        self.assertEquals(alert.text, "Loading")

    def test_new_blank_form_no_file(self):
        # When the 'add' sample_type button is clicked if no file has been selected a message should be
        # swapped into the div_id_sample_type_holder tag saying no file has been selected

        url = reverse("core:form_sample_config_new", args=('default',))

        # anything that requires access to a file will need to be a post method
        response = self.client.post(url, {'sample_file': ''})

        soup = BeautifulSoup(response.content, 'html.parser')

        div = soup.find(id="div_id_sample_type_holder")
        self.assertIsNotNone(div)
        msg_div = div.findChild('div')
        self.assertIsNotNone(msg_div)
        self.assertEquals(msg_div.attrs['class'], ['alert', 'alert-warning', 'mt-2'])
        self.assertEquals(msg_div.string, "File is required before adding sample")

    @tag('form_sample_config_test_new_blank_form_with_file')
    def test_new_blank_form_with_file(self):
        # When the 'add' sample_type button is clicked if a file has been selected
        # the SampleTypeForm should be swapped into the div_id_sample_type_holder tag
        file_initial = {"skip": 9, "tab": 0}
        expected_config_form = form_sample_type_config.SampleTypeConfigForm('default', file_type="xlsx",
                                                                            field_choices=self.expected_headers,
                                                                            initial=file_initial)

        expected_form_html = render_crispy_form(expected_config_form)

        url = reverse("core:form_sample_config_new", args=('default',))

        # anything that requres accss to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        returned_content = response.content.decode('utf-8')
        self.assertEquals(returned_content, expected_form_html)

    @tag('form_sample_config_test_submit_new_sample_type_get')
    def test_submit_new_sample_type_get(self):
        # After the form has been filled out and the user clicks the submit button the 'save_sample_config' url
        # should be called with a get request to get the saving alert

        url = reverse("core:form_sample_config_save", args=('default',))

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

        url = reverse("core:form_sample_config_save", args=('default',))

        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp,
                                              'file_type': file_type, 'skip': header,
                                              'mission_id': self.mission.pk})

        soup = BeautifulSoup(response.content, "html.parser")
        missing_fields = ['id_sample_type', 'id_tab', 'id_sample_field', 'id_value_field']
        for field in missing_fields:
            self.assertIsNotNone(soup.find(id=field, attrs={'class': "is-invalid"}))

    @tag('form_sample_config_test_submit_new_sample_type_post')
    def test_submit_new_sample_type_valid_post(self):
        # If a submitted form is valid a div#div_id_loaded_samples_list element should be returned
        # with the 'core/partials/card_sample_config.html' html to be swapped into the
        # #div_id_loaded_samples_list section of the 'core/partials/form_sample_config.html' template

        oxy_sample_type = settings_factory.GlobalSampleTypeFactory(
            short_name='oxy',
            long_name='Oxygen'
        )
        # required post variables that the form would have previously setup without user input
        file_type = 'xlsx'
        header = 9
        tab = 0
        sample_field = 'sample'
        value_field = 'o2_concentration(ml/l)'

        expected_sample_type_load_form_id = f'div_id_sample_config_card_{1}'

        url = reverse("core:form_sample_config_save", args=('default',))

        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp, 'mission_id': self.mission.pk,
                                              'sample_type': oxy_sample_type.pk, 'file_type': file_type,
                                              'skip': header, 'tab': tab, 'sample_field': sample_field,
                                              'value_field': value_field, })

        soup = BeautifulSoup(response.content, 'html.parser')
        div_id_loaded_samples_list = soup.find(id="div_id_loaded_samples_list")
        self.assertIsNotNone(div_id_loaded_samples_list)
        self.assertIn('hx-swap-oob', div_id_loaded_samples_list.attrs)

        sample_type_load_card = div_id_loaded_samples_list.find(id=expected_sample_type_load_form_id)
        self.assertIsNotNone(sample_type_load_card)
        self.assertEquals(len(sample_type_load_card.find_next_siblings()), 0)

    def test_input_file_with_config(self):
        # If a config exists for a selected file it should be presented as a SampleTypeLoadForm in the
        # div_id_loaded_samples_list. This is populated by an out of band select on the file input on the
        # 'core/partials/form_sample_type.html' template. So the 'load_sample_config' method should
        # return an empty 'div_id_sample_type_holder' element to clear the 'loading' alert and the
        # 'div_id_loaded_samples_list' to swap in the list of SampleTypeLoadForms

        oxy_sample_type = settings_factory.GlobalSampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )

        oxy_sample_type_config = settings_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        expected = render_to_string('core/partials/card_sample_config.html',
                                    context={'database': 'default', 'sample_config': oxy_sample_type_config})

        url = reverse("core:form_sample_config_load", args=('default',))
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp, 'mission_id': self.mission.pk})

        soup = BeautifulSoup(response.content, 'html.parser')
        samples_type = soup.find(id='div_id_sample_type_holder')
        self.assertIsNotNone(samples_type)
        self.assertIsNone(samples_type.string)

        list_div = soup.find(id=f'div_id_loaded_sample_type')
        self.assertIsNotNone(list_div)

        self.assertEquals(len(list_div.find_all('div', recursive=False)), 2)
        self.assertIsNotNone(list_div.find(id="div_id_error_list"))
        self.assertIsNotNone(list_div.find(id="div_id_sample_config_card_1"))

    def test_edit_sample_type(self):
        # if the new_sample_config url contains an argument with a 'sample_type' id the form should load with the
        # existing config.

        file_type = 'xlsx'
        oxy_sample_type = settings_factory.GlobalSampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )

        oxy_sample_type_config = settings_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type=file_type,
        )

        url = reverse("core:form_sample_config_new", args=('default', oxy_sample_type.pk,))

        expected_config_form = form_sample_type_config.SampleTypeConfigForm(database='default', file_type=file_type,
                                                                            field_choices=self.expected_headers,
                                                                            instance=oxy_sample_type_config)

        expected_form_html = render_crispy_form(expected_config_form)

        # anything that requires access to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        returned_content = response.content.decode('utf-8')
        self.assertEquals(returned_content, expected_form_html)

    def test_edit_sample_type_update_message(self):
        # if the new_sample_config url contains an argument with a 'config_id' the form should load with the
        # existing config and pass back a saving message pointing to the "sample_type/hx/update/<int:config_id>/" url

        oxy_sample_type = settings_factory.GlobalSampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )

        oxy_sample_type_config = settings_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:form_sample_config_save", args=(oxy_sample_type_config.pk,))

        response = self.client.get(url, {'update_sample_type': ''})

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)

        message = soup.find(id="div_id_loaded_sample_type_message")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], url)

        alert = message.find('div')
        self.assertEquals(alert.text, "Saving")

    def test_edit_sample_type_save_message(self):
        # if the new_sample_config url contains an argument with a 'config_id' the form should load with the
        # existing config and pass back a saving message pointing to the "sample_type/hx/save/" url

        oxy_sample_type = settings_factory.GlobalSampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )

        oxy_sample_type_config = settings_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:form_sample_config_save", args=('default',))

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
        # if the new_sample_config url contains an argument with a 'sample_type' id the form should load with the
        # existing config.

        oxy_sample_type = settings_factory.GlobalSampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )
        oxy_sample_type_config = settings_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            tab=1,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:form_sample_config_save", args=('default', oxy_sample_type_config.pk,))

        # anything that requires access to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url,
                                        {'sample_file': fp, 'mission_id': self.mission.pk,
                                         'sample_type': oxy_sample_type_config.sample_type.pk,
                                         'file_type': oxy_sample_type_config.file_type,
                                         'skip': oxy_sample_type_config.skip, 'tab': 0,
                                         'sample_field': oxy_sample_type_config.sample_field,
                                         'value_field': oxy_sample_type_config.value_field, })

        sample_type = settings_models.SampleTypeConfig.objects.get(pk=oxy_sample_type_config.pk)
        self.assertEquals(sample_type.tab, 0)

    def test_load_samples_get(self):
        # clicking the load button should add a loading websocket alert to the SampleTypeLoadForm message area
        # to indicate that the file is being loaded.

        oxy_sample_type = settings_factory.GlobalSampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )
        oxy_sample_type_config = settings_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            tab=1,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:mission_samples_load_samples", args=('default',))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)

        message = soup.find(id=f"div_id_sample_type_holder_alert")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], url)

        alert = message.find('div')
        self.assertEquals(alert.text, "Loading")

    # in the event the user select the 'New Sample Type' option from the sample_type drop down
    # the drop down should be replaced with a SampleTypeForm allowing the user to create a new
    # sample type. Upon saving that form the dropdown should replace the form, with the new
    # sample type selected
    def test_new_sample_type_form(self):
        # The sample_type dropdown has an hx-get attribute on it that should call 'mission/sample_type/new/'

        expected_form = forms.SampleTypeForm()
        expected_html = render_crispy_form(expected_form)

        url = reverse("core:sample_type_new")

        response = self.client.get(url)

        self.assertEquals(response.content.decode('utf-8'), expected_html)

    def test_new_sample_type_on_config(self):
        # if -1 is passed as the sample_type id to the 'core:form_sample_config_new' url the
        # SampleTypeConfigForm should be returned with the sample_type dropdown replaced
        # with a SampleTypeForm and a button to submit the new sample type

        url = reverse("core:form_sample_config_new", args=('default',))

        response = self.client.get(url, {'sample_type': -1})

        soup = BeautifulSoup(response.content, 'html.parser')
        form = soup.find(id="div_id_sample_type_holder_form")
        self.assertIsNotNone(form)

        button = soup.find(id="button_id_new_sample_type_submit")
        self.assertIsNotNone(button)

    def test_existing_sample_type_on_config(self):
        # if an existing sample type is selected then it should appear as if nothing has happened
        # although what actually happens is the 'new_sample_config' is called, but the form
        # with the initial sample_type set is returned and the div_id_sample_type dropdown
        # is then swapped back in

        oxy_sample_type = settings_factory.GlobalSampleTypeFactory(
            short_name='oxy',
            long_name='Oxygen'
        )

        url = reverse("core:form_sample_config_new", args=('default',))

        response = self.client.get(url, {'sample_type': oxy_sample_type.pk})

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)
        sample_type = soup.find(id='id_sample_type')
        self.assertIsNotNone(sample_type)
        selected = sample_type.find('option', selected=True)
        self.assertIsNotNone(selected)
        self.assertEquals(int(selected.attrs['value']), oxy_sample_type.pk)

    def test_new_sample_type_on_config_save(self):
        # if the 'core:form_sample_config_save' url recieves a POST containing the 'new_sample'
        # attribute then it should create a SampleTypeForm and save the POST vars, then return
        # a SampleTypeConfigForm with the sample_type set to the new sample_type object that was
        # just created.

        url = reverse("core:form_sample_config_save", args=('default',))

        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp, 'new_sample': '',
                                              'short_name': 'oxy', 'priority': 1, 'long_name': 'Oxygen'})

        # a new sample type should have been created
        oxy_sample_type = settings_models.GlobalSampleType.objects.get(short_name='oxy')

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)
        sample_type = soup.find(id='id_sample_type')
        self.assertIsNotNone(sample_type)
        selected = sample_type.find('option', selected=True)
        self.assertIsNotNone(selected)
        self.assertEquals(int(selected.attrs['value']), oxy_sample_type.pk)
