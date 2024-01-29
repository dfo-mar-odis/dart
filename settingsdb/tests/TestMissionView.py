import os.path
import shutil

from bs4 import BeautifulSoup
from django.test import tag, Client
from django.db import connections
from django.urls import reverse

from dart2.tests.DartTestCase import DartTestCase

from core import models as core_models
from core.tests import CoreFactoryFloor as core_factory

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
        (settingsdb := settings_models.LocalSetting(database_location=fake_location)).save()
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
                    connection.close()

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

        soup = BeautifulSoup(response.content)

        # we're using a hx-target/hx-swap in the mission_filter.html template so we're just returning what will
        # be swapped onto the page under the tables.
        trs = soup.find_all('tr')
        self.assertEquals(len(trs), 1)

        mission_row = soup.find(id=f"tr_id_mission_{self.mission.pk}")
        self.assertIsNotNone(mission_row)

        edit_mission_url = reverse("core:mission_edit", args=(fake_db_name, self.mission.pk))
        edit_settings_link = mission_row.find('a', id="a_id_edit_mission")
        self.assertEquals(edit_settings_link.attrs['href'], edit_mission_url)

        edit_events_url = reverse("core:mission_events_details", args=(fake_db_name, self.mission.pk))
        edit_events_link = mission_row.find('a', id="a_id_edit_mission_events")
        self.assertEquals(edit_events_link.attrs['href'], edit_events_url)

