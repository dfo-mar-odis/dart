import os

from bs4 import BeautifulSoup
from django.urls import reverse

from bio_tables import models as bio_models
from core import models as core_models
from core.tests import CoreFactoryFloor
from dart2 import settings
from dart2.tests.DartTestCase import DartTestCase

from django.test import tag, Client

import logging

logger = logging.getLogger('dart.test')


@tag("views", "forms", "sample_type_form_view")
class TestSampleTypeFormView(DartTestCase):

    def setUp(self) -> None:
        self.mission = CoreFactoryFloor.MissionFactory()
        self.client = Client()
        self.url = reverse("core:load_sample_type")
        self.form_submit_url = reverse("core:load_sample_type", args=(self.mission.pk,))
        self.file_location = os.path.join(settings.BASE_DIR, 'core/tests/sample_data/')

    def test_url_response(self):
        # test the initial response which should just be the file input dialog
        response = self.client.get(self.url)

        self.assertEquals(response.status_code, 200)

        soup = BeautifulSoup(response.content)

        logger.debug(soup)
        self.assertIsNotNone(soup.find("input", {"id": "id_input_sample_file"}))

        # at this point the response should only have a form with the file input field on it.
        swap_div = soup.find(id="div_id_sample_type")
        self.assertIsNotNone(swap_div)
        self.assertEquals(len(swap_div.findChildren()), 0)

    def test_csv_file_change(self):
        # test the response if a file has been provided, in this case the csv version of the SampleFileSettings form
        # should be returned
        file_name = 'sample_oxy.csv'

        with open(self.file_location + file_name, 'rb') as fp:
            response = self.client.post(self.url, {'sample_file': fp})

        self.assertEquals(response.status_code, 200)

        soup = BeautifulSoup(response.content)

        logger.debug(soup)
        file_input = soup.find(id="id_input_sample_file")
        # at this point the response should only have a form with the file input field on it.
        swap_div = soup.find(id="div_id_sample_type")
        self.assertIsNotNone(swap_div)
        self.assertGreater(len(swap_div.findChildren()), 0)

    def test_csv_file_valid_details(self):
        # test that provided valid details with a csv file the form returns to its initial state with just
        # the file input
        file_name = 'sample_oxy.csv'
        bc_datatype = bio_models.BCDataType.objects.get(pk=90000007)
        expected_short_name = 'oxy'
        expected_sample_field = "Sample"
        expected_value_field = "O2_Concentration(ml/l)"
        details = {'short_name': expected_short_name, 'sample_type_name': 'Oxygen', 'priority': 1,
                   'data_type': bc_datatype, 'file_config_name': 'csv - oxy', 'file_type': 'csv', 'header': 9,
                   'sample_field': expected_sample_field, 'value_field': expected_value_field}

        with open(self.file_location + file_name, 'rb') as fp:
            details['sample_file'] = fp
            response = self.client.post(self.form_submit_url, details)

        self.assertEquals(response.status_code, 200)

        soup = BeautifulSoup(response.content)

        logger.debug(soup)
        self.assertIsNotNone(soup.find("input", {"id": "id_input_sample_file"}))

        # at this point the response should only have a form with the file input field on it.
        swap_div = soup.find(id="div_id_sample_type")
        self.assertIsNotNone(swap_div)
        self.assertEquals(len(swap_div.findChildren()), 0)

        # The objects related to the sample data should also exist at this point
        sample_type = core_models.SampleType.objects.get(short_name=expected_short_name)
        self.assertIsNotNone(sample_type)

        config = sample_type.sample_file_configs.filter(file_type='csv', sample_field__exact=expected_sample_field,
                                                        value_field__exact=expected_value_field)
        self.assertTrue(config.exists())
