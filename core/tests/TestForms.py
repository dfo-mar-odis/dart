from bs4 import BeautifulSoup
from django.template.loader import render_to_string
from django.test import tag, Client
from render_block import render_block_to_string

from dart2.tests.DartTestCase import DartTestCase
from core import forms

import logging

logger = logging.getLogger("dart.test")


@tag('forms', 'form_sample_config')
class TestSampleFileConfiguration(DartTestCase):

    def setUp(self) -> None:
        self.template_name = 'core/partials/form_sample_type.html'
        self.form_block = "file_config_form_block"
        self.initial = {'get_post_url': ''}
        # if field choices are supplied the sample, value, flag and replicate fields should all be selection fields
        self.field_choices = [(i, f"Choice ({i})") for i in range(10)]

    def test_form_required_initial_args(self):
        try:
            forms.SampleFileConfigurationForm()
            self.fail("An exception should have been raised for missing arguments")
        except KeyError as ex:
            self.assertEquals(ex.args[0]["message"], "missing initial \"file_type\"")

        try:
            forms.SampleFileConfigurationForm(initial={})
            self.fail("An exception should have been raised for missing arguments")
        except KeyError as ex:
            self.assertEquals(ex.args[0]["message"], "missing initial \"file_type\"")

    def test_form_exists(self):
        initial = self.initial
        initial['file_type'] = 'csv'

        file_form = forms.SampleFileConfigurationForm(field_choices=self.field_choices, initial=initial)

        context = {"file_form": file_form}
        html = render_block_to_string(self.template_name, self.form_block, context=context)

        soup = BeautifulSoup(html, 'html.parser')
        logger.debug(soup)
        form = soup.find(id="id_form_file_configuration")

        self.assertIsNotNone(form)

    def test_input_choice_fields_csv(self):
        # a file has been chosen, now the input fields should be visible to the user
        initial = self.initial
        initial['get_post_url'] = ""

        # if the file has been chosen, pass the file type to the form. This should enable a different layout
        # based on the type of file
        initial['file_type'] = 'csv'

        file_form = forms.SampleFileConfigurationForm(field_choices=self.field_choices, initial=initial)

        context = {"file_form": file_form}
        html = render_block_to_string(self.template_name, self.form_block, context=context)

        soup = BeautifulSoup(html, 'html.parser')
        logger.debug(soup)

    def test_input_fields_csv(self):
        # a file has been chosen, now the input fields should be visible to the user
        initial = self.initial
        initial['get_post_url'] = ""

        # if the file has been chosen, pass the file type to the form. This should enable a different layout
        # based on the type of file
        initial['file_type'] = 'csv'

        file_form = forms.SampleFileConfigurationForm(field_choices=self.field_choices, initial=initial)

        context = {"file_form": file_form}
        html = render_block_to_string(self.template_name, self.form_block, context=context)

        soup = BeautifulSoup(html, 'html.parser')
        logger.debug(soup)
        div = soup.find(id="div_id_file_attributes")
        self.assertIsNotNone(div)

        expected_ids = ["sample_field", "value_field", "flag_field", "replicate_field",
                        "file_type", "header", "comment_field"]

        for field in expected_ids:
            self.assertIsNotNone(div.find(id=f"id_{field}"), f"Could not find id field id_{field}")

    def test_input_fields_xls(self):
        # a file has been chosen, now the input fields should be visible to the user
        initial = self.initial
        initial['get_post_url'] = ""

        # if the file has been chosen, pass the file type to the form. This should enable a different layout
        # based on the type of file
        initial['file_type'] = 'xls'

        file_form = forms.SampleFileConfigurationForm(field_choices=self.field_choices, initial=initial)

        context = {"file_form": file_form}
        html = render_block_to_string(self.template_name, self.form_block, context=context)

        soup = BeautifulSoup(html, 'html.parser')
        logger.debug(soup)
        div = soup.find(id="div_id_file_attributes")
        self.assertIsNotNone(div)

        expected_ids = ["sample_field", "value_field", "flag_field", "replicate_field",
                        "file_type", "tab", "header", "comment_field"]

        for field in expected_ids:
            self.assertIsNotNone(div.find(id=f"id_{field}"), f"Could not find id field id_{field}")


@tag('forms', 'form_sample_type')
class TestSampleTypeForm(DartTestCase):

    def setUp(self) -> None:
        self.template_name = 'core/partials/form_sample_type.html'
        self.form_block = "sample_type_form_block"
        self.initial = {'get_post_url': ''}

    def test_form_exists(self):
        form = forms.SampleTypeForm()

        context = {"sample_type_form": form}
        html = render_block_to_string(self.template_name, self.form_block, context=context)

        soup = BeautifulSoup(html, 'html.parser')
        logger.debug(soup)

        self.assertIsNotNone(soup.find(id="div_id_sample_type_form"))

    def test_form_fields(self):
        # the form should have a datatype filter field on it that can help filter down the 'id_datatype' select
        form = forms.SampleTypeForm()

        context = {"sample_type_form": form}
        html = render_block_to_string(self.template_name, self.form_block, context=context)

        soup = BeautifulSoup(html, 'html.parser')
        logger.debug(soup)

        expected_input_fields = ['short_name', 'long_name', 'priority', 'comments']
        for field in expected_input_fields:
            self.assertIsNotNone(soup.find(id=f"id_{field}"), f"Could not find id field id_{field}")

    def test_form_fields_sample_name(self):
        # if a sample name is provided as an argument then all fields should be post fixed with the sample_name
        expected_sample_name = "oxy"
        form = forms.SampleTypeForm(sample_name=expected_sample_name)

        context = {"sample_type_form": form}
        html = render_block_to_string(self.template_name, self.form_block, context=context)

        soup = BeautifulSoup(html, 'html.parser')
        logger.debug(soup)

        expected_input_fields = ['short_name', 'long_name', 'priority', 'comments']
        for field in expected_input_fields:
            self.assertIsNotNone(soup.find(id=f"id_{field}_{expected_sample_name}"),
                                 f"Could not find id field id_{field}_{expected_sample_name}")

    def test_datatype_filter(self):
        # the form should have a datatype filter field on it that can help filter down the 'id_datatype' select
        form = forms.SampleTypeForm()

        context = {"sample_type_form": form}
        html = render_block_to_string(self.template_name, self.form_block, context=context)

        soup = BeautifulSoup(html, 'html.parser')
        logger.debug(soup)

        input_datatype_filter = soup.find("input", {"id": "id_datatype_filter"})
        self.assertIsNotNone(input_datatype_filter)