import os.path
import shutil
import time

from bs4 import BeautifulSoup
from django.test import tag, Client
from django.db import connections, close_old_connections
from django.urls import reverse
from django.conf import settings

from dart.tests.DartTestCase import DartTestCase

from core import models as core_models

from settingsdb import models as settings_models
from settingsdb import utils

fake_location = "./test_db"
fake_db_name = 'fake_db'


@tag("mission_view")
class TestMissionView(DartTestCase):

    # tough to simulate testing for dynamic database loading, but in the setUpClass function
    # we'll create the fake database then in tearDownClass we'll close the connections and delete the fake folder
    # We're doing this in the xxxClass rather than the regular setUp and tearDown so the database migrations
    # won't be run on every single test. It runs once, all the tests are run, then the database is destroyed

    @classmethod
    def setUpClass(cls):
        (settingsdb := settings_models.LocalSetting(database_location=fake_location, connected=True)).save()
        utils.add_database(fake_db_name)

        core_models.Mission(name=fake_db_name).save(using=fake_db_name)

    @classmethod
    def tearDownClass(cls):
        # by using 'delete_db = True' or 'delete_db = False' we can keep a database if we're going to be doing
        # a lot of testing, because running migrations takes a long time... if using 'delete_db = False' you'll
        # have to remember to manually delete the database or swap this to 'delete_db = True' after the testing
        # is complete.
        delete_db = True
        if delete_db:
            for connection in connections.all():
                if connection.alias == fake_db_name:
                    settings.DATABASES.pop(connection.alias)
                    connection.close()

                    time.sleep(2)  # wait a couple of seconds to make sure the connection is closed

                    if os.path.isdir(fake_location):
                        shutil.rmtree(fake_location)

    def setUp(self) -> None:
        self.client = Client()
        self.mission = core_models.Mission.objects.using(fake_db_name).first()

    @tag("mission_view_test_list_missions_get")
    def test_list_missions_get(self):
        # upon loading the "settingsdb/mission_filter.html" a get request is made to the list missions address
        # that will return table rows for each mission available in the LocalSettings database_location

        url = reverse("settingsdb:mission_filter_list_missions")
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')

        # we're using a hx-target/hx-swap in the mission_filter.html template so we're just returning what will
        # be swapped onto the page under the tables. There should be 2 table rows, one for the headings, one for the
        # mission
        trs = soup.find_all('tr')
        self.assertEquals(len(trs), 2)

        mission_row = soup.find(id=f"tr_id_mission_{self.mission.name}")
        self.assertIsNotNone(mission_row)

        edit_mission_url = reverse("core:mission_edit", args=(fake_db_name, self.mission.pk))
        edit_settings_link = mission_row.find('a', id="a_id_edit_mission")
        self.assertEquals(edit_settings_link.attrs['href'], edit_mission_url)

        edit_events_url = reverse("core:mission_events_details", args=(fake_db_name, self.mission.pk))
        edit_events_link = mission_row.find('a', id="a_id_edit_mission_events")
        self.assertEquals(edit_events_link.attrs['href'], edit_events_url)


@tag("mission_view", "mission_view_ui")
class TestMissionViewUI(DartTestCase):

    def setUp(self) -> None:
        self.client = Client()

    @tag("mission_view_ui_test_missions_directory")
    def test_missions_directory(self):
        # the mission view page should have a drop down showing the user the directory the application is
        # pointing to to view the mission databases.

        url = reverse("settingsdb:mission_filter")
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")
        mission_select = soup.find(id="select_id_mission_directory")
        self.assertIsNotNone(mission_select)

        # the selection element needs to have an hx-trigger="changed" on it
        self.assertIn('hx-trigger', mission_select.attrs)
        self.assertEquals(mission_select.attrs['hx-trigger'], 'change')

        self.assertIn('hx-get', mission_select.attrs)
        self.assertEquals(mission_select.attrs['hx-get'], reverse('settingsdb:update_mission_directory'))

        self.assertIn('hx-swap', mission_select.attrs)
        self.assertEquals(mission_select.attrs['hx-swap'], 'outerHTML')

    @tag("mission_view_ui_test_missions_directory_update_get")
    def test_missions_directory_update_get(self):
        # if the user selects the (-1, ---- New ----) option the update mission directory url should be called
        # with a get request that returns a text field and a submit button the user can then paste a location
        # into

        url = reverse("settingsdb:update_mission_directory")
        response = self.client.get(url, {'directory': -1})

        soup = BeautifulSoup(response.content)
        self.assertIsNotNone(soup)

        self.assertIsNotNone(soup)
        self.assertIsNotNone(soup.find(id="id_directory_field"))

        # The button should point to the same url used for the get request, but should use 'hx-post' instead
        button = soup.find("button", attrs={'name': "update_mission_directory"})
        self.assertIsNotNone(button)
        self.assertIn('hx-post', button.attrs)

    @tag("mission_view_ui_test_missions_directory_update_post")
    def test_missions_directory_update_post(self):
        # upon submission the update mission directory url should return the new selection UI with the newly
        # added directory selected
        url = reverse("settingsdb:update_mission_directory")
        new_directory = r"C:\new_location\\"
        response = self.client.post(url, {'directory': new_directory})

        options = settings_models.LocalSetting.objects.using('default').filter(database_location__iexact=new_directory)
        self.assertTrue(options.exists())
        pass

