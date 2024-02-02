import os
from datetime import datetime

from bs4 import BeautifulSoup
from django.test import tag, Client
from django.urls import reverse
from django.conf import settings

from dart2.tests.DartTestCase import DartTestCase

from core.tests import CoreFactoryFloor as core_factory
from core import models


@tag('forms', 'form_btl_load')
class TestFormBottleLoad(DartTestCase):

    def setUp(self) -> None:
        self.client = Client()

    @tag('form_btl_load_test_bottle_load_get')
    def test_bottle_load_get(self):
        # provided a mission and database the form_btl_card url on a get request should return a "Load Sample from file"
        # card
        mission = core_factory.MissionFactory()

        url = reverse("core:form_btl_card", args=('default', mission.pk))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")

        sample_card = soup.find(id="div_id_card_bottle_load")
        self.assertIsNotNone(sample_card)

        # by default loaded BTL files should be hidden
        show_hide_field = soup.find(id="id_hide_loaded")
        self.assertNotIn('value', show_hide_field.attrs)

    @tag('form_btl_load_test_bottle_load_get_with_dir')
    def test_bottle_load_get_with_dir(self):
        # provided a mission with a directory containing BTL files and database the form_btl_card url on a get request
        # should return a "Load Sample from file" with the dir field populated with the missions bottle_directory
        # and the files field in the body of the card should list BTL files from the directory
        btl_directory = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        btl_files = [file for file in os.listdir(btl_directory) if file.upper().endswith('BTL')]

        mission = core_factory.MissionFactory(bottle_directory=btl_directory)

        url = reverse("core:form_btl_card", args=('default', mission.pk))

        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")

        bottle_dir_field = soup.find(id="id_dir_field")
        self.assertIsNotNone(bottle_dir_field)
        self.assertEquals(bottle_dir_field.attrs['value'], btl_directory)

        files_field = soup.find(id="id_files")
        self.assertIsNotNone(files_field)
        for file in btl_files:
            file_option = files_field.find(attrs={'value': file})
            self.assertIsNotNone(file_option)

    @tag('form_btl_load_test_reload_files')
    def test_reload_files(self):
        # provided a mission and database the reload files url, called when the user updates
        # the mission.bottle_directory should return an updated "Load Bottles" card
        btl_directory = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        btl_files = [file for file in os.listdir(btl_directory) if file.upper().endswith('BTL')]

        mission = core_factory.MissionFactory(bottle_directory=btl_directory)

        url = reverse("core:form_btl_reload_files", args=('default', mission.pk))
        response = self.client.get(url)
        soup = BeautifulSoup(response.content, "html.parser")

        files_field = soup.find(id="id_files")
        self.assertIsNotNone(files_field)
        for file in btl_files:
            file_option = files_field.find(attrs={'value': file})
            self.assertIsNotNone(file_option)

    @tag('form_btl_load_test_reload_files_show_all')
    def test_reload_files_show_all(self):
        # provided a database and mission and 'hide_loaded' is *not* in the get request
        # the 'hide_loaded' field should be false
        btl_directory = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        mission = core_factory.MissionFactory(bottle_directory=btl_directory)

        url = reverse("core:form_btl_reload_files", args=('default', mission.pk))
        response = self.client.get(url)
        soup = BeautifulSoup(response.content, "html.parser")

        show_hide_field = soup.find(id="id_hide_loaded")
        self.assertNotIn('value', show_hide_field.attrs)

    @tag('form_btl_load_test_reload_files_hide_loaded')
    def test_reload_files_hide_loaded(self):
        # provided a database and mission and 'hide_loaded' is in the get request
        # the 'hide_loaded' field should be true
        btl_directory = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        mission = core_factory.MissionFactory(bottle_directory=btl_directory)

        url = reverse("core:form_btl_reload_files", args=('default', mission.pk))
        response = self.client.get(url, {'hide_loaded': 'true'})
        soup = BeautifulSoup(response.content, "html.parser")

        show_hide_field = soup.find(id="id_hide_loaded")
        self.assertEquals(show_hide_field.attrs['value'], 'true')

    @tag('form_btl_load_test_upload_btl_files_get')
    def test_upload_btl_files_get(self):
        # provided a mission and database, calling the update files url as a get request should return a web socket
        # save-load dialog that will initialize the update files url with an hx-post request on hx-trigger="load"
        btl_directory = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        mission = core_factory.MissionFactory(bottle_directory=btl_directory)

        url = reverse("core:form_btl_upload_bottles", args=('default', mission.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")

        alert = soup.find(id="div_id_alert_bottle_load_alert")
        self.assertIsNotNone(alert)
        self.assertIn('hx-post', alert.attrs)
        self.assertIn('hx-trigger', alert.attrs)
        self.assertEquals(alert.attrs['hx-post'], url)
        self.assertEquals(alert.attrs['hx-trigger'], 'load')

    @tag('form_btl_load_test_upload_btl_files_post')
    def test_upload_btl_files_post(self):
        # provided a database, BTL file and mission containing bottle ids for the BTL file calling the upload
        # bottle file as a post request should load the bottles into the mission's database
        # an alert should be returned that calls the url to reload hte bottles form with an Hx-Trigger="update_samples"
        # attached
        btl_file = "JC243a001.BTL"
        btl_directory = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        btl = os.path.join(btl_directory, btl_file)

        mission = core_factory.MissionFactory(bottle_directory=btl_directory)
        trip = core_factory.TripFactory(mission=mission,
                                        start_date=datetime.strptime("2022-10-01", "%Y-%m-%d"),
                                        end_date=datetime.strptime("2022-10-20", "%Y-%m-%d"))
        event = core_factory.CTDEventFactory(trip=trip, event_id=1)

        url = reverse("core:form_btl_upload_bottles", args=('default', mission.pk))
        response = self.client.post(url, {'files': [btl_file]})
        self.assertIn('Hx-Trigger', response.headers)
        self.assertEquals(response.headers['Hx-Trigger'], 'update_samples')

        samples = models.Sample.objects.using('default').all()
        self.assertTrue(samples.exists())

        soup = BeautifulSoup(response.content, "html.parser")
        root = soup.find(recursive=False)
        self.assertIsNotNone(root)
        self.assertIn('hx-trigger', root.attrs)
        self.assertEquals(root.attrs['hx-trigger'], 'load')

        self.assertIn('hx-get', root.attrs)
        self.assertEquals(root.attrs['hx-get'], reverse('core:form_btl_reload_files', args=('default', mission.pk)))

        self.assertIn('hx-target', root.attrs)
        self.assertEquals(root.attrs['hx-target'], '#div_id_card_bottle_load')

    @tag('form_btl_load_test_choose_btl_directory_post')
    def test_choose_btl_directory_post(self):
        # providing a new directory as part of the post request should return an updated version
        # of the bottle load card containing the new address and any bottles in the provided
        # directory

        btl_directory = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
        mission = core_factory.MissionFactory(bottle_directory=os.path.join("c:", "nowhere"))
        url = reverse("core:form_btl_choose_bottle_dir", args=('default', mission.pk))
        response = self.client.post(url, {"dir_field": btl_directory})

        soup = BeautifulSoup(response.content, 'html.parser')

        input = soup.find(id="id_dir_field")
        self.assertEquals(input.attrs['value'], btl_directory)
