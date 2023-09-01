import os

import bs4
from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.template.loader import render_to_string

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


@tag('forms', 'form_mission_samples')
class TestMissionSamplesForm(DartTestCase):

    def setUp(self) -> None:
        self.client = Client()
        self.mission = core_factory.MissionFactory()

    def test_ctd_card(self):
        # The CTD card should have a form with a text input and a refresh button
        url = reverse('core:sample_details', args=(self.mission.id,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')

        upload_form = soup.find(id="ctd_upload_file_form_id")
        self.assertIsNotNone(upload_form)

    def test_get_btl_list(self):
        # provided a directory a get request to hx_sample_upload_ctd should return a form
        # with a list of files that can be uploaded when selected.
        url = reverse('core:hx_sample_upload_ctd', args=(self.mission.id,))
        dir = os.path.join(settings.BASE_DIR, 'core/tests/sample_data')

        response = self.client.get(url, {"bottle_dir": dir})

        soup = BeautifulSoup(response.content, 'html.parser')
        file_selection = soup.find(id="id_file_name")
        self.assertIsNotNone(file_selection)

    def test_event_upload_selected(self):
        # Upon selecting files and clicking the submit button a get request should be made to
        # hx_sample_upload_ctd that will return a loading dialog that will make a post request
        # to hx_sample_upload_ctd with a websocket on it.
        url = reverse('core:hx_sample_upload_ctd', args=(self.mission.id,))

        dir = os.path.join(settings.BASE_DIR, 'core/tests/sample_data')

        response = self.client.get(url, {"bottle_dir": dir, "file_name": ['JC243a001.btl', 'JC243a006.btl']})
        soup = BeautifulSoup(response.content, 'html.parser')
        div_load_alert = soup.find(id='div_id_upload_ctd_load')

        self.assertIsNotNone(div_load_alert)
        self.assertIn('hx-post', div_load_alert.attrs)


@tag('forms', 'form_mission_events')
class TestMissionEventForm(DartTestCase):

    def setUp(self) -> None:
        self.client = Client()
        self.mission = core_factory.MissionFactory()

    def test_events_card(self):
        # the mission events page should have a card on it that contains an upload button
        url = reverse("core:event_details", args=(self.mission.id,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')

        upload_form = soup.find(id="elog_upload_file_form_id")
        self.assertIsNotNone(upload_form)

        form_input = soup.find(id="event_file_input_id")
        self.assertIsNotNone(form_input)

    def test_events_upload_response(self):
        # the response from a get request to core:hx_elog_upload url should contain a loading alert
        # the loading alert should have a post request to core:hx_elog_upload to start the processing
        # of uploaded files.
        url = reverse("core:hx_upload_elog", args=(self.mission.id,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        div_load_alert = soup.find(id='div_id_upload_elog_load')

        self.assertIsNotNone(div_load_alert)
        self.assertIn('hx-post', div_load_alert.attrs)


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
            forms.SampleTypeConfigForm()
            self.fail("An exception should have been raised for missing arguments")
        except KeyError as ex:
            self.assertEquals(ex.args[0]["message"], "missing initial \"file_type\"")

        try:
            forms.SampleTypeConfigForm(initial={})
            self.fail("An exception should have been raised for missing arguments")
        except KeyError as ex:
            self.assertEquals(ex.args[0]["message"], "missing initial \"file_type\"")

    def test_form_exists(self):
        url = reverse("core:load_sample_config") + f"?mission={self.mission.pk}"
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

        url = reverse("core:load_sample_config")
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
        # tag should contain a message that no configs were found

        url = reverse("core:load_sample_config")
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        soup = BeautifulSoup(response.content, 'html.parser')
        samples_list = soup.find(id='div_id_sample_type_holder')
        msg_div = samples_list.findChild('div')

        self.assertIsNotNone(msg_div)
        self.assertEquals(msg_div.attrs['class'], ['alert', 'alert-warning', 'mt-2'])
        self.assertEquals(msg_div.string, "No File Configurations Found")

    def test_new_blank_loading_msg(self):
        # When the 'add' sample_type button is clicked an alert dialog should be swapped in indicating that a loading
        # operation is taking place, this is a get request so no file is needed. The alert will then call
        # new_sample_config with a post request to retrieve the details
        url = reverse("core:new_sample_config")

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')

        message = soup.find(id="div_id_loaded_sample_type_message")

        self.assertIsNotNone(message)
        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertEquals(message.attrs['hx-post'], reverse("core:new_sample_config"))

        alert = message.find('div')
        self.assertEquals(alert.text, "Loading")

    def test_new_blank_form_no_file(self):
        # When the 'add' sample_type button is clicked if no file has been selected a message should be
        # swapped into the div_id_sample_type_holder tag saying no file has been selected

        url = reverse("core:new_sample_config")

        # anything that requires access to a file will need to be a post method
        response = self.client.post(url, {'sample_file': ''})

        soup = BeautifulSoup(response.content, 'html.parser')

        div = soup.find(id="div_id_sample_type_holder")
        self.assertIsNotNone(div)
        msg_div = div.findChild('div')
        self.assertIsNotNone(msg_div)
        self.assertEquals(msg_div.attrs['class'], ['alert', 'alert-warning', 'mt-2'])
        self.assertEquals(msg_div.string, "File is required before adding sample")

    def test_new_blank_form_with_file(self):
        # When the 'add' sample_type button is clicked if a file has been selected
        # the SampleTypeForm should be swapped into the div_id_sample_type_holder tag
        file_initial = {"file_type": "xlsx", "skip": 9, "tab": 0}
        expected_config_form = forms.SampleTypeConfigForm(field_choices=self.expected_headers, initial=file_initial)

        expected_form_html = render_crispy_form(expected_config_form)

        url = reverse("core:new_sample_config")

        # anything that requres accss to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        returned_content = response.content.decode('utf-8')
        self.assertEquals(returned_content, expected_form_html)

    def test_submit_new_sample_type(self):
        # After the form has been filled out and the user clicks the submit button the 'save_sample_config' url
        # should be called with a get request to get the saving alert

        url = reverse("core:save_sample_config")

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
        post_vars = {'file_type': file_type, 'skip': header}

        expected_config_form = forms.SampleTypeConfigForm(post_vars, field_choices=self.expected_headers)
        expected_config_form.is_valid()

        expected_form_html = render_crispy_form(expected_config_form)

        url = reverse("core:save_sample_config")

        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp,
                                              'file_type': file_type, 'skip': header,
                                              'mission_id': self.mission.pk})

        logger.debug(response.content)
        self.assertEquals(response.content.decode('utf-8'), str(expected_form_html))

    def test_submit_new_sample_type_valid(self):
        # If a submitted form is valid a div#div_id_loaded_samples_list element should be returned
        # with the 'core/partials/card_sample_config.html' html to be swapped into the
        # #div_id_loaded_samples_list section of the 'core/partials/form_sample_config.html' template

        oxy_sample_type = core_factory.SampleTypeFactory(
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

        url = reverse("core:save_sample_config")

        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp, 'mission_id': self.mission.pk,
                                              'sample_type': oxy_sample_type.pk, 'file_type': file_type,
                                              'skip': header, 'tab': tab, 'sample_field': sample_field,
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
        # 'core/partials/form_sample_type.html' template. So the 'load_sample_config' method should
        # return an empty 'div_id_sample_type_holder' element to clear the 'loading' alert and the
        # 'div_id_loaded_samples_list' to swap in the list of SampleTypeLoadForms

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )

        oxy_sample_type_config = core_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        expected = render_to_string('core/partials/card_sample_config.html',
                                    context={'sample_config': oxy_sample_type_config})
        expected_soup = BeautifulSoup(f'<div id="div_id_loaded_samples_list">{expected}</div>', 'html.parser')

        url = reverse("core:load_sample_config")
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        soup = BeautifulSoup(response.content, 'html.parser')
        samples_type = soup.find(id='div_id_sample_type_holder')
        self.assertIsNotNone(samples_type)
        self.assertIsNone(samples_type.string)

        list_div = soup.find(id=f'div_id_loaded_samples_list').find('div')
        self.assertIsNotNone(list_div)

        self.assertEquals(len(list_div.find_next_siblings()), 0)

    def test_edit_sample_type(self):
        # if the new_sample_config url contains an argument with a 'sample_type' id the form should load with the
        # existing config.

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )

        oxy_sample_type_config = core_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:new_sample_config", args=(oxy_sample_type.pk,))

        expected_config_form = forms.SampleTypeConfigForm(instance=oxy_sample_type_config,
                                                          field_choices=self.expected_headers)

        expected_form_html = render_crispy_form(expected_config_form)

        # anything that requires access to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp})

        returned_content = response.content.decode('utf-8')
        self.assertEquals(returned_content, expected_form_html)

    def test_edit_sample_type_update_message(self):
        # if the new_sample_config url contains an argument with a 'config_id' the form should load with the
        # existing config and pass back a saving message pointing to the "sample_type/hx/update/<int:config_id>/" url

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )

        oxy_sample_type_config = core_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:save_sample_config", args=(oxy_sample_type_config.pk,))

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

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )

        oxy_sample_type_config = core_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:save_sample_config", )

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

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )
        oxy_sample_type_config = core_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            tab=1,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:save_sample_config", args=(oxy_sample_type_config.pk,))

        # anything that requires access to a file will need to be a post method
        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url,
                                        {'sample_file': fp, 'mission_id': self.mission.pk,
                                         'sample_type': oxy_sample_type_config.sample_type.pk,
                                         'file_type': oxy_sample_type_config.file_type,
                                         'skip': oxy_sample_type_config.skip, 'tab': 0,
                                         'sample_field': oxy_sample_type_config.sample_field,
                                         'value_field': oxy_sample_type_config.value_field, })

        sample_type = core.models.SampleTypeConfig.objects.get(pk=oxy_sample_type_config.pk)
        self.assertEquals(sample_type.tab, 0)

    def test_load_samples(self):
        # clicking the load button should add a loading alert to the SampleTypeLoadForm message area
        # to indicate that the file is being loaded.

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name="oxy",
            long_name="Oxygen",
        )
        oxy_sample_type_config = core_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            tab=1,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        url = reverse("core:load_samples", args=(oxy_sample_type_config.pk,))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)

        message = soup.find(id=f"div_id_loading_div_id_sample_config_card_{oxy_sample_type_config.pk}")

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
        )
        oxy_sample_type_config = core_factory.SampleTypeConfigFactory(
            sample_type=oxy_sample_type,
            skip=9,
            sample_field='sample',
            value_field='o2_concentration(ml/l)',
            comment_field='comment',
            file_type='xlsx',
        )

        message_div_id = f'div_id_sample_config_card_{oxy_sample_type_config.pk}'
        url = reverse("core:load_samples", args=(oxy_sample_type_config.pk,))

        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp, 'mission_id': self.mission.pk})

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)

        button = soup.find(id=f"{message_div_id}_load_button")

        self.assertIsNotNone(button)
        self.assertIn('btn-warning', button.attrs['class'])

        errors = soup.find(id=f"{message_div_id}_message")

        self.assertIsNotNone(errors)

    # in the event the user select the 'New Sample Type' option from the sample_type drop down
    # the drop down should be replaced with a SampleTypeForm allowing the user to create a new
    # sample type. Upon saving that form the dropdown should replace the form, with the new
    # sample type selected
    def test_new_sample_type_form(self):
        # The sample_type dropdown has an hx-get attribute on it that should call 'mission/sample_type/new/'

        expected_form = forms.SampleTypeForm()
        expected_html = render_crispy_form(expected_form)

        url = reverse("core:new_sample_type")

        response = self.client.get(url)

        self.assertEquals(response.content.decode('utf-8'), expected_html)

    def test_new_sample_type_on_config(self):
        # if -1 is passed as the sample_type id to the 'core:new_sample_config' url the
        # SampleTypeConfigForm should be returned with the sample_type dropdown replaced
        # with a SampleTypeForm and a button to submit the new sample type

        url = reverse("core:new_sample_config")

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

        oxy_sample_type = core_factory.SampleTypeFactory(
            short_name='oxy',
            long_name='Oxygen'
        )

        url = reverse("core:new_sample_config")

        response = self.client.get(url, {'sample_type': oxy_sample_type.pk})

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)
        sample_type = soup.find(id='id_sample_type')
        self.assertIsNotNone(sample_type)
        selected = sample_type.find('option', selected=True)
        self.assertIsNotNone(selected)
        self.assertEquals(int(selected.attrs['value']), oxy_sample_type.pk)

    def test_new_sample_type_on_config_save(self):
        # if the 'core:save_sample_config' url recieves a POST containing the 'new_sample'
        # attribute then it should create a SampleTypeForm and save the POST vars, then return
        # a SampleTypeConfigForm with the sample_type set to the new sample_type object that was
        # just created.

        url = reverse("core:save_sample_config")

        with open(self.sample_oxy_xlsx_file, 'rb') as fp:
            response = self.client.post(url, {'sample_file': fp, 'new_sample': '',
                                              'short_name': 'oxy', 'priority': 1, 'long_name': 'Oxygen'})

        # a new sample type should have been created
        oxy_sample_type = core.models.SampleType.objects.get(short_name='oxy')

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.debug(soup)
        sample_type = soup.find(id='id_sample_type')
        self.assertIsNotNone(sample_type)
        selected = sample_type.find('option', selected=True)
        self.assertIsNotNone(selected)
        self.assertEquals(int(selected.attrs['value']), oxy_sample_type.pk)


@tag('forms', 'forms_sample_type_card')
class TestSampleTypeCard(DartTestCase):

    def setUp(self) -> None:
        pass

    def test_form_exists(self):
        # given a sample type id of an existing sample type the 'core:load_sample_type' url
        # should return a 'core/partials/card_sample_type.html' template

        sample_type = core_factory.SampleTypeFactory(short_name='oxy', long_name="Oxygen")

        url = reverse('core:load_sample_type', args=(sample_type.pk,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.find(id=f"div_id_sample_type_{sample_type.pk}"))

    # when the delete sample type button is clicked on the sample type card
    # the 'core:delete_sample_type' url should be called with a post request.
    # The results should be an alert that will be swapped into the message area
    # upon success the alert will have a hx-trigger='load' that targets the
    # cards id and a hx-swap='delete' that will remove the card.
    # on failure a message will be swapped in describing why the sample type can't be deleted
    def test_delete_sample_type_success(self):

        sample_type = core_factory.SampleTypeFactory(short_name='oxy', long_name="Oxygen")

        url = reverse('core:delete_sample_type', args=(sample_type.pk,))

        response = self.client.post(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)

    def test_delete_sample_type_fail(self):
        # if there are missions that have samples that are using this sample type, it should not be deleted
        # and the user should get back a message saying why.
        oxy_sample_type = core_factory.SampleTypeFactory(short_name='oxy', long_name="Oxygen")

        core_factory.SampleFactory(type=oxy_sample_type)

        url = reverse('core:delete_sample_type', args=(oxy_sample_type.pk,))

        response = self.client.post(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)

    def test_save_sample_type_invalid(self):
        # if no short_name is provided then an invalid form should be returned
        url = reverse('core:save_sample_type')
        response = self.client.post(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.find(id="div_id_sample_type_form"))  # invalid form

        short_name_input = soup.find(id='id_short_name')
        self.assertIn('is-invalid', short_name_input.attrs['class'])

    def test_save_sample_type(self):
        # provided a post request with a short_name and priority, the sample type should be saved and
        # a div_id_loaded_sample_types element along with div_id_sample_type_form should be returned
        # to be swapped into the 'core/sample_settings.html' template
        kwargs = {'short_name': 'oxy', 'priority': '1'}

        url = reverse('core:save_sample_type')
        response = self.client.post(url, kwargs)

        sample_type = core.models.SampleType.objects.filter(short_name='oxy')
        self.assertTrue(sample_type.exists())

        soup = BeautifulSoup(response.content, 'html.parser')
        form = soup.find(id="div_id_sample_type_form")
        self.assertIsNotNone(form)  # blank form
        self.assertIsNone(form.find(id='id_short_name').string)

        new_card = soup.find(id='div_id_loaded_sample_types')
        self.assertIsNotNone(new_card)

    def test_edit_sample_type(self):
        # provided a sample_type.pk to the 'core:edit_sample_type' url a SampleTypeForm should be returned
        # populated with the sample_type details

        sample_type = core_factory.SampleTypeFactory(short_name='oxy', long_name='Oxygen')

        url = reverse('core:edit_sample_type', args=(sample_type.pk,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.find(id='div_id_sample_type_form'))

        short_name_input = soup.find(id='id_short_name')
        self.assertEquals(short_name_input.attrs['value'], sample_type.short_name)

        long_name_input = soup.find(id='id_long_name')
        self.assertEquals(long_name_input.attrs['value'], sample_type.long_name)

    def test_save_update_sample_type(self):
        # provided an existing sample type with updated post arguments the sample_type should be updated
        sample_type = core_factory.SampleTypeFactory(short_name='oxy', long_name='Oxygen')

        url = reverse('core:save_sample_type', args=(sample_type.pk,))

        response = self.client.post(url, {'short_name': sample_type.short_name,
                                          'priority': sample_type.priority,
                                          'long_name': 'Oxygen2'})

        sample_type_updated = core.models.SampleType.objects.filter(short_name='oxy')
        self.assertTrue(sample_type_updated.exists())
        self.assertEquals(sample_type_updated[0].long_name, 'Oxygen2')

        soup = BeautifulSoup(response.content, 'html.parser')
        form = soup.find(id="div_id_sample_type_form")
        self.assertIsNotNone(form)  # blank form
        self.assertIsNone(form.find(id='id_short_name').string)

        new_card = soup.find(id=f'div_id_sample_type_{ sample_type.pk }')
        self.assertIsNotNone(new_card)
