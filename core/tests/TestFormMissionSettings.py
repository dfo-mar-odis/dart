from bs4 import BeautifulSoup
from django.test import tag, Client
from django.urls import reverse

from dart.tests.DartTestCase import DartTestCase

from core import models as core_models
from core import form_mission_settings


@tag('forms', 'form_mission_settings')
class TestFormMissionSettings(DartTestCase):

    def setUp(self):
        self.client = Client()

    @tag("form_mission_settings_test_entry_point")
    def test_entry_point(self):
        # The mission settings form is accessed though the MissionCreateView and MissionUpdateView

        url = reverse("core:mission_new")
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")
        self.assertIsNotNone(soup)

        form = soup.find("form")
        self.assertIsNotNone(form)

        mission_name_field = form.find("input", {"name": "name"})
        self.assertIsNotNone(mission_name_field)

        geographic_region_field = form.find(id="div_id_geographic_region_field")
        self.assertIsNotNone(mission_name_field)

        mission_descriptor_field = form.find("input", {"name": "mission_descriptor"})
        self.assertIsNotNone(mission_descriptor_field)

        lead_scientist_field = form.find("input", {"name": "lead_scientist"})
        self.assertIsNotNone(lead_scientist_field)

        data_center_field = form.find("select", {"name": "data_center"})
        self.assertIsNotNone(data_center_field)

