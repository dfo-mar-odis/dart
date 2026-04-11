from http.client import responses

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column, Div
from crispy_forms.utils import render_crispy_form
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path, reverse_lazy

from django import forms
from django.utils.translation import gettext_lazy as _

from bio_tables.models import BCDataType
from config.utils import load_svg
from core.parsers.samples.samplefile_config import FileConfig


class FileConfigSaveForm(forms.Form):
    config_name = forms.CharField(required=True)
    config_description = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        attrs = {}
        icon = load_svg("check-square")
        save_button = StrictButton(icon, **attrs, css_class='btn btn-primary btn-sm')

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Div(
                    Row(
                        Column(Field('config_name', css_class='form-control form-control-sm'), css_class='col-2'),
                        Column(Field('config_description', css_class='form-control form-control-sm'), css_class='col'),
                    ),
                    Row(
                        Column(save_button)
                    ),
                    css_class='card-body'
                ),
                css_class='card mt-2'
            )
        )

class FileValueForm(forms.Form):

    value_column = forms.ChoiceField(choices=[(-1, '--------')])
    name_column = forms.CharField(required=False, help_text=_('Data table display name. If blank, uses datatype method as a display name'))

    datatype_id = forms.IntegerField(required=False)
    datatype_text_filter = forms.CharField(required=False)
    datatype = forms.ChoiceField(choices=[(-1, '--------')], required=False)

    def get_datatype_filter_row(self) -> Div:

        datatype_id_attrs = {
            'hx-post': reverse_lazy('core:form_sample_type_get_datatype_method'),
            'hx-target': "#id_datatype",
            'hx-trigger': "keyup changed delay:1000ms"
        }

        row = Div(
            Row(
                Column(Field('datatype_id', css_class='form-control form-control-sm', **datatype_id_attrs), css_class='col-2'),
                Column(Field('datatype_text_filter', css_class='form-control form-control-sm', **datatype_id_attrs), css_class='col'),
            ),
            Row(
                Column(Field('datatype', css_class='form-select form-select-sm')),
            )
        )

        return row

    def __init__(self, column_names: list[tuple[int, str]], datatype_text_filter: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['value_column'].choices = [(-1, '--------')] + column_names

        datatypes = BCDataType.objects.all()
        if datatype_text_filter:
            tokens = datatype_text_filter.strip().split(' ')
            for token in tokens:
                datatypes = datatypes.filter(description__icontains=token)
            datatype_choices = [(datatype.pk, f'{datatype.pk}: {datatype.method} - {datatype.description}') for datatype
                                in datatypes]
        else:
            datatype_choices = [(-1, '--------')] + [(datatype.pk, f'{datatype.pk}: {datatype.method} - {datatype.description}') for datatype in datatypes]

        self.fields['datatype'].choices = datatype_choices

        attrs = {
            'title': _("Add to configuration"),
            'hx-post': reverse_lazy('core:form_sample_type_add_to_config'),
            'hx-target': f"#table_id_column_configuration_table tbody",
            'hx-swap': "beforeend"
        }

        icon = load_svg("plus-square")
        add_button = StrictButton(icon, **attrs, css_class='btn btn-primary btn-sm')

        form_attrs = {
            'hx-post': reverse_lazy('core:form_sample_type_get_value_form'),
            'hx-trigger': 'clear_value_form from:body'
        }

        datatype_filter_row = self.get_datatype_filter_row()

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Div(
                Div(
                    Row(
                        Column(Field('value_column', css_class='form-select form-select-sm')),
                        Column(Field('name_column', css_class='form-control form-control-sm')),
                    ),
                    datatype_filter_row,
                    Row(
                        Column(add_button),
                    ),
                    css_class='card-body',
                ),
                css_class='card', css_id="div_id_sample_value_form_content", **form_attrs
            )
        )

class FileConfigForm(forms.Form):

    column_names: list[tuple[int, str]] = None

    file_config: FileConfig = None
    file_tab = forms.ChoiceField(choices=[])
    header_line_number = forms.IntegerField()

    sample_column = forms.ChoiceField(choices=[(-1, '--------')])
    comment_column = forms.ChoiceField(choices=[(-1, '--------')], required=False)

    def get_file_tab_column(self):
        file_tab_column = None
        if self.file_config.file_type == 'XLS':
            tab_names = self.file_config.get_tab_names()
            self.fields['file_tab'].choices = [(i, name) for i, name in enumerate(tab_names)]

            tab_attrs = {
                'hx-post': reverse_lazy('core:form_sample_type_get_headers'),
                'hx-target': '#div_id_sample_config_form_content',
                'hx-trigger': 'change',
                'hx-indicator': "#div_id_indicator_sample_config"
            }
            file_tab_column = Column(Field('file_tab', css_class='form-select form-select-sm', **tab_attrs))

        return file_tab_column

    def __init__(self, file_config: FileConfig, *args, **kwargs):
        self.file_config = file_config

        initial = kwargs.pop('initial', {})
        if 'header_line_number' not in initial:
            initial['header_line_number'] = file_config.get_header_line_number()

        if 'file_tab' not in initial:
            initial['file_tab'] = file_config.selected_tab

        if default_sample_column := file_config.get_sample_id_column():
            if 'sample_column' not in initial:
                initial['sample_column'] = default_sample_column[0]

        if default_comment_column := file_config.get_comment_column():
            if 'comment_column' not in initial:
                initial['comment_column'] = default_comment_column[0]

        super().__init__(*args, **kwargs, initial=initial)

        self.column_names = [(col_index, col_name) for col_index, col_name in enumerate(file_config.get_column_names())]
        self.fields['sample_column'].choices = [(-1, '--------')] + self.column_names
        self.fields['comment_column'].choices = [(-1, '--------')] + self.column_names

        update_value_trigger_attrs = {
            'hx-post': reverse_lazy('core:form_sample_type_get_value_form'),
            'hx-target': '#div_id_sample_value_form_content',
            'hx-trigger': 'change',
            'hx-indicator': "#div_id_indicator_sample_config"
        }
        ##################### Table Layout #####################
        tab_header_row = Row(
            Column(Field('header_line_number', css_class='form-control form-control-sm'))
        )

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            tab_header_row,
            Row(
                Column(Field('sample_column', css_class='form-select form-select-sm', **update_value_trigger_attrs)),
                Column(Field('comment_column', css_class='form-select form-select-sm', **update_value_trigger_attrs)),
            ),
        )

        if file_tab_column := self.get_file_tab_column():
            tab_header_row.fields.insert(0, file_tab_column)


def initialize_file_config(request) -> FileConfig:
    file = request.FILES.get('sample_file', None)

    initial = {}
    if header_line_number := request.POST.get('header_line_number', -1):
        initial['header_line_number'] = int(header_line_number)

    if file_tab := request.POST.get('file_tab', -1):
        initial['file_tab'] = int(file_tab)

    file_config = FileConfig(file.name, file, tab=initial['file_tab'])
    file_config.set_header_line_number(initial['header_line_number'])

    if request.session.get('sample_file', None) != file.name:
        request.session['sample_file'] = file.name

        if 'sample_file_column_names' in request.session:
            del request.session['sample_file_column_names']

        request.session['sample_file_column_names'] = [(idx, col) for idx, col in
                                                       enumerate(file_config.get_column_names())]

    return file_config


def get_file_columns(request):
    if 'sample_file_column_names' not in request.session:
        initialize_file_config(request)

    columns = request.session.get('sample_file_column_names', []).copy()

    return columns


def get_file_config(request):
    # only one file can be uploaded here at a time.
    file = request.FILES.get('sample_file', None)
    soup = BeautifulSoup('<div id="div_id_sample_config_form_content"></div>', 'html.parser')
    if not file:
        if 'sample_file' in request.session:
            del request.session['sample_file']
        if 'sample_file_column_names' in request.session:
            del request.session['sample_file_column_names']
    else:
        form_content = soup.find('div')
        file_config = initialize_file_config(request)
        form = FileConfigForm(file_config)
        html = render_crispy_form(form)

        form_content.append(BeautifulSoup(html, 'html.parser'))

        if file_config.get_header_line_number() is not None:
            exclude: list[int] = []
            if sid_col := file_config.get_sample_id_column():
                exclude.append(sid_col[0])
            if cid_col := file_config.get_comment_column():
                exclude.append(cid_col[0])

            column_names = request.session.get('sample_file_column_names', []).copy()
            exclude.sort(reverse=True)
            for exclude in exclude:
                column_names.pop(exclude)

            value_form = FileValueForm(column_names)
            value_form_html = render_crispy_form(value_form)
            value_form_soup = BeautifulSoup(value_form_html, 'html.parser')
            form_content.append(value_form_soup)

            config_table_html = render_to_string('core/partials/table_samplefile_config.html', request=request)
            config_table_soup = BeautifulSoup(config_table_html, 'html.parser')
            form_content.append(config_table_soup)

            save_form = FileConfigSaveForm()
            save_form_html = render_crispy_form(save_form)
            save_form_soup = BeautifulSoup(save_form_html, 'html.parser')
            form_content.append(save_form_soup)

    return HttpResponse(soup)


def update_value_form(request, **kwargs):

    # This is called when the user changes the file tab or header line number. It will return an updated value form with the new column names.
    exclude = []
    if (sample_id_index := int(request.POST.get('sample_column', -1))) != -1:
        exclude.append(sample_id_index)

    if (comment_index := int(request.POST.get('comment_column', -1))) != -1:
        exclude.append(comment_index)

    column_names = get_file_columns(request)
    exclude.sort(reverse=True)
    for exclude in exclude:
        column_names.pop(exclude)

    initial = {}
    if 'column_id' in kwargs:
        prefix = f'config_{kwargs["column_id"]}'
        initial['value_column'] = request.POST.get(prefix, None)
        initial['name_column'] = request.POST.get(f'{prefix}_name_column', None)
        initial['datatype'] = request.POST.get(f'{prefix}_datatype', None)

    value_form = FileValueForm(column_names, initial=initial)

    value_form_html = render_crispy_form(value_form)
    soup = BeautifulSoup(value_form_html, 'html.parser')

    return HttpResponse(soup.find('div'))


def get_config_soup(request) -> BeautifulSoup | None:
    file = request.FILES.get('sample_file', None)
    if file:
        value_column_id = int(request.POST.get('value_column', -1))

        columns = get_file_columns(request)
        value_column_name = columns.pop(value_column_id)

        name_column = request.POST.get('name_column', None)
        datatype_id = int(request.POST.get('datatype', -1))
        try:
            datatype = None
            if datatype_id != -1:
                datatype = BCDataType.objects.get(pk=datatype_id)
        except BCDataType.DoesNotExist:
            datatype = BCDataType(method="N/A",
                                  description="Could not find datatype. You're datatype definitions may need to be updated")

        context = {
            'configs': [{
                'value_id': value_column_id,
                'value_column': value_column_name[1],
                'name_column': name_column,
                'datatype': datatype_id,
                'datatype_method': datatype.method if datatype else None,
                'datatype_description': datatype.description if datatype else None,
            }]
        }
        html = render_to_string('core/partials/table_samplefile_config.html', context=context, request=request)
        return BeautifulSoup(html, 'html.parser')

    return None


def add_to_config(request):
    file = request.FILES.get('sample_file', None)
    if file:
        value_column_id = int(request.POST.get('value_column', -1))
        if f'config_{value_column_id}' in request.POST:
            response = HttpResponse()
            response['HX-Trigger-After-Settle'] = f'update_config_{value_column_id}'
            return response

        soup = get_config_soup(request)

        row = soup.find('tr', id=f'config_{value_column_id}')
        response = HttpResponse(row.find_parent())
        response['HX-Trigger'] = f'clear_value_form'
        return response

    return HttpResponse()

def update_to_config(request):
    file = request.FILES.get('sample_file', None)
    if file:
        value_column_id = int(request.POST.get('value_column', -1))

        soup = get_config_soup(request)

        row = soup.find('tr', id=f'config_{value_column_id}')
        response = HttpResponse(row.find_parent())
        response['HX-Trigger'] = f'clear_value_form'
        return response

    return HttpResponse()


def remove_from_config(request, column_id):
    return HttpResponse()


def update_to_datatype_description_field(request):
    file = request.FILES.get('sample_file', None)
    if file:
        initial = {}
        column_names = get_file_columns(request)
        datatype_id = request.POST.get('datatype_id', '')
        if datatype_id != '':
            initial['datatype'] = int(datatype_id)

        datatype_text_filter = request.POST.get('datatype_text_filter', None)

        value_form = FileValueForm(column_names, datatype_text_filter=datatype_text_filter, initial=initial)
        html = render_crispy_form(value_form)
        soup = BeautifulSoup(html, 'html.parser')

        return HttpResponse(soup.find(id="id_datatype"))

    return HttpResponse()

url_patterns = [
    path('sample_config/header/', get_file_config, name='form_sample_type_get_headers'),
    path('sample_config/value/', update_value_form, name='form_sample_type_get_value_form'),
    path('sample_config/value/<int:column_id>/', update_value_form, name='form_sample_type_get_value_form'),
    path('sample_config/config/add/', add_to_config, name='form_sample_type_add_to_config'),
    path('sample_config/config/update/', update_to_config, name='form_sample_type_update_to_config'),
    path('sample_config/config/remove/<int:column_id>/', remove_from_config, name='form_sample_type_remove_from_config'),

    path('sample_config/datatype/update/', update_to_datatype_description_field, name='form_sample_type_get_datatype_method'),

]
