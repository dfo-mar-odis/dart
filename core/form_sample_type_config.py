from io import BytesIO

import openpyxl
from bs4 import BeautifulSoup
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field
from crispy_forms.utils import render_crispy_form
from django.http import HttpResponse
from django.urls import path

from django import forms


class FileConfig:
    file_type: str
    tab: int = -1
    tab_names: list = None
    header_line_number: int = 0

    def get_file_type(self):
        return self.file_type

    def get_xls_tab_names(self) -> list:

        if self.tab_names:
            return self.tab_names

        try:
            workbook = openpyxl.load_workbook(BytesIO(self.content), read_only=True)
            self.tab_names = workbook.sheetnames
            return self.tab_names
        except Exception as e:
            raise ValueError(f"Error reading XLS file: {e}")


    def __init__(self, filename, content: BytesIO):
        self.filename = filename
        self.content = content.read()

        # Determine file type based on the file extension
        extension = filename.split('.')[-1].lower()
        if extension == 'csv':
            self.file_type = 'CSV'
        elif extension in ['xls', 'xlsx']:
            self.file_type = 'XLS'
        elif extension == 'dat':
            self.file_type = 'DAT'
        else:
            raise TypeError(f'Unsupported file type: {extension}')



class FileConfigForm(forms.Form):

    file_tab = forms.ChoiceField(choices=[])
    header_line_number = forms.IntegerField()

    def __init__(self, file_config: FileConfig, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Field('header_line_number', css_class='form-control')
        )

        if file_config.file_type == 'XLS':
            tab_names = file_config.get_xls_tab_names()
            self.fields['file_tab'].choices = [(i, name) for i, name in enumerate(tab_names)]

            self.helper.layout.fields.insert(0, Field('file_tab', css_class='form-control'))

def get_file_headers(request):

    # only one file can be uploaded here at a time.
    file = request.FILES.get('sample_file', None)
    soup = BeautifulSoup('<div id="div_id_sample_config_form_content"></div>', 'html.parser')
    if file:
        file_config = FileConfig(file.name, file)
        form = FileConfigForm(file_config)
        form_content = soup.find('div')

        html = render_crispy_form(form)
        form_content.append(BeautifulSoup(html, 'html.parser'))

    return HttpResponse(soup)


url_patterns = [
    path('sample_config/header/', get_file_headers, name='form_sample_type_get_headers')
]