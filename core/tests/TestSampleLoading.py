from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag, Client
from django.urls import reverse_lazy

from config.tests.DartTestCase import DartTestCase
from core.parsers.samples.samplefile_config import FileConfig


@tag('test_file_config_form')
class TestConfigForm(DartTestCase):
    def setUp(self):
        self.client = Client()
        self.sample_data_path = Path('.', 'core', 'tests', 'sample_data', 'sample_loader')

        self.file_name = 'oxygen.xlsx'
        file_path = Path(self.sample_data_path, self.file_name)

        with open(file_path, 'br') as f:
            self.file = SimpleUploadedFile(self.file_name, f.read())

    def test_base_form(self):
        # provided a file a form should be returned with the sample column and comment columns selected
        context = {
            'sample_file': self.file,
            'file_tab': 1
        }
        url = reverse_lazy('core:form_sample_type_get_headers')
        response = self.client.post(url, context)

        soup = BeautifulSoup(response.content, 'html.parser')

        tab_input = soup.find(id="id_file_tab")
        assert tab_input is not None, "Missing expected tab input"

        selected_tab = tab_input.find('option', attrs={'selected':''})
        assert selected_tab.attrs['value'] == '1', f"incorrect tab selected {selected_tab.attrs['value']}"

        header_line = soup.find(id="id_header_line_number")
        assert tab_input is not None, "Missing expected header line input"

        header_line_no = header_line.attrs['value']
        assert header_line_no == '10', f"incorrect header line selected {header_line_no}"

        sample_column = soup.find(id="id_sample_column")
        assert sample_column is not None, "Missing expected sample column input"

        sample_column_selected = sample_column.find('option', attrs={'selected':''})
        assert sample_column_selected.attrs['value'] == '0', f"incorrect sample column selected {sample_column_selected.attrs['value']}"
        assert sample_column_selected.string == 'Sample', f"incorrect sample column text {sample_column_selected.string }"

        comment_column = soup.find(id="id_comment_column")
        assert comment_column is not None, "Missing expected sample column input"

        comment_column_selected = comment_column.find('option', attrs={'selected': ''})
        assert comment_column_selected.attrs['value'] == '15', f"incorrect comment column selected {comment_column_selected.attrs['value']}"
        assert comment_column_selected.string == 'Comments', f"incorrect comment column text {comment_column_selected.string }"

    def test_add_value_to_config(self):
        # Provided a file and column information, a table entry should be added to the table_id_column_configuration_table
        context = {
            'sample_file': self.file,
            'file_tab': 1,
            'value_column': 2,
            'name_column': 'oxy',
            'datatype': 90000002
        }
        url = reverse_lazy('core:form_sample_type_add_to_config')
        response = self.client.post(url, context)

        soup = BeautifulSoup(response.content, 'html.parser')
        table_entry = soup.find(id=f"config_{context['value_column']}")
        assert table_entry is not None, "Missing expected table entry"

    def test_update_value_to_config(self):
        # Provided a file and column information, a table entry should be updated in the
        # table_id_column_configuration_table if it a config row already exists
        volume_column_id = 2
        config_prefix = f'config_{volume_column_id}'
        context = {
            'sample_file': self.file,
            'file_tab': 1,

            # New values being set
            'value_column': volume_column_id,
            'name_column': 'oxy',
            'datatype': 90000002,

            # These are the original values that would have been previously created
            f'{config_prefix}': volume_column_id,
            f'{config_prefix}_value_column': 'O2_Concentration(ml/l)',
            f'{config_prefix}_name_column': '',
            f'{config_prefix}_datatype': 90000001
        }
        url = reverse_lazy('core:form_sample_type_update_to_config')
        response = self.client.post(url, context)

        soup = BeautifulSoup(response.content, 'html.parser')
        table_entry = soup.find(id=config_prefix)
        assert table_entry is not None, "Missing expected table entry"

        tds = table_entry.find_all('td')
        tds.pop(0) # first entry is the button column
        td_strings = [td.string for td in tds]
        assert td_strings == ["O2_Concentration(ml/l)", "oxy", "90000002", "Salinity_CTD", "Salinity / CTD"], f"incorrect table entry {td_strings}"

    def test_update_value_form(self):
        # provided a file, the value form should be able to be populated from an existing config table element

        volume_column_id = 2
        config_prefix = f'config_{volume_column_id}'

        context = {
            'sample_file': self.file,
            'file_tab': 1,

            # These are the original values that would have been previously created
            f'{config_prefix}': volume_column_id,
            f'{config_prefix}_value_column': 'O2_Concentration(ml/l)',
            f'{config_prefix}_name_column': '',
            f'{config_prefix}_datatype': 90000001
        }

        url = reverse_lazy('core:form_sample_type_get_value_form', args=[volume_column_id])
        # has to be done as a POST request because the file involved doesn't get passed when using a GET request
        response = self.client.post(url, context)
        soup = BeautifulSoup(response.content, 'html.parser')

        value_input = soup.find(id="id_value_column")
        assert value_input is not None, "Missing expected value input"

        selected_value_input = value_input.find('option', attrs={'selected': ''})
        assert selected_value_input is not None, "Missing expected value input"
        assert selected_value_input.attrs['value'] == '2'


@tag('test_file_config')
class TestFileConfigObject(TestCase):

    def setUp(self):
        self.sample_data_path = Path('.', 'core', 'tests', 'sample_data', 'sample_loader')

    def test_get_header_line_number_csv(self):
        # provided a csv file that contains some metadata the file config object should be able to find
        # the header details on line 9
        file_name = 'oxygen.csv'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config, "File config was not created"

        assert file_config.get_header_line_number() == 9, f"Header line number was not correct, expected 9 but got {file_config.get_header_line_number()}"

    def test_user_set_header_line_number_csv(self):
        # if the user sets a header line, that value should be used to locate the header
        expected_line_number = 1

        file_name = 'oxygen.csv'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))
            file_config.set_header_line_number(expected_line_number)

        assert file_config, "File config was not created"
        assert file_config.get_header_line_number() == expected_line_number, f"Header line number was not correct, expected {expected_line_number} but got {file_config.get_header_line_number()}"

    def test_get_header_line_number_dat(self):
        # provided a dat file that contains some metadata the file config object should be able to find
        # the header details on line 9
        file_name = 'oxygen.dat'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config, "File config was not created"

        assert file_config.get_header_line_number() == 9, f"Header line number was not correct, expected 9 but got {file_config.get_header_line_number()}"

    def test_get_header_columns_csv(self):
        # provided a csv file that contains some metadata the file config object should be able to find
        # the header details on line 9, and retrieve the expected list of column names
        expected_columns = ["Sample", "Bottle#", "O2_Concentration(ml/l)", "QC", "O2_Uncertainty(ml/l)",
                            "Titrant_volume(ml)", "Titrant_uncertainty(ml)", "Analysis_date", "Data_file",
                            "Standards(ml)", "Blanks(ml)", "Bottle_volume(ml)", "Initial_transmittance(%%)",
                            "Standard_transmittance0(%%)", "Comments"]

        file_name = 'oxygen.csv'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config, "File config was not created"

        assert file_config.get_column_names() == expected_columns, f"Incorrect header:\n{file_config.get_column_names()}\n{expected_columns}"

    def test_get_header_columns_line_reset_csv(self):
        # provided a csv file that contains some metadata the file config object should be able to find
        # the header details on line 9, if the user manually sets the line number the columns for that line
        # should be retrieved
        expected_columns = ["Sample", "Bottle#", "O2_Concentration(ml/l)", "QC", "O2_Uncertainty(ml/l)",
                            "Titrant_volume(ml)", "Titrant_uncertainty(ml)", "Analysis_date", "Data_file",
                            "Standards(ml)", "Blanks(ml)", "Bottle_volume(ml)", "Initial_transmittance(%%)",
                            "Standard_transmittance0(%%)", "Comments"]

        expected_columns_2 = ["521277_1", "5048", "4.889", "0", "0.01", "2.332", "0.002", "9/29/2025 3:38",
                            "521277_1.tod", "2.009 2.008 2.008", "0.001 0.001 0.001", "134.476", "0", "0", ""]

        file_name = 'oxygen.csv'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config, "File config was not created"

        assert file_config.get_column_names() == expected_columns, f"Incorrect header:\n{file_config.get_column_names()}\n{expected_columns}"

        file_config.set_header_line_number(10)

        assert file_config.get_column_names() == expected_columns_2, f"Incorrect header:\n{file_config.get_column_names()}\n{expected_columns_2}"

    def test_get_header_line_number_xls_no_tab_provided(self):
        # provided an xlsx file and no tab, the file config object should be able to locate the header on the initial
        # tab and identify the two tabs in the file
        expected_tabs = ['Oxygen_JC28302_Final', 'RBEDITS']

        file_name = 'oxygen.xlsx'
        file = Path(self.sample_data_path, file_name)
        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config, "File config was not created"
        assert file_config.get_tab_names() == expected_tabs, f"Tab names were not correct, expected [{expected_tabs}] but got {file_config.get_tab_names()}"
        assert file_config.get_header_line_number() == 9, f"Header line number {file_config.get_header_line_number()} was not correct"

    def test_get_header_line_number_xls_with_tab_provided(self):
        # provided n xlsx file and a tab, the file config object should be able to locate
        # the header on the provided tab

        file_name = 'oxygen.xlsx'
        file = Path(self.sample_data_path, file_name)
        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()), 1)

        assert file_config, "File config was not created"
        assert file_config.get_header_line_number() == 10, f"Header line number {file_config.get_header_line_number()} was not correct"

    def test_get_header_line_number_xls_with_selected_tab(self):
        # provided a xlsx file and a tab, the file config object should be able to locate
        # the header on the provided tab
        expected_tab = 1

        file_name = 'oxygen.xlsx'
        file = Path(self.sample_data_path, file_name)
        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))
            file_config.set_selected_tab(expected_tab)

        assert file_config, "File config was not created"
        assert file_config.get_selected_tab() == expected_tab, f"Selected tab was not correct: {file_config.get_selected_tab()}"
        assert file_config.get_header_line_number() == 10, f"Header line number {file_config.get_header_line_number()} was not correct"

    def test_get_header_line_number_xls_with_selected_tab_changed(self):
        # provided a xlsx file and no tab, the file config object should be able to locate the header on the initial
        # tab, when the user changes the tab the header line should be re-identified
        expected_tabs = ['Oxygen_JC28302_Final', 'RBEDITS']

        file_name = 'oxygen.xlsx'
        file = Path(self.sample_data_path, file_name)
        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config, "File config was not created"
        assert file_config.get_header_line_number() == 9, f"Header line number {file_config.get_header_line_number()} was not correct"

        file_config.set_selected_tab(1)
        assert file_config.get_header_line_number() == 10, f"Header line number {file_config.get_header_line_number()} was not correct"

    def test_get_header_columns_xls_no_tab(self):
        # provided a xlsx file, the file config object should be able to locate
        # the header row and the column names should be saved in the config
        expected_columns = ['Sample', 'Bottle#', 'O2_Concentration(ml/l)', 'QC', 'O2_Uncertainty(ml/l)',
                            'Titrant_volume(ml)', 'Titrant_uncertainty(ml)', 'Analysis_date', 'Data_file',
                            'Standards(ml)', 'Blanks(ml)', 'Bottle_volume(ml)', 'Initial_transmittance(%%)',
                            'Standard_transmittance0(%%)', 'Comments']

        file_name = 'oxygen.xlsx'
        file = Path(self.sample_data_path, file_name)
        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config, "File config was not created"
        assert file_config.get_column_names() == expected_columns, f"Column names were not correct:\n{file_config.get_column_names()}\n{expected_columns}"

    def test_get_header_columns_xls_with_selected_tab(self):
        # provided a xlsx file, the file config object should be able to locate
        # the header row and the column names should reset if the selected tab is changed after the initial load
        expected_columns = ['Sample', 'Bottle#', 'O2_Concentration(ml/l)', 'QC', 'O2_Uncertainty(ml/l)',
                            'Titrant_volume(ml)', 'Titrant_uncertainty(ml)', 'Analysis_date', 'Data_file',
                            'Standards(ml)', 'Blanks(ml)', 'Bottle_volume(ml)', 'Initial_transmittance(%%)',
                            'Standard_transmittance0(%%)', 'Comments']

        expected_columns_2 = ['Sample', 'Bottle#', 'O2_Concentration(ml/l)', 'QC', 'DL', 'O2_Uncertainty(ml/l)',
                            'Titrant_volume(ml)', 'Titrant_uncertainty(ml)', 'Analysis_date', 'Data_file',
                            'Standards(ml)', 'Blanks(ml)', 'Bottle_volume(ml)', 'Initial_transmittance(%%)',
                            'Standard_transmittance0(%%)', 'Comments']

        file_name = 'oxygen.xlsx'
        file = Path(self.sample_data_path, file_name)
        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config, "File config was not created"
        assert file_config.get_column_names() == expected_columns, f"Column names were not correct:\n{file_config.get_column_names()}\n{expected_columns}"

        file_config.set_selected_tab(1)
        assert file_config.get_column_names() == expected_columns_2, f"Column names were not correct:\n{file_config.get_column_names()}\n{expected_columns_2}"

    def test_csv_get_sample_id_column(self):
        # Provided a CSV file we should beable to detect the sample ID column
        file_name = 'oxygen.csv'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config.get_sample_id_column() == (0, 'Sample'), f"Sample ID column was not correct {file_config.get_sample_id_column()}"

    def test_dat_get_sample_id_column(self):
        # Provided a DAT file we should beable to detect the sample ID column
        file_name = 'oxygen.dat'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config.get_sample_id_column() == (0, 'Sample'), f"Sample ID column was not correct {file_config.get_sample_id_column()}"

    def test_xls_get_sample_id_column(self):
        # Provided a XLS file we should beable to detect the sample ID column
        file_name = 'oxygen.xlsx'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))
            file_config.set_selected_tab(1)

        assert file_config.get_sample_id_column() == (0, 'Sample'), f"Sample ID column was not correct {file_config.get_sample_id_column()}"

    def test_xls_get_sample_id_column_salinity(self):
        # Provided a XLS file we should beable to detect the sample ID column
        # for a salinity file, the column 'BOTTLE LABEL' should be prioritized.
        file_name = 'salinity.xlsx'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config.get_sample_id_column() == (3, 'Bottle Label'), f"Sample ID column was not correct {file_config.get_sample_id_column()}"

    def test_xls_get_sample_id_column_nutrient(self):
        # Provided a XLS file we should beable to detect the sample ID column
        # for a nutrient file, the column 'SAMPLE_ID' should be prioritized.
        file_name = 'nutrients.xlsx'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config.get_sample_id_column() == (0, 'SAMPLE_ID'), f"Sample ID column was not correct {file_config.get_sample_id_column()}"

    def test_xls_get_sample_id_column_chlorophyll(self):
        # Provided a XLS file we should beable to detect the sample ID column
        # for a chlorophyll file, the column 'I.D.' should be prioritized.
        file_name = 'chlorophyll.xlsx'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))
            file_config.set_selected_tab(2)

        assert file_config.get_sample_id_column() == (0, 'I.D.'), f"Sample ID column was not correct {file_config.get_sample_id_column()}"

    def test_csv_get_comment_id_column(self):
        # Provided a CSV file we should beable to detect the sample ID column
        file_name = 'oxygen.csv'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config.get_comment_column() == (14, 'Comments'), f"Comment column was not correct {file_config.get_comment_column()}"

    def test_dat_get_comment_column(self):
        # Provided a DAT file we should beable to detect the sample ID column
        file_name = 'oxygen.dat'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))

        assert file_config.get_comment_column() == (13, 'Comments'), f"Comment column was not correct {file_config.get_comment_column()}"

    def test_xls_get_comment_column(self):
        # Provided a XLS file we should beable to detect the sample ID column
        file_name = 'oxygen.xlsx'
        file = Path(self.sample_data_path, file_name)

        file_config = None
        with open(file, 'br') as f:
            file_config = FileConfig(file_name, BytesIO(f.read()))
            file_config.set_selected_tab(1)

        assert file_config.get_comment_column() == (15, 'Comments'), f"Comment column was not correct {file_config.get_comment_column()}"

