import os.path

from bs4 import BeautifulSoup

from django.test import tag, Client
from django.urls import reverse
from django.conf import settings

from core.parsers import PlanktonParser
from dart.tests.DartTestCase import DartTestCase

from core.tests import CoreFactoryFloor as core_factory
from core import models as core_models


@tag('forms', 'form_plankton')
class TestFormPlanktonLoad(DartTestCase):

    entry_point_url = "core:mission_plankton_plankton_details"
    load_plankton_url = "core:form_plankton_load_plankton"
    import_plankton_url = "core:form_plankton_import_plankton"
    list_plankton_url = "core:form_plankton_list_plankton"
    clear_plankton_url = "core:mission_plankton_clear"

    def setUp(self):
        self.mission = core_factory.MissionFactory()
        self.client = Client()

        # The origional column name for the sample ID in a plankton file was just 'ID'. It changed to 'SAMPLE_ID' in
        # 2024. The test file still uses 'ID', but the Plankton Parser was updated to use the file config model
        # so we can update the field for the file we're loading pretty easily.
        config = PlanktonParser.get_or_create_phyto_file_config().get(required_field='id')
        config.mapped_field = 'ID'
        config.save()

    @tag('form_plankton_test_entry_point')
    def test_form_entry_point(self):
        # Provided a database and mission id calling the entry point url should return the
        # views_mission_plankton.PlanktonDetails() page
        url = reverse(self.entry_point_url, args=('default', self.mission.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")
        self.assertIsNotNone(soup)

        card = soup.find(id="div_id_card_plankton_form")
        self.assertIsNotNone(card)

        card_head = card.find(attrs={'class': "card-header"})
        self.assertIsNotNone(card_head)

        card_body = card.find(attrs={"class": "card-body"})
        self.assertIsNotNone(card_body)

        card_form = card_body.find(id="form_id_plankton_upload")
        self.assertIsNotNone(card_form)

        # the form should have a file chooser input field with hx-get=url, hx-trigger='change', hx-swap='none'
        # to call the function to load the rest of the form when the user selects a file
        file_url = reverse(self.load_plankton_url, args=('default', self.mission.pk))
        file_input = card_form.find(id="id_input_sample_file")
        self.assertIsNotNone(file_input)
        self.assertIn('hx-get', file_input.attrs)
        self.assertEquals(file_input.attrs['hx-get'], file_url)

        self.assertIn('hx-trigger', file_input.attrs)
        self.assertEquals(file_input.attrs['hx-trigger'], 'change')

        self.assertIn('hx-swap', file_input.attrs)
        self.assertEquals(file_input.attrs['hx-swap'], 'none')

        # the form needs to have a message area to display save/load dialogs
        card_msg_area = card_form.find(id="div_id_plankton_message")
        self.assertIsNotNone(card_msg_area)

        # below the save/load message area the card needs a row to swap in additional
        # form elements once a file is chosen
        card_form_area = card_form.find(id="div_id_plankton_form")
        self.assertIsNotNone(card_form_area)

    @tag('form_plankton_test_file_chooser_get')
    def test_file_chooser_get(self):
        # using a get request on the file_chooser url when the user selects a file should send back
        # a save/load dialog that will call hx-post=[file_chooser url] on hx-trigger='load'
        url = reverse(self.load_plankton_url, args=('default', self.mission.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        message = soup.find(id="div_id_plankton_message")
        self.assertIsNotNone(message)
        self.assertIn('hx-post', message.attrs)

        self.assertEquals(message.attrs['hx-post'], url)
        self.assertIn('hx-trigger', message.attrs)

        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertIn('hx-swap-oob', message.attrs)

    @tag('form_plankton_test_file_chooser_zoo_post')
    def test_file_chooser_zoo_post(self):
        # using a post request provided a plankton file, the file_chooser url should return a PlanktonForm
        file_name = "sample_zoo.xlsx"
        file_location = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        file = os.path.join(file_location, file_name)
        url = reverse(self.load_plankton_url, args=('default', self.mission.pk))

        with open(file, 'rb') as fp:
            response = self.client.post(url, {'plankton_file': fp})

        soup = BeautifulSoup(response.content, 'html.parser')

        form_details = soup.find(id="div_id_plankton_form_details")
        self.assertIsNotNone(form_details)

    @tag('form_plankton_test_import_plankton_get')
    def test_import_plankton_get(self):
        # calling the import plankton url should return a save/load dialog to be swapped in at
        # the div_id_plankton_message element that will have hx-post=url and hx-trigger='load' attributes
        url = reverse(self.import_plankton_url, args=('default', self.mission.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        message = soup.find(id="div_id_plankton_message")
        self.assertIsNotNone(message)
        self.assertIn('hx-post', message.attrs)

        self.assertEquals(message.attrs['hx-post'], url)
        self.assertIn('hx-trigger', message.attrs)

        self.assertEquals(message.attrs['hx-trigger'], 'load')
        self.assertIn('hx-swap-oob', message.attrs)

    @tag('form_plankton_test_import_zoo_plankton_post')
    def test_import_zoo_plankton_post(self):
        # posting the import plankton url with a valid file should load the plankton data
        file_name = "sample_zoo.xlsx"
        file_location = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        file = os.path.join(file_location, file_name)

        # the events will have to exist for this to load, the numbers come from the 'event' column of the sample file
        core_factory.NetEventFactory(mission=self.mission, event_id=2)
        core_factory.NetEventFactory(mission=self.mission, event_id=88)

        url = reverse(self.import_plankton_url, args=('default', self.mission.pk))
        with open(file, 'rb') as fp:
            response = self.client.post(url, {'plankton_file': fp, 'tab': 1, 'header': 0})

        soup = BeautifulSoup(response.content, 'html.parser')

        plankton = core_models.PlanktonSample.objects.using('default').all()
        self.assertTrue(plankton.exists())

        # the function should clear the div_id_plankton_message area
        msg_area = soup.find(id="div_id_plankton_message")
        self.assertIsNotNone(msg_area)

        success_msg = msg_area.find(id="div_id_message_alert")
        self.assertIsNotNone(success_msg)
        # the css class will be applied to the first child of the alert
        self.assertIn('alert-success', success_msg.find(recursive=False).attrs['class'])

        # the plankton form should also be cleared with an out of band swap
        form = soup.find(id="div_id_plankton_form")
        self.assertIsNotNone(form)
        self.assertIn('hx-swap-oob', form.attrs)
        self.assertEquals(0, len(form.find_all()))

        # the response should have an Hx-Trigger="update_samples" event to tell listening elements to update
        self.assertIn('Hx-Trigger', response.headers)
        self.assertEquals(response.headers['Hx-Trigger'], 'update_samples')

    @tag('form_plankton_test_import_phyto_plankton_post')
    def test_import_phyto_plankton_post(self):
        # posting the import plankton url with a valid file should load the plankton data
        file_name = "sample_phyto.xlsx"
        file_location = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        file = os.path.join(file_location, file_name)

        # the events will have to exist for this to load, the numbers come from the 'event' column of the sample file
        # phytoplankton comes from CTD events not Net events, and the bottles have to exist
        event = core_factory.CTDEventFactory(mission=self.mission, event_id=7)
        core_factory.BottleFactory(event=event, bottle_id=488275)

        event = core_factory.CTDEventFactory(mission=self.mission, event_id=92)
        core_factory.BottleFactory(event=event, bottle_id=488685)

        url = reverse(self.import_plankton_url, args=('default', self.mission.pk))
        with open(file, 'rb') as fp:
            response = self.client.post(url, {'plankton_file': fp, 'tab': 0, 'header': 0})

        soup = BeautifulSoup(response.content, 'html.parser')

        plankton = core_models.PlanktonSample.objects.using('default').all()
        self.assertTrue(plankton.exists())

        # the function should clear the div_id_plankton_message area
        msg_area = soup.find(id="div_id_plankton_message")
        self.assertIsNotNone(msg_area)

        success_msg = msg_area.find(id="div_id_message_alert")
        self.assertIsNotNone(success_msg)
        # the css class will be applied to the first child of the alert
        self.assertIn('alert-success', success_msg.find(recursive=False).attrs['class'])

        # the plankton form should also be cleared with an out of band swap
        form = soup.find(id="div_id_plankton_form")
        self.assertIsNotNone(form)
        self.assertIn('hx-swap-oob', form.attrs)
        self.assertEquals(0, len(form.find_all()))

        # the response should have an Hx-Trigger="update_samples" event to tell listening elements to update
        self.assertIn('Hx-Trigger', response.headers)
        self.assertEquals(response.headers['Hx-Trigger'], 'update_samples')

    @tag('form_plankton_test_list_plankton_get')
    def test_list_plankton_get(self):
        # Provided a database and mission id calling the list plankton function as a get request should
        # return a table of existing plankton samples to be swapped into the Plankton Samples card
        url = reverse(self.list_plankton_url, args=('default', self.mission.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")
        table = soup.find(id="div_id_plankton_data_table")
        self.assertIsNotNone(table)

        self.assertIn('hx-swap-oob', table.attrs)
        self.assertIn('hx-get', table.attrs)
        self.assertEquals(table.attrs['hx-get'], url)
        self.assertIn('hx-trigger', table.attrs)
        # the hx-trigger should NOT include 'load' because that will cause an infinite loop where the element
        # is swapped in and then immediately calls the url again.
        self.assertEquals(table['hx-trigger'], 'update_samples from:body')

    @tag('form_plankton_test_clear_plankton_post')
    def test_clear_plankton_post(self):
        # provided a database and mission_id, the clear plankton url should remove existing plankton data
        event = core_factory.CTDEventFactory(mission=self.mission)
        bottles = core_factory.BottleFactory.create_batch(10, event=event)
        for bottle in bottles:
            core_factory.PhytoplanktonSampleFactory(bottle=bottle)

        plankton = core_models.PlanktonSample.objects.using('default').all()
        self.assertTrue(plankton.exists())

        url = reverse(self.clear_plankton_url, args=('default', self.mission.pk))
        response = self.client.post(url)

        plankton = core_models.PlanktonSample.objects.using('default').all()
        self.assertFalse(plankton.exists())

        # the response should also have Hx-Trigger="update_samples" to update the sample table
        self.assertIn('Hx-Trigger', response.headers)
        self.assertEqual(response.headers['Hx-Trigger'], 'update_samples')

    @tag('form_plankton_test_get_plankton_db_card_get')
    def test_get_plankton_db_card(self):
        # provided a database and mission_id the get plankton db card url should return a database connection
        # card used for uploading plankton samples to BSD_P and BSC_P tables

        url = reverse('core:mission_plankton_biochem_upload_plankton', args=('default', self.mission.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)
