import os

from bs4 import BeautifulSoup

from django.test import tag, Client
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _

from core import forms as core_forms

from core.parsers import ctd
from config import settings
from config.tests.DartTestCase import DartTestCase

from core.tests import CoreFactoryFloor as core_factory

from settingsdb import models as settings_models
from settingsdb.tests import SettingsFactoryFloor as settings_factory

import logging

logger = logging.getLogger("dart.test")


@tag('forms', 'form_mission_plankton')
class TestMissionPlanktonForm(DartTestCase):

    def setUp(self) -> None:
        self.client = Client()
        self.mission = core_factory.MissionFactory()

    def test_plankton_form(self):
        url = reverse('core:mission_plankton_plankton_details', args=('default', self.mission.pk,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')

        upload_form = soup.find(id='form_id_plankton_upload')
        self.assertIsNotNone(upload_form)


@tag('forms', 'form_mission_samples')
class TestMissionSamplesForm(DartTestCase):

    def setUp(self) -> None:
        self.client = Client()
        self.mission = core_factory.MissionFactory()

    def test_ctd_card(self):
        # The CTD card should have a form with a text input and a refresh button
        url = reverse('core:mission_samples_sample_details', args=('default', self.mission.pk,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')

        upload_form = soup.find(id="id_form_load_samples")
        self.assertIsNotNone(upload_form)

    def test_event_upload_selected(self):
        # Upon selecting files and clicking the submit button a get request should be made to
        # sample_upload_ctd that will return a loading dialog that will make a post request
        # to sample_upload_ctd with a websocket on it.
        url = reverse('core:form_btl_upload_bottles', args=(self.mission.pk,))

        attrs = {
            'alert_area_id': "div_id_alert_bottle_load",
            'message': _("Loading Bottles"),
            'logger': ctd.logger_notifications.name,
            'hx-post': url,
            'hx-trigger': 'load',
            'hx-swap': "none"
        }

        alert = core_forms.websocket_post_request_alert(**attrs)

        sample_dir = os.path.join(settings.BASE_DIR, 'core/tests/sample_data')

        response = self.client.get(url, {"bottle_dir": sample_dir, "file_name": ['JC243a001.btl', 'JC243a006.btl']})
        soup = BeautifulSoup(response.content, 'html.parser')

        self.assertEqual(soup.prettify(), alert.prettify())


@tag('forms', 'forms_sample_type_card')
class TestSampleTypeCard(DartTestCase):

    def setUp(self) -> None:
        pass

    def test_form_exists(self):
        # given a sample type id of an existing sample type the 'core:sample_type_load' url
        # should return a 'core/partials/card_sample_type.html' template

        sample_type = settings_factory.GlobalSampleTypeFactory(short_name='oxy', long_name="Oxygen")

        url = reverse('core:sample_type_load', args=(sample_type.pk,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.find(id=f"div_id_sample_type_{sample_type.pk}"))

    def test_save_sample_type_invalid(self):
        # if no short_name is provided then an invalid form should be returned
        url = reverse('core:sample_type_save')
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

        url = reverse('core:sample_type_save')
        response = self.client.post(url, kwargs)

        sample_type = settings_models.GlobalSampleType.objects.filter(short_name='oxy')
        self.assertTrue(sample_type.exists())

        soup = BeautifulSoup(response.content, 'html.parser')
        form = soup.find(id="div_id_sample_type_form")
        self.assertIsNotNone(form)  # blank form
        self.assertIsNone(form.find(id='id_short_name').string)

        new_card = soup.find(id='div_id_loaded_sample_types')
        self.assertIsNotNone(new_card)

    def test_edit_sample_type(self):
        # provided a sample_type.pk to the 'core:sample_type_edit' url a SampleTypeForm should be returned
        # populated with the sample_type details

        sample_type = settings_factory.GlobalSampleTypeFactory(short_name='oxy', long_name='Oxygen')

        url = reverse('core:sample_type_edit', args=(sample_type.pk,))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.find(id='div_id_sample_type_form'))

        short_name_input = soup.find(id='id_short_name')
        self.assertEqual(short_name_input.attrs['value'], sample_type.short_name)

        long_name_input = soup.find(id='id_long_name')
        self.assertEqual(long_name_input.attrs['value'], sample_type.long_name)

    def test_save_update_sample_type(self):
        # provided an existing sample type with updated post arguments the sample_type should be updated
        sample_type = settings_factory.GlobalSampleTypeFactory(short_name='oxy', long_name='Oxygen')

        url = reverse('core:sample_type_save', args=(sample_type.pk,))

        response = self.client.post(url, {'short_name': sample_type.short_name,
                                          'priority': sample_type.priority,
                                          'long_name': 'Oxygen2'})

        sample_type_updated = settings_models.GlobalSampleType.objects.filter(short_name='oxy')
        self.assertTrue(sample_type_updated.exists())
        self.assertEqual(sample_type_updated[0].long_name, 'Oxygen2')

        soup = BeautifulSoup(response.content, 'html.parser')
        form = soup.find(id="div_id_sample_type_form")
        self.assertIsNotNone(form)  # blank form
        self.assertIsNone(form.find(id='id_short_name').string)

        new_card = soup.find(id=f'div_id_sample_type_{ sample_type.pk }')
        self.assertIsNotNone(new_card)
