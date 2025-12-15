# See "docs/form_sample_type_configflowchart.mmd"
import time

import django.utils.datastructures
from bs4 import BeautifulSoup

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Column, Row, Div
from crispy_forms.utils import render_crispy_form

from django import forms
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

import logging

from config.utils import load_svg
from core import models
from core.consumer import LoggerConsumer
from core.parsers.samples.sample_parser import logger as sampler_logger, SampleParser
from settingsdb.models import SampleFileType, SampleTypeVariable

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')

div_id_file_header_row = "div_id_file_header_row"
table_column_header_id = "tabel_id_sample_file_header"
div_id_data_value_row_form = "div_id_data_value_row_form"
div_id_file_config_section = "div_id_file_config_section"
indicator_id = "div_id_file_config_spinner"
div_id_button_action_row = "div_id_button_action_row"
div_id_sample_load_message = "div_id_sample_load_message"
div_id_sample_type_variable = "div_id_sample_type_variable"
div_id_config_row = "div_id_config_row"
div_id_parser_button_col = "div_id_parser_button_row"


class SampleFileTypeForm(forms.ModelForm):
    class Meta:
        model = SampleFileType
        fields = '__all__'

    def get_tab_entry(self):
        attrs = {
            "hx-post": reverse_lazy("core:form_sample_config_load"),
            "hx-target": "#" + div_id_file_config_section,
            "hx-indicator": "#" + indicator_id,
            "onchange": "document.getElementById('id_skip').value = -1;",
        }
        return Field('tab', **attrs, css_class="form-select-sm")

    def get_skip_entry(self):
        attrs = {
            "hx-post": reverse_lazy("core:form_sample_config_load"),
            "hx-target": "#" + div_id_file_config_section,
            "hx-indicator": "#" + indicator_id,
        }
        return Field('skip', **attrs, css_class="form-control-sm")

    def get_sample_field_entry(self):
        attrs = {
            "hx-post": reverse_lazy("core:form_sample_config_reload_header"),
            "hx-target": "#" + div_id_file_header_row,
            "hx-indicator": "#" + indicator_id,
        }
        return Field('sample_field', css_class="form-select-sm", **attrs)

    def get_comment_field_entry(self):
        attrs = {
            "hx-post": reverse_lazy("core:form_sample_config_reload_header"),
            "hx-target": "#" + div_id_file_header_row,
            "hx-indicator": "#" + indicator_id,
        }
        return Field('comment_field', css_class="form-select-sm", **attrs)

    def get_allowed_blanks(self):
        return Field('are_blank_sample_ids_replicates', css_class="form-control-sm")

    def get_allowed_replicates(self):
        return Field('allowed_replicates', css_class="form-control-sm")

    def __init__(self, tab_names=None, headers=None, *args, **kwargs):
        super(SampleFileTypeForm, self).__init__(*args, **kwargs)

        self.fields['skip'].help_text = _(
            "Number of rows to skip to find the header. If -1 Dart will try to find it automatically.")

        hidden_row = Row(Field('file_type', type='hidden'))
        config_row = Row(Column(self.get_skip_entry()))

        data_value_row = Row(css_id=div_id_data_value_row_form, css_class="vertical-scrollbar-sm")

        button_row_attrs = {
            "hx-trigger": "reload_buttons from:body",
            "hx-post": reverse_lazy("core:form_sample_config_reload_buttons"),
            "hx-indicator": "#" + indicator_id,
        }
        button_row = Row(css_id=div_id_button_action_row, **button_row_attrs)

        file_header_row_attrs = {
            "hx-trigger": "reload_headers from:body",
            "hx-post": reverse_lazy("core:form_sample_config_reload_header"),
            "hx-indicator": "#" + indicator_id,
            'class': "overflow-x-scroll",
        }
        file_header_row = Row(css_id=div_id_file_header_row, **file_header_row_attrs)

        config_row_attrs = {
            "hx-trigger": "reload_configs from:body",
            "hx-post": reverse_lazy("core:form_sample_config_reload_configs"),
            "hx-indicator": "#" + indicator_id,
        }
        existing_configs_row = Div(css_id=div_id_config_row, **config_row_attrs)

        # if there are tabs, we're dealing with an excel file and the user might
        # have to choose which worksheet to use.
        if tab_names:
            self.fields['tab'] = forms.ChoiceField(
                choices=[(item, name) for item, name in enumerate(tab_names)],
            )
            config_row.insert(0, Column(self.get_tab_entry()))
        else:
            hidden_row.append(Field('tab', type='hidden'))

        # If column names are provided the sample and comment fields should be picklist,
        # otherwise the user will have to manually enter the values.
        if headers:
            field_choices = [(name.upper(), name) for item, name in enumerate(headers)]
            self.fields['sample_field'] = forms.ChoiceField(
                label=_("Sample ID Column"),
                choices=field_choices
            )

            self.fields['comment_field'] = forms.ChoiceField(
                required=False,
                choices=[(None, '------')] + field_choices
            )

        config_row.append(Column(self.get_sample_field_entry()))
        config_row.append(Column(self.get_comment_field_entry()))
        config_row.append(Column(self.get_allowed_replicates()))
        config_row.append(Column(self.get_allowed_blanks()))

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            hidden_row,  # storage of hidden variables
            config_row,  # storage of available header information if found
            file_header_row,  # A place to put the file headers with buttons for selecting a column to load
            data_value_row,  # A Place for SampleVariables to be configured
            button_row,  # A button row for saving the configuration
            existing_configs_row  # A place to put configs we were able to detected for the user to select from.
        )


class SampleVariableForm(forms.ModelForm):
    class Meta:
        model = SampleTypeVariable
        fields = "__all__"

    def __init__(self, column_id=0, headers=None, *args, **kwargs):
        super(SampleVariableForm, self).__init__(*args, **kwargs)

        hidden_row = Row(Field('sample_type', type='hidden'), Field('value_field', type='hidden'))

        if headers:
            field_choices = [(name.upper(), name) for item, name in enumerate(headers)]

            self.fields['flag_field'] = forms.ChoiceField(choices=[(None, '------')] + field_choices, required=False)
            self.fields['limit_field'] = forms.ChoiceField(choices=[(None, '------')] + field_choices, required=False)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                hidden_row,
                Row(
                    Column(Field('name', css_class="form-control-sm")),
                    Column(Field('flag_field', css_class="form-select-sm" if headers else "form-control-sm")),
                    Column(Field('limit_field', css_class="form-select-sm" if headers else "form-control-sm")),
                ),
                css_id=div_id_sample_type_variable + f"_{column_id}"
            )
        )


class StatusAlert(BeautifulSoup):
    component_id = None
    alert_container = None

    def set_type(self, alert_type):
        self.alert_container.attrs["class"] = f"alert alert-{alert_type}"

    def set_socket(self, socket_name):
        self.alert_container.attrs["hx-ext"] = "ws"
        self.alert_container.attrs["ws-connect"] = f'/ws/notifications/{socket_name}/{self.component_id}/'

    def get_message_container(self):
        return self.alert_message

    def set_message(self, message):
        self.alert_message.string = message

    def include_close_button(self):
        self.message_row.append(col:=self.new_tag("div", attrs={"class": "col-auto"}))
        col.append(remove_btn:=self.new_tag("button", attrs={"class": "btn btn-sm btn-secondary", "type": "button"}))
        remove_btn.attrs['onclick'] = f"document.getElementById(`{self.component_id}_container`).remove();"
        icon = BeautifulSoup(load_svg('x-square'), 'html.parser').svg
        remove_btn.append(icon)

    def include_progress_bar(self):
        # create a progress bar to give the user something to stare at while they wait.
        progress_bar = self.new_tag("div")
        progress_bar.attrs = {
            'class': "progress-bar progress-bar-striped progress-bar-animated",
            'role': "progressbar",
            'style': "width: 100%"
        }
        progress_bar_div = self.new_tag("div", attrs={'class': "progress", 'id': 'progress_bar'})
        progress_bar_div.append(progress_bar)

        self.alert_container.append(progress_bar_div)

    def is_socket_connected(self, socket_name):
        is_open = False
        for count in range(5):
            if is_open := LoggerConsumer.is_socket_open(socket_name, self.component_id):
                break
            time.sleep(0.5)

        return is_open

    def __init__(self, component_id, message="connecting...", alert_type="info"):
        super().__init__("", "html.parser")

        self.component_id = component_id

        self.alert_container = self.new_tag("div", attrs={"id": f"{component_id}_container"})
        self.message_row = self.new_tag("div", attrs={"class": "row"})

        self.alert_message = self.new_tag("div", attrs={"id": component_id})

        self.alert_container.append(self.message_row)
        self.message_row.append(col:=self.new_tag("div", attrs={"class": "col"}))
        col.append(self.alert_message)

        self.append(self.alert_container)
        self.set_message(message)
        self.set_type(alert_type)


class ParserButtonRow(BeautifulSoup):
    def __init__(self, *args, **kwargs):
        super().__init__("", "html.parser")

        self.append(row:=self.new_tag("div", attrs={"class": "row mb-2"}))
        row.append(col:=self.new_tag("div", attrs={"class": "col-auto"}))
        col.append(input_group:=self.new_tag("div", attrs={"class": "input-group"}))

        input_attrs = {
            "type": "text",
            "class": "form-control form-control-sm",
            "placeholder": "Enter a configuration name",
        }
        input_group.append(config_input := self.new_tag('input', attrs=input_attrs))

        save_button_attrs = {
            "type": "button",
            "class": "btn btn-sm btn-primary me-2",
            "hx-post": reverse_lazy("core:form_sample_config_save"),
            "hx-target": "#" + div_id_parser_button_col,
        }
        input_group.append(save_btn := self.new_tag('button', attrs=save_button_attrs))
        save_btn.attrs['name'] = 'save'
        save_btn.string = _("Save")

        config_input.attrs['name'] = 'config_name'

        # this is where we can place a "success" or a "This config name is already in use" message
        self.append(row:=self.new_tag("div", attrs={"class": "row mb-2"}))
        row.append(self.new_tag("div", attrs={"id": div_id_parser_button_col, "class": "col-auto"}))


class ConfigCard(BeautifulSoup):
    def __init__(self, config: SampleFileType, *args, **kwargs):
        context = {
            "post": reverse_lazy("core:form_sample_config_parse", args=[config.pk]),
            "target": "#" + div_id_sample_load_message,
            "trigger": f"click, start_parsing_{config.pk} from:body",
            "card_name": f"config_{config.pk}",
            "card_title": config.name,
            "config": config
        }
        super().__init__(render_to_string("core/partials/card_sample_file_config.html", context), "html.parser")


def add_header_table(request, soup: BeautifulSoup, sample_parser: SampleParser):
    try:
        headers = sample_parser.get_headers()
    except ValueError as ex:
        headers = ["Could not automatically find header line"]

    soup.append(div := soup.new_tag("div", attrs={"id": table_column_header_id }))
    div.append(table := soup.new_tag('table', attrs={'class': 'table table-sm table-bordered'}))
    table.append(tbody := soup.new_tag('tbody'))
    tbody.append(tr := soup.new_tag('tr'))

    used_columns = [column.upper() for column in request.POST.getlist("value_field")]
    for col_number, col in enumerate(headers):
        tr.append(td := soup.new_tag('td'))
        if col.upper() != sample_parser.get_sample_field() and col.upper() != sample_parser.get_comment_field():
            attrs = {
                "id": f"btn_id_sample_value_{col_number}",
                "type": "button",
                "hx-indicator": "#" + indicator_id,
            }
            if col.upper() in used_columns:
                attrs['title'] = _("remove from processing")
                attrs['class'] = "btn btn-sm btn-primary"
                attrs['hx-post'] = reverse_lazy("core:form_sample_config_add_value_column", args=[col_number]) + "?remove=true"
                attrs['hx-swap'] = "delete"
                attrs['hx-target'] = "#" + div_id_sample_type_variable + f"_{col_number}"
            else:
                attrs['title'] = _("Add to processing")
                attrs['class'] = "btn btn-sm btn-secondary"
                attrs['hx-post'] = reverse_lazy("core:form_sample_config_add_value_column", args=[col_number])
                attrs['hx-swap'] = "beforeend"
                attrs['hx-target'] = "#" + div_id_data_value_row_form

            td.append(button := soup.new_tag('button', attrs=attrs))
            button.string = col
        else:
            td.string = col


def get_sample_parser(request) -> SampleParser:
    file = request.FILES['sample_file']
    file_name = file.name
    file_type = file_name.split('.')[-1].upper()
    raw_data = file.read()  # the file can only be read once per POST request

    mission_id = int(request.GET.get('mission_id', 1))
    clear_form = request.GET.get('clear_form', None)
    tab = 0 if clear_form else int(request.POST.get('tab', 0))
    skip = -1 if clear_form else int(request.POST.get('skip', -1))
    sample_field = None if clear_form else request.POST.get('sample_field', None)
    comment_field = None if clear_form else request.POST.get('comment_field', None)
    allowed_replicates = 2 if clear_form else int(request.POST.get('allowed_replicates', 2))
    allow_blank_sample_replicates = True if clear_form else bool(request.POST.get('are_blank_sample_ids_replicates', False))

    sample_parser = SampleParser(mission_id, file_name, file_type, raw_data)
    (sample_parser
     .set_tab(tab).set_skip(skip)
     .set_sample_field(sample_field)
     .set_comment_field(comment_field)
     .set_allowed_replicates(allowed_replicates)
     .set_allow_blank_sample_ids(allow_blank_sample_replicates))

    return sample_parser


def reload_configs(request):
    soup = BeautifulSoup("", "html.parser")

    try:
        sample_parser = get_sample_parser(request)
    except django.utils.datastructures.MultiValueDictKeyError as ex:
        return HttpResponse()

    parsers = SampleFileType.objects.filter(
        file_type__icontains=sample_parser.get_file_type(),
        tab=sample_parser.get_tab(),
        skip=sample_parser.get_skip(),
        sample_field=sample_parser.get_sample_field(),
    )

    for parser in parsers:
        soup.append(ConfigCard(parser))
    return HttpResponse(soup)

def reload_header(request):
    soup = BeautifulSoup("", "html.parser")

    try:
        sample_parser = get_sample_parser(request)
    except django.utils.datastructures.MultiValueDictKeyError as ex:
        return HttpResponse()

    add_header_table(request, soup, sample_parser)

    response =  HttpResponse(soup.find(id=table_column_header_id))

    # we might eventually do this if we want to filter down configurations to configs matching what
    # a user has selected for now we just want to update the header column to turn buttons on and off.

    response['HX-Trigger-After-Settle'] = "reload_configs"

    return response


def reload_buttons(request, **kwargs):
    used_columns = [column.upper() for column in request.POST.getlist("value_field")]

    if len(used_columns) <= 0:
        return HttpResponse("")

    soup = ParserButtonRow()

    response = HttpResponse(soup)
    return response



def load_sample_config(request, **kwargs):
    soup = BeautifulSoup("", "html.parser")

    try:
        sample_parser = get_sample_parser(request)
    except django.utils.datastructures.MultiValueDictKeyError as ex:
        return HttpResponse()

    # add_header_table(request, soup, sample_parser)
    tab_names = sample_parser.get_tabs()
    try:
        headers = sample_parser.get_headers()
    except ValueError as ex:
        headers = None

    initial = {
        "file_type": sample_parser.get_file_type(),
        "tab": sample_parser.get_tab(),
        "skip": sample_parser.get_skip(),
        "sample_field": sample_parser.get_sample_field(),
        "comment_field": sample_parser.get_comment_field(),
        "allowed_replicates": sample_parser.get_allowed_replicates(),
        "are_blank_sample_ids_replicates": sample_parser.get_blank_samples_allowed(),
    }
    form = SampleFileTypeForm(tab_names=tab_names, headers=headers, initial=initial)
    html = render_crispy_form(form)
    soup.append(BeautifulSoup(html, "html.parser"))
    # soup.append(get_header_table_placeholder(soup))

    response = HttpResponse(soup)
    response['HX-Trigger-After-Settle'] = "reload_headers, reload_buttons"
    return response


def load_data_value_form(request, column_id, **kwargs):
    soup = BeautifulSoup("", "html.parser")

    if bool(request.GET.get('remove', False)):
        response = HttpResponse(soup)
        response['HX-Trigger-After-Settle'] = "reload_headers, reload_buttons"
        return response

    try:
        sample_parser = get_sample_parser(request)
    except django.utils.datastructures.MultiValueDictKeyError as ex:
        return HttpResponse()

    try:
        headers = sample_parser.get_headers()
    except ValueError as ex:
        headers = None

    initial = {
        'name': headers[column_id],
        'value_field': headers[column_id].upper(),
    }
    exclude = [sample_parser.get_comment_field(), sample_parser.get_sample_field(), initial['value_field']]
    coerced_headers = [header for header in headers if header.upper() not in exclude]
    form = SampleVariableForm(column_id=column_id, headers=coerced_headers, initial=initial)
    html = render_crispy_form(form)
    soup.append(BeautifulSoup(html, "html.parser"))

    response = HttpResponse(soup)
    response['HX-Trigger'] = "reload_headers"
    response['HX-Trigger-After-Settle'] = "reload_buttons"
    return response


def save(request):
    try:
        sample_parser = get_sample_parser(request)
    except django.utils.datastructures.MultiValueDictKeyError as ex:
        return HttpResponse()

    sft = sample_parser.get_sample_config()

    template_name = request.POST.get("config_name", "tmp")
    existing_sample_file_type = SampleFileType.objects.filter(name=template_name)

    if existing_sample_file_type.exists():
        if "save" in request.POST:
            msg_alert = StatusAlert("div_id_sample_type_config_save_alert",_("A config by this name already exists. Replace it?"), 'warning')
            msg_alert.get_message_container().append(div:=msg_alert.new_tag("div", attrs={"class": ""}))
            div.append(btn_row:=msg_alert.new_tag("div", attrs={"class": "row"}))
            btn_row.append(btn_col:=msg_alert.new_tag("div", attrs={"class": "col-auto"}))

            ok_icon = BeautifulSoup(load_svg("check-square"), "html.parser").svg
            ok_attrs = {
                "class": "btn btn-sm btn-secondary me-2",
                "title": _("Save over existing config"),
                "hx-post": request.path,
                "hx-target": "#" + div_id_parser_button_col,
                "hx-indicator": "#" + indicator_id,
            }
            btn_col.append(ok_btn:=msg_alert.new_tag("button", attrs=ok_attrs))
            ok_btn.append(ok_icon)
            ok_btn.attrs["name"] = "save_over"

            cancel_attrs = {
                "class": "btn btn-sm btn-secondary me-2",
                "title": _("Cancel"),
                "onclick": f"document.getElementById(`{msg_alert.component_id}_container`).remove();",
            }
            cancel_icon = BeautifulSoup(load_svg("x-square"), "html.parser").svg
            btn_col.append(cancel_btn:=msg_alert.new_tag("button", attrs=cancel_attrs))
            cancel_btn.append(cancel_icon)

            return HttpResponse(msg_alert)
        elif "save_over" in request.POST:
            sft = existing_sample_file_type.first()
            sft.variables.all().delete()

    sft.name = template_name

    sft.save()
    try:
        sample_variable_array = zip(
            request.POST.getlist('name'),
            request.POST.getlist('value_field'),
            request.POST.getlist('flag_field'),
            request.POST.getlist('limit_field')
        )

        for sample_variable in sample_variable_array:
            stv = SampleTypeVariable()
            stv.sample_type = sft
            stv.name = sample_variable[0]
            stv.value_field = sample_variable[1]
            stv.flag_field = sample_variable[2]
            stv.limit_field = sample_variable[3]
            stv.save()

    finally:
        if sft.name == 'tmp':
            sft.delete()

    msg_alert = StatusAlert("div_id_sample_type_config_save_alert", "Saved", 'success')
    msg_alert.include_close_button()

    response = HttpResponse(msg_alert)
    response['HX-Trigger-After-Settle'] = "reload_configs"
    return response


def parse(request, file_config_id):
    msg_alert = StatusAlert("parser_message")
    if not msg_alert.is_socket_connected(sampler_logger.name):
        msg_alert.set_socket(sampler_logger.name)
        msg_alert.include_progress_bar()
        response = HttpResponse(msg_alert)
        response['HX-Trigger-After-Settle'] = f"start_parsing_{file_config_id}"
        return response

    file = request.FILES['sample_file']
    file_name = file.name
    file_type = file_name.split('.')[-1].upper()
    raw_data = file.read()  # the file can only be read once per POST request

    mission_id = int(request.GET.get('mission_id', 1))

    sft = SampleFileType.objects.get(id=file_config_id)

    sample_parser = SampleParser(mission_id, file_name, file_type, raw_data)
    sample_parser.set_sample_config(sft)

    msg_alert.include_close_button()
    msg_alert.set_type('success')
    msg_alert.set_message("success")

    try:
        sample_parser.parse()
        errors = models.FileError.objects.filter(file_name__iexact=sample_parser.file_name)
        if errors:
            error_report = msg_alert.new_tag("div", attrs={"class": "vertical-scrollbar-sm"})
            for error in errors:
                error_report.append(err_row:=msg_alert.new_tag("div", attrs={}))
                err_row.string = error.message

            msg_alert.set_type('danger')
            msg_alert.set_message("Errors occurred parsing sample file.")
            msg_alert.alert_container.append(error_report)

    except Exception as ex:
        msg_alert.set_type('warning')
        msg_alert.set_message(str(ex))
        logger.exception(ex)

    response = HttpResponse(msg_alert)
    response['HX-Trigger'] = "update_samples"
    return response

url_patterns = [
    path(f'sample_config/', load_sample_config, name="form_sample_config_load"),
    path(f'sample_config/config/', reload_configs, name="form_sample_config_reload_configs"),
    path(f'sample_config/header/', reload_header, name="form_sample_config_reload_header"),
    path(f'sample_config/buttons/', reload_buttons, name="form_sample_config_reload_buttons"),
    path(f'sample_config/data_row_form/<int:column_id>/', load_data_value_form,
         name="form_sample_config_add_value_column"),

    path(f'sample_config/parse/<int:file_config_id>/', parse, name="form_sample_config_parse"),
    path(f'sample_config/save/', save, name="form_sample_config_save"),
]
