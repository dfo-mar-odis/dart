from http.client import responses

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column, Div
from crispy_forms.utils import render_crispy_form
from django.db import transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path, reverse_lazy

from django import forms
from django.utils.translation import gettext as _

import settingsdb
from settingsdb.models import SampleFileConfig, SampleFileConfigColumns
from bio_tables.models import BCDataType
from config.utils import load_svg
from core.parsers.samples.samplefile_config import FileConfig
from core.forms import AlertSoup


class ExistingConfigForm(forms.Form):

    existing_config = forms.ChoiceField(choices=[(-1, '--------')], required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        existing_config_attrs = {
            'hx-post': reverse_lazy('core:from_sample_type_update_existing_config'),
            'hx-trigger': 'change',
            'hx-target': '#div_id_existing_config',
            'hx-swap': 'outerHTML'
        }

        init_attrs = {}
        if self.initial:
            init_attrs = {
                'hx-post': reverse_lazy('core:form_sample_type_get_headers', args=(self.initial['existing_config'],)),
                'hx-trigger': 'load',
                'hx-target': '#div_id_config_details',
            }

        config_choices = [(c.pk, f"{c.name} - {c.description if c.description else 'No Description'}") for c in SampleFileConfig.objects.all()]
        self.fields['existing_config'].choices += config_choices

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Div(
                Div(
                    Row(
                        Column(
                            Field('existing_config', **existing_config_attrs, css_class='form-select form-select-sm'),
                        )
                    ),
                    css_class='card-body', css_id='div_id_existing_config_content'
                ),
                css_class='card', **init_attrs, css_id='div_id_existing_config'
            )
        )

class FileConfigSaveForm(forms.Form):
    config_name = forms.CharField(required=True)
    config_description = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        attrs = {
            'hx-post': reverse_lazy('core:form_sample_type_validate_save_config'),
            'hx-target': "#div_id_save_config_card",
            'hx-indicator': "#div_id_indicator_sample_config",
            'hx-swap': 'outerHTML'
        }
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
                    css_class='card-body', css_id='div_id_save_config_content'
                ),
                css_class='card mt-2', css_id='div_id_save_config_card'
            )
        )

class FileValueForm(forms.Form):

    name_column = forms.CharField(required=False, label=_("Alias"), help_text=_('Data table display name. If blank, uses datatype method as a display name'))
    value_column = forms.ChoiceField(label=_("Value Column"), choices=[(-1, '--------')])
    detection_limit_column = forms.ChoiceField(label=_("Detection Limit"), choices=[(-1, '--------')])
    quality_control_column = forms.ChoiceField(label=_("Quality Control"), choices=[(-1, '--------')])

    datatype_id = forms.IntegerField(required=False)
    datatype_text_filter = forms.CharField(required=False)
    datatype = forms.ChoiceField(choices=[(-1, '--------')], required=False)

    def clean_value_column(self):
        value_column = self.cleaned_data['value_column']

        if value_column == '-1':
            raise forms.ValidationError(_('At least one column must be selected to be added to the configuration'))
        return value_column

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
        self.fields['detection_limit_column'].choices = [(-1, '--------')] + column_names
        self.fields['quality_control_column'].choices = [(-1, '--------')] + column_names

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
            'hx-post': reverse_lazy('core:form_sample_type_validate_value_form'),
            'hx-target': "#div_id_sample_value_form_content",
            'hx-swap': "outerHTML"
        }

        icon = load_svg("plus-square")
        add_button = StrictButton(icon, **attrs, css_class='btn btn-primary btn-sm')

        form_attrs = {
            'hx-post': reverse_lazy('core:form_sample_type_get_value_form'),
            'hx-trigger': 'clear_value_form from:body',
            'hx-indicator': "#div_id_indicator_sample_config"
        }

        datatype_filter_row = self.get_datatype_filter_row()

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Div(
                Div(
                    Row(
                        Column(Field('name_column', css_class='form-control form-control-sm')),
                    ),
                    Row(
                        Column(Field('value_column', css_class='form-select form-select-sm')),
                        Column(Field('detection_limit_column', css_class='form-select form-select-sm')),
                        Column(Field('quality_control_column', css_class='form-select form-select-sm')),
                    ),
                    datatype_filter_row,
                    Row(
                        Column(add_button),
                    ),
                    css_class='card-body',
                ),
                css_class='card mt-2', css_id="div_id_sample_value_form_content", **form_attrs
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

    def __init__(self, file_config: FileConfig = None, *args, **kwargs):

        initial = kwargs.pop('initial', {})
        self.file_config = file_config
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
            Div(
                Div(
                    tab_header_row,
                    Row(
                        Column(Field('sample_column', css_class='form-select form-select-sm', **update_value_trigger_attrs)),
                        Column(Field('comment_column', css_class='form-select form-select-sm', **update_value_trigger_attrs)),
                    ),
                    css_class='card-body',
                ),
                css_class='card mt-2'
            )
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


def get_file_config(request, **kwargs):
    # only one file can be uploaded here at a time.
    file = request.FILES.get('sample_file', None)
    soup = BeautifulSoup('<div id="div_id_sample_config_form_content"></div>', 'html.parser')
    if not file:
        # if there's no file we'll clear the session cache so cached headers
        # don't interfere with other files loaded later
        if 'sample_file' in request.session:
            del request.session['sample_file']
        if 'sample_file_column_names' in request.session:
            del request.session['sample_file_column_names']
    else:
        existing_config = None
        if 'config_id' in kwargs:
            existing_config = SampleFileConfig.objects.get(pk=kwargs['config_id'])

        form_content = soup.find('div')

        existing_config_form = ExistingConfigForm(initial={
            'existing_config': existing_config.pk}) if existing_config else ExistingConfigForm()
        existing_config_html = render_crispy_form(existing_config_form)
        existing_config_soup = BeautifulSoup(existing_config_html, 'html.parser')
        form_content.append(existing_config_soup)

        form_content.append(content_div := soup.new_tag('div', id='div_id_config_details'))

        file_config = initialize_file_config(request)
        if existing_config:
            file_config.set_selected_tab(existing_config.tab)
            file_config.set_header_line_number(existing_config.header_line)
            file_config.set_sample_id_column_by_name(existing_config.sample_id_column_name)
            file_config.set_comment_column_by_name(existing_config.comment_column_name)

        if existing_config:
            save_form_init = {
                'config_name': existing_config.name,
                'config_description': existing_config.description
            }
            save_form = FileConfigSaveForm(initial=save_form_init)
        else:
            save_form = FileConfigSaveForm()

        save_form_html = render_crispy_form(save_form)
        save_form_soup = BeautifulSoup(save_form_html, 'html.parser')
        content_div.append(save_form_soup)

        form = FileConfigForm(file_config)
        html = render_crispy_form(form)
        content_div.append(BeautifulSoup(html, 'html.parser'))

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
            content_div.append(value_form_soup)

            config_row_context = {}
            if existing_config:
                config_rows = []
                col_names_upper = [c[1].upper() for c in column_names]
                for row in existing_config.config_columns.all():
                    value_col = column_names[col_names_upper.index(row.value_column_name)]
                    dl_col = None
                    if row.detection_limit_column_name:
                        dl_col = column_names[col_names_upper.index(row.detection_limit_column_name)]

                    qc_col = None
                    if row.quality_control_column_name:
                        qc_col = column_names[col_names_upper.index(row.quality_control_column_name)]

                    datatype = None
                    if row.datatype_id:
                        datatype = BCDataType.objects.get(pk=row.datatype_id)

                    config_row = {
                        'value_id': value_col[0],
                        'dl_id': dl_col[0] if dl_col else None,
                        'qc_id': qc_col[0] if qc_col else None,
                        'value_column': value_col[1],
                        'dl_column': dl_col[1] if dl_col else None,
                        'qc_column': qc_col[1] if qc_col else None,
                        'name_column': row.column_alias if row.column_alias else None,
                        'datatype': datatype.pk if datatype else "",
                        'datatype_method': datatype.method if datatype else "",
                        'datatype_description': datatype.description if datatype else "",
                    }
                    config_rows.append(config_row)
                config_row_context['configs'] = config_rows
                config_table_html = render_to_string('core/partials/table_samplefile_config.html', context=config_row_context, request=request)
            else:
                config_table_html = render_to_string('core/partials/table_samplefile_config.html', request=request)
            config_table_soup = BeautifulSoup(config_table_html, 'html.parser')
            content_div.append(config_table_soup)

        if existing_config:
            return HttpResponse(content_div)

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
        initial['detection_limit_column'] = request.POST.get(f"{prefix}_dl_column", None)
        initial['quality_control_column'] = request.POST.get(f"{prefix}_qc_column", None)
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
        dl_column_id = int(request.POST.get('detection_limit_column', -1))
        qc_column_id = int(request.POST.get('quality_control_column', -1))

        columns = get_file_columns(request)
        value_column_name = columns[value_column_id]
        dl_column_name = columns[dl_column_id]
        qc_column_name = columns[qc_column_id]

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
                'dl_id': dl_column_id,
                'qc_id': qc_column_id,
                'value_column': value_column_name[1],
                'dl_column': dl_column_name[1],
                'qc_column': qc_column_name[1],
                'name_column': name_column,
                'datatype': datatype_id if datatype_id != -1 else "",
                'datatype_method': datatype.method if datatype else "",
                'datatype_description': datatype.description if datatype else "",
            }]
        }
        html = render_to_string('core/partials/table_samplefile_config.html', context=context, request=request)
        return BeautifulSoup(html, 'html.parser')

    return None


def validate_config(request):

    file = request.FILES.get('sample_file', None)
    if not file:
        soup = AlertSoup('validate_config_form')
        soup.set_status('danger').add_message(_("No file was selected."))
        return HttpResponse(soup)

    column_names = get_file_columns(request)
    form = FileValueForm(column_names, data=request.POST)
    if form.is_valid():
        crispy_html = render_crispy_form(form)
        soup = BeautifulSoup(crispy_html, 'html.parser')
        form_div = soup.find(id="div_id_sample_value_form_content").find('div')
        form_div.attrs['hx-trigger'] = "load"

        form_div.attrs['hx-post'] = reverse_lazy("core:form_sample_type_update_to_config")
        if request.POST.get(f'config_{form.data['value_column']}', -1) == -1:
            form_div.attrs['hx-swap'] = "beforeend"
            form_div.attrs['hx-post'] = reverse_lazy("core:form_sample_type_add_to_config")

        form_div.attrs['hx-target'] = "#table_id_column_configuration_table tbody"
        form_div.attrs['hx-indicator'] = "#div_id_indicator_sample_config"
        response = HttpResponse(soup)
        # response['HX-Trigger'] = f'clear_value_form'
        return response

    return HttpResponse(render_crispy_form(form))

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


def create_sample_config_columns(request, sample_config) -> None:
    column_names = get_file_columns(request)

    configs = request.POST.getlist('configs', [])
    for config in configs:
        prefix = f"config_{config}"
        value_col_id = request.POST.get(f'{prefix}', -1)
        dl_col_id = request.POST.get(f'{prefix}_dl_column', None)
        qc_col_id = request.POST.get(f'{prefix}_qc_column', None)
        alias_col = request.POST.get(f'{prefix}_name_column', None)
        datatype_col = request.POST.get(f'{prefix}_datatype', None)

        value_col = column_names[int(value_col_id)]
        config_attrs = {
            'file_config_id': sample_config.pk,
            'value_column_name': value_col[1]
        }

        if alias_col:
            config_attrs['column_alias'] = alias_col

        if datatype_col:
            config_attrs['datatype_id'] = datatype_col

        if dl_col_id:
            dl_col = column_names[int(dl_col_id)]
            config_attrs['detection_limit_column_name'] = dl_col[1]

        if qc_col_id:
            qc_col = column_names[int(qc_col_id)]
            config_attrs['quality_control_column_name'] = qc_col[1]

        if sample_config.config_columns.filter(value_column_name__iexact=value_col[1]).exists():
            SampleFileConfigColumns.objects.update(**config_attrs)
        else:
            SampleFileConfigColumns.objects.create(**config_attrs)


def validate_save_config(request):
    file = request.FILES.get('sample_file', None)

    save_form = FileConfigSaveForm(data=request.POST)
    alert_soup = None
    if not file:
        crispy_html = render_crispy_form(save_form)
        soup = BeautifulSoup(crispy_html, 'html.parser')

        alert_soup = AlertSoup('validate_config_form')
        alert_soup.set_status('danger').add_message(_("No file was selected."))
        soup.find(id='div_id_save_config_content').insert(0, alert_soup)

        return HttpResponse(soup)

    if save_form.is_valid():
        # Validate the config name is unique and isn't already in settingsdb.models.SampleFileConfig
        # Validate file type (required), header line (required), sample ID column (required), comment column (optional)
        column_names = get_file_columns(request)

        sample_id_col = int(request.POST.get('sample_column', -1))
        comment_col = int(request.POST.get('comment_column', -1))
        file_type = request.POST.get('file_type', '')

        sample_column = column_names[sample_id_col]
        comment_column = column_names[comment_col]
        attrs = {
            'name': save_form.cleaned_data['config_name'],
            'description': save_form.cleaned_data['config_description'],
            'file_type': file_type,
            'tab': int(request.POST.get('file_tab', -1)),
            'header_line': int(request.POST.get('header_line_number', -1)),
            'sample_id_column_name': sample_column[1],
            'comment_column_name': comment_column[1]
        }
        try:
            if SampleFileConfig.objects.filter(name__iexact=attrs['name']).exists():
                with transaction.atomic():
                    config = SampleFileConfig.objects.update(**attrs)
                    create_sample_config_columns(request, config)
            else:
                with transaction.atomic():
                    config = SampleFileConfig.objects.create(**attrs)
                    create_sample_config_columns(request, config)

        except Exception as ex:
            alert_soup = AlertSoup('validate_config_form')
            alert_soup.set_status('danger').add_message(str(ex))

    crispy_html = render_crispy_form(save_form)
    if alert_soup:
        soup = BeautifulSoup(crispy_html, 'html.parser')
        soup.find(id='div_id_save_config_content').insert(0, alert_soup)
        return HttpResponse(soup)

    return HttpResponse(crispy_html)


def update_existing_config(request):
    existing = request.POST.get('existing_config', None)
    if existing:
        existing_form = ExistingConfigForm(initial={'existing_config': int(existing)})
    else:
        existing_form = ExistingConfigForm()

    crispy_html = render_crispy_form(existing_form)
    soup = BeautifulSoup(crispy_html, 'html.parser')
    return HttpResponse(soup)

url_patterns = [
    path('sample_config/header/', get_file_config, name='form_sample_type_get_headers'),
    path('sample_config/header/<int:config_id>/', get_file_config, name='form_sample_type_get_headers'),

    path('sample_config/value/', update_value_form, name='form_sample_type_get_value_form'),
    path('sample_config/value/<int:column_id>/', update_value_form, name='form_sample_type_get_value_form'),

    path('sample_config/config/validate/', validate_config, name='form_sample_type_validate_value_form'),
    path('sample_config/config/add/', add_to_config, name='form_sample_type_add_to_config'),
    path('sample_config/config/update/', update_to_config, name='form_sample_type_update_to_config'),
    path('sample_config/config/remove/<int:column_id>/', remove_from_config, name='form_sample_type_remove_from_config'),

    path('sample_config/existing/config/update/', update_existing_config, name='from_sample_type_update_existing_config'),

    path('sample_config/config/save/validate/', validate_save_config, name='form_sample_type_validate_save_config'),

    path('sample_config/datatype/update/', update_to_datatype_description_field, name='form_sample_type_get_datatype_method'),

]
