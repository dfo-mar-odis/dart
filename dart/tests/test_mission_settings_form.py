from bs4 import BeautifulSoup
from django.test import TestCase, RequestFactory

from unittest.mock import patch

from django.urls import reverse

from dart.forms.mission_settings_form import MissionSettingsForm, get_region_list, new_geographic_regions, \
    show_selected_regions, delete_geographic_region
from dart.tests import DartModelFactoryFloor as DartFactory

class TestMissionSettingsForm(TestCase):
    def test_valid_form(self):
        form = MissionSettingsForm(data={
            'name': 'Mission1',
            'geographic_region': 'Test Region',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'lead_scientist': 'Upson, Patrick',
            'platform': 'RSS Discovery',
            'protocol': 'AZMP',
            'data_center': 20
        })
        self.assertTrue(form.is_valid())

    def test_invalid_name(self):
        form = MissionSettingsForm(data={
            'name': 'Invalid Name!',
            'mission_descriptor': 'Test mission',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_start_date_after_end_date(self):
        form = MissionSettingsForm(data={
            'name': 'Mission2',
            'mission_descriptor': 'Test mission',
            'start_date': '2024-12-31',
            'end_date': '2024-01-01',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('start_date', form.errors)

    def test_missing_required_fields(self):
        form = MissionSettingsForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        self.assertIn('geographic_region', form.errors)
        self.assertIn('start_date', form.errors)
        self.assertIn('end_date', form.errors)

    def test_invalid_date_format(self):
        form = MissionSettingsForm(data={
            'name': 'Mission3',
            'mission_descriptor': 'Test mission',
            'start_date': '2024/01/01',
            'end_date': '2024-12-31',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('start_date', form.errors)


class TestGeographicRegionHelpers(TestCase):
    def setUp(self):
        self.region1 = DartFactory.GlobalGeographicRegionFactory(name="Region A")
        self.region2 = DartFactory.GlobalGeographicRegionFactory(name="Region B")
        self.factory = RequestFactory()

    @patch('dart.forms.mission_settings_form.render_to_string')
    def test_get_region_list_renders_options(self, mock_render):
        mock_render.return_value = '<select id="global_geographic_region_select"></select>'

        soup = get_region_list(selected=self.region2.pk)
        select = soup.find('select', id='global_geographic_region_select')
        options = select.find_all('option')

        self.assertTrue(any(opt.string == 'Region A' for opt in options))
        self.assertTrue(any(opt.string == 'Region B' for opt in options))
        selected_option = select.find('option', {'selected': 'selected'})
        self.assertIsNotNone(selected_option)
        self.assertEqual(selected_option['value'], self.region2.pk)

    def test_new_geographic_regions_get(self):
        request = self.factory.get(reverse("dart:form_mission_new_geographic_region"),
                                   {"global_geographic_region": "0"})
        response = new_geographic_regions(request)
        soup = BeautifulSoup(response.content, "html.parser")

        # Check for add button
        add_btn = soup.find("button", id="btn_id_add_div_id_global_geographic_region_select")
        self.assertIsNotNone(add_btn)

        # Check for delete/cancel button
        cancel_btn = soup.find("button", id="btn_id_cancel_div_id_global_geographic_region_select")
        self.assertIsNotNone(cancel_btn)

        # Check for text input
        text_input = soup.find("input", id="input_id_field_div_id_global_geographic_region_select")
        self.assertIsNotNone(text_input)

    def test_post_new_geographic_regions_returns_geographic_region_section(self):
        url = reverse("dart:form_mission_new_geographic_region")
        region_value = f"{self.region1.name}, {self.region2.name}"
        data = {"geographic_region": region_value}

        request = self.factory.post(url, data)
        response = new_geographic_regions(request)
        soup = BeautifulSoup(response.content, "html.parser")
        region_section = soup.find(id="div_id_geographic_region_section")
        self.assertIsNotNone(region_section)

        # Check input field value
        input_field = soup.find("input", {"name": "geographic_region"})
        self.assertIsNotNone(input_field)
        self.assertEqual(input_field.get("value"), region_value)

        # Check for badges
        badges = soup.find_all("span", class_="badge bg-secondary")
        self.assertEqual(len(badges), 2)
        badge_texts = [badge.get_text(strip=True).replace("Delete selected region(s)", "").strip() for badge in badges]
        self.assertIn(self.region1.name, badge_texts)
        self.assertIn(self.region2.name, badge_texts)

        # Check for delete buttons inside badges
        for badge, region_name in zip(badges, [self.region1.name, self.region2.name]):
            btn = badge.find("button", {"name": "delete", "value": region_name})
            self.assertIsNotNone(btn)
            self.assertEqual(btn["type"], "button")
            self.assertEqual(btn["title"], "Delete selected region(s)")
            self.assertEqual(btn["hx-post"], "/mission/geographic_regions/delete/")

    def test_post_with_new_global_region_select(self):
        region = DartFactory.GlobalGeographicRegionFactory(name="Region C")
        url = reverse("dart:form_mission_new_geographic_region")
        region_names = ["Region C"]
        data = {
            "new_global_region": "Region C",
        }
        request = self.factory.post(url, data)
        response = new_geographic_regions(request)
        soup = BeautifulSoup(response.content, "html.parser")
        # Check that the region appears in the response (e.g., as a badge or in the input)
        self.assertIn("Region C", soup.text)

        # Check for badges
        badges = soup.find_all("span", class_="badge bg-secondary")
        self.assertEqual(len(badges), 1)
        badge_texts = [badge.get_text(strip=True).replace("Delete selected region(s)", "").strip() for badge in badges]
        self.assertIn(region.name, badge_texts)

        # Check for delete buttons inside badges
        for badge, region_name in zip(badges, [region.name]):
            btn = badge.find("button", {"name": "delete", "value": region_name})
            self.assertIsNotNone(btn)
            self.assertEqual(btn["type"], "button")
            self.assertEqual(btn["title"], "Delete selected region(s)")
            self.assertEqual(btn["hx-post"], "/mission/geographic_regions/delete/")

    def test_post_new_geographic_regions_too_many_regions_shows_error(self):
        # Create five regions
        regions = [
            DartFactory.GlobalGeographicRegionFactory(name=f"Region {i}") for i in range(1, 6)
        ]
        region_value = ", ".join(region.name for region in regions)
        url = reverse("dart:form_mission_new_geographic_region")
        data = {"geographic_region": region_value}

        request = self.factory.post(url, data)
        response = new_geographic_regions(request)
        soup = BeautifulSoup(response.content, "html.parser")

        # Check for error in the correct div
        error_div = soup.find("div", id="div_id_geographic_region_errors")
        self.assertIsNotNone(error_div)
        self.assertIn("Maximum of four regions", error_div.text)

    def test_post_new_geographic_regions_add_too_many_regions_shows_error(self):
        # Create five regions
        regions = [
            DartFactory.GlobalGeographicRegionFactory(name=f"Region {i}") for i in range(1, 5)
        ]
        region_value = ", ".join(region.name for region in regions)
        url = reverse("dart:form_mission_new_geographic_region")
        data = {"geographic_region": region_value, "new_global_region": "Region C"}

        request = self.factory.post(url, data)
        response = new_geographic_regions(request)
        soup = BeautifulSoup(response.content, "html.parser")

        # Check for error in the correct div
        error_div = soup.find("div", id="div_id_geographic_region_errors")
        self.assertIsNotNone(error_div)
        self.assertIn("Maximum of four regions", error_div.text)

    def test_post_new_geographic_regions_too_many_characters_shows_error(self):
        # Create four regions with long names to exceed 100 characters in total
        regions = [
            DartFactory.GlobalGeographicRegionFactory(name="Region_" + "A" * 40),
            DartFactory.GlobalGeographicRegionFactory(name="Region_" + "B" * 40),
            DartFactory.GlobalGeographicRegionFactory(name="Region_" + "C" * 40),
        ]
        region_value = ", ".join(region.name for region in regions)
        url = reverse("dart:form_mission_new_geographic_region")
        data = {"geographic_region": region_value}

        request = self.factory.post(url, data)
        response = new_geographic_regions(request)
        soup = BeautifulSoup(response.content, "html.parser")

        # Check for error in the correct div
        error_div = soup.find("div", id="div_id_geographic_region_errors")
        self.assertIsNotNone(error_div)
        self.assertIn("Too many characters in region list", error_div.text)

    def test_post_new_geographic_regions_add_too_many_characters_shows_error(self):
        # Create four regions with long names to exceed 100 characters in total
        regions = [
            DartFactory.GlobalGeographicRegionFactory(name="Region_" + "A" * 40),
            DartFactory.GlobalGeographicRegionFactory(name="Region_" + "B" * 40),
        ]
        region_value = ", ".join(region.name for region in regions)
        url = reverse("dart:form_mission_new_geographic_region")
        data = {"geographic_region": region_value, "new_global_region": "Region_" + "C" * 40}

        request = self.factory.post(url, data)
        response = new_geographic_regions(request)
        soup = BeautifulSoup(response.content, "html.parser")

        # Check for error in the correct div
        error_div = soup.find("div", id="div_id_geographic_region_errors")
        self.assertIsNotNone(error_div)
        self.assertIn("Too many characters in region list", error_div.text)

    def test_show_selected_regions_displays_selected_badges(self):
        # Assume show_selected_regions takes a request with 'geographic_region' data
        region1 = DartFactory.GlobalGeographicRegionFactory(name="Region X")
        region2 = DartFactory.GlobalGeographicRegionFactory(name="Region Y")
        region_value = f"{region1.name}, {region2.name}"
        url = reverse("dart:form_mission_show_selected_geographic_regions")
        data = {"geographic_region": region_value}

        request = self.factory.post(url, data)
        response = show_selected_regions(request)
        soup = BeautifulSoup(response.content, "html.parser")

        # Check that badges for both regions are present
        badges = soup.find_all("span", class_="badge bg-secondary")
        badge_texts = [badge.get_text(strip=True).replace("Delete selected region(s)", "").strip() for badge in badges]
        self.assertIn(region1.name, badge_texts)
        self.assertIn(region2.name, badge_texts)

        # Check that the input field contains the correct value
        for badge, region_name in zip(badges, [region1, region2]):
            btn = badge.find("button", {"name": "delete", "value": region_name})
            self.assertIsNotNone(btn)
            self.assertEqual(btn["type"], "button")
            self.assertEqual(btn["title"], "Delete selected region(s)")
            self.assertEqual(btn["hx-post"], "/mission/geographic_regions/delete/")

    def test_delete_geographic_region_removes_region(self):
        url = reverse("dart:form_mission_delete_geographic_region")
        data = {
            "global_geographic_region": self.region1.pk,
            "geographic_region": f"{self.region1.name},{self.region2.name}",
            "delete": self.region1.name,
        }
        request = self.factory.post(url, data)
        response = delete_geographic_region(request)
        soup = BeautifulSoup(response.content, "html.parser")

        # Region1 should be deleted from DB
        from dart.forms import mission_settings_form
        self.assertFalse(mission_settings_form.user_models.GlobalGeographicRegion.objects.filter(pk=self.region1.pk).exists())

        # Badge for region1 should not be present
        badges = soup.find_all("span", class_="badge bg-secondary")
        badge_texts = [badge.get_text(strip=True).replace("Delete selected region(s)", "").strip() for badge in badges]
        self.assertNotIn(self.region1.name, badge_texts)
        self.assertIn(self.region2.name, badge_texts)

    def test_delete_geographic_region_only_removes_selected(self):
        url = reverse("dart:form_mission_delete_geographic_region")
        data = {
            "global_geographic_region": self.region2.pk,
            "geographic_region": f"{self.region1.name},{self.region2.name}",
            "delete": self.region2.name,
        }
        request = self.factory.post(url, data)
        response = delete_geographic_region(request)
        soup = BeautifulSoup(response.content, "html.parser")

        # Only region2 should be deleted from DB
        from dart.forms import mission_settings_form
        self.assertFalse(mission_settings_form.user_models.GlobalGeographicRegion.objects.filter(pk=self.region2.pk).exists())
        self.assertTrue(mission_settings_form.user_models.GlobalGeographicRegion.objects.filter(pk=self.region1.pk).exists())

        # Badge for region2 should not be present
        badges = soup.find_all("span", class_="badge bg-secondary")
        badge_texts = [badge.get_text(strip=True).replace("Delete selected region(s)", "").strip() for badge in badges]
        self.assertNotIn(self.region2.name, badge_texts)
        self.assertIn(self.region1.name, badge_texts)

    def test_delete_geographic_region_with_no_selected_regions(self):
        url = reverse("dart:form_mission_delete_geographic_region")
        data = {
            "global_geographic_region": self.region1.pk,
        }
        request = self.factory.post(url, data)
        response = delete_geographic_region(request)
        soup = BeautifulSoup(response.content, "html.parser")

        # Region1 should be deleted from DB
        from dart.forms import mission_settings_form
        self.assertFalse(mission_settings_form.user_models.GlobalGeographicRegion.objects.filter(pk=self.region1.pk).exists())

        # No badges should be present
        badges = soup.find_all("span", class_="badge bg-secondary")
        self.assertEqual(len(badges), 0)