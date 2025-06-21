from django.test import TestCase, tag
from dart.forms.mission_list_filter_form import MissionListFilterForm


@tag('mission_list_filter_form')
class TestMissionListFilterForm(TestCase):
    def test_valid_form(self):
        form = MissionListFilterForm(data={
            'mission_name': 'Apollo',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
        })
        self.assertTrue(form.is_valid())

    def test_empty_form(self):
        form = MissionListFilterForm(data={})
        self.assertTrue(form.is_valid())

    def test_invalid_date(self):
        form = MissionListFilterForm(data={
            'mission_name': 'Apollo',
            'start_date': 'invalid-date',
            'end_date': '2024-12-31',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('start_date', form.errors)
