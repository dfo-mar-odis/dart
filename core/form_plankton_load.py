import easygui

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout, Row, Column, Div, HTML
from crispy_forms.utils import render_crispy_form

from django import forms
from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django_pandas.io import read_frame
from django.conf import settings

from core import models as core_models
from core import forms as core_forms
from core.forms import CollapsableCardForm
from core.parsers.PlanktonParser import parse_zooplankton, parse_phytoplankton, parse_zooplankton_bioness

from core.parsers.SampleParser import get_excel_dataframe
from core.parsers.BionessParser import parse_bioness

from dart.utils import load_svg

import os
import logging

debug_logger = logging.getLogger('dart.debug')
logger = logging.getLogger('dart')


class PlanktonForm(forms.Form):

    header = forms.IntegerField(label="Header Line")
    tab = forms.IntegerField(label="Tab")

    def __init__(self, mission, *args, **kwargs):
        self.mission = mission

        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        url = reverse_lazy("core:form_plankton_load_plankton", args=(mission.pk,))
        tab_field = Field('tab')
        tab_field.attrs['hx-post'] = url
        tab_field.attrs['hx-swap'] = "none"
        tab_field.attrs['class'] = "form-control form-control-sm"

        header_field = Field('header')
        header_field.attrs['hx-post'] = url
        header_field.attrs['hx-swap'] = "none"
        header_field.attrs['class'] = "form-control form-control-sm"

        importurl = reverse_lazy("core:form_plankton_import_plankton", args=(mission.pk,))
        button_attrs = {
            'title': _('Import'),
            'name': 'import',
            'hx_get': importurl,
            'hx_swap': 'none'
        }

        icon = load_svg('arrow-down-square')
        submit = StrictButton(icon, css_class="btn btn-sm btn-primary", **button_attrs)

        self.helper.layout = Layout(
            Row(
                Column(tab_field, css_class='col-auto'),
                Column(header_field, css_class='col-auto'),
                Column(submit, css_class="align-self-end mb-3"),
                css_class='input-group input-group-sm',
                id="div_id_plankton_form_details"
            )
        )


class MultinetLoadForm(CollapsableCardForm):

    net_volume_help_text = _("For single net plankton catches net volumes are computed based on the the surface area "
                             "a net covers (e.g [base * height] or [πr²]) and multiplied by distance the net traveled. "
                             "The travel distance is either the difference in a end flowmeter and a start flowmeter "
                             "reading multiplied by a manufacture provided constant of 0.3 or computed based on a "
                             "wire out formula, if no flowmeter is present. In the case of multinets there is often "
                             "accompanying files that identify the volume of water that passes through a net before "
                             "the net is closed. Dart provides a template that can assist in providing volume data.")

    def get_card_body(self) -> Div:
        body = super().get_card_body()

        load_icon = load_svg("arrow-up-square")
        url = reverse_lazy("core:form_plankton_upload_multinet", args=(self.mission.pk,))
        load_attrs = {
            'id': f"{self.card_name}_load_bottles",
            'hx-get': url,
            'hx-swap': 'none'
        }
        load_btn = StrictButton(load_icon, css_class="btn btn-primary btn-sm mb-2", **load_attrs)

        button_row = Row(
            Column(load_btn, css_class="col-auto"),
        )
        description_row = Row(
            Column(HTML("<p>" + self.net_volume_help_text + "</p>"), css_class="col"),
        )

        body.fields.append(description_row)
        body.fields.append(button_row)

        return body

    def __init__(self, mission, *args, **kwargs):

        self.mission = mission

        super().__init__(card_name="multinet_load", card_title=_("Load Net Volume"), *args, **kwargs)


def load_plankton(request, mission_id):
    mission = core_models.Mission.objects.get(pk=mission_id)

    if request.method == 'GET':
        # you can only get the file though a POST request
        url = request.path
        attrs = {
            'component_id': 'div_id_plankton_message',
            'message': _("Loading"),
            'alert_type': 'info',
            'hx-trigger': "load",
            'hx-swap-oob': 'true',
            'hx-post': url,
        }
        load_card = core_forms.save_load_component(**attrs)
        return HttpResponse(load_card)

    soup = BeautifulSoup('', 'html.parser')

    message_div = soup.new_tag('div')
    message_div.attrs['class'] = "mt-2"
    message_div.attrs['id'] = "div_id_message"
    message_div.attrs['hx-swap-oob'] = "true"
    soup.append(message_div)

    form_div = soup.new_tag('div')
    form_div.attrs['class'] = "row"
    form_div.attrs['id'] = "div_id_plankton_form"
    form_div.attrs['hx-swap-oob'] = "true"
    soup.append(form_div)

    attrs = {
        'component_id': 'div_id_message_alert',
        'message': _("Success"),
        'alert_type': 'success',
        'hx-swap-oob': 'true',
    }
    if 'plankton_file' not in request.FILES:
        attrs['message'] = 'No file chosen'
        attrs['alert_type'] = 'warning'
        post_card = core_forms.blank_alert(**attrs)
        message_div.append(post_card)

        return HttpResponse(soup)

    file = request.FILES['plankton_file']

    # determine the file type
    debug_logger.debug(file)

    # the file can only be read once per request
    data = file.read()
    file_type: str = file.name.split('.')[-1].lower()

    if file_type.startswith('xls'):
        debug_logger.debug("Excel format detected")

        # because this is an excel format, we now need to know what tab and line the header
        # appears on to figure out if this is zooplankton or phytoplankton
        tab = int(request.POST.get('tab', 1) or 1)
        tab = 1 if tab <= 0 else tab

        header = int(request.POST.get('header', -1) or -1)
        dict_vals = request.POST.copy()
        dict_vals['tab'] = tab
        dict_vals['header'] = header

        try:
            dataframe = get_excel_dataframe(stream=data, sheet_number=(tab-1), header_row=(header-1))
            start = dataframe.index.start if hasattr(dataframe.index, 'start') else 0
            dict_vals['header'] = max(start + 1, header)

            # If the file contains a 'What_was_it' column, then this is a zooplankton file.
            # problem is the column may be uppercase, lowercase, may be a mix, may contain spaces or
            # underscores and may or may not end with a question mark. It very typically is the last column,
            # unless a 'comment' column is present.

            table_html = dataframe.head(10).to_html()
            table_soup = BeautifulSoup(table_html, 'html.parser')
            table = table_soup.find('table')
            table.attrs['class'] = "table table-striped"

            table_div = soup.new_tag('div')
            table_div.attrs['class'] = 'vertical-scrollbar'
            table_div.append(table)
        except ValueError as e:
            logger.exception(e)
            attrs = {
                'component_id': "div_id_plankton_table",
                'alert_type': "danger",
                'message': e.args[0]
            }
            table_div = core_forms.blank_alert(**attrs)

        form = PlanktonForm(mission=mission, data=dict_vals)
        form_html = render_crispy_form(form)

        form_soup = BeautifulSoup(form_html, 'html.parser')
        form_soup.append(table_div)

        form_div.append(form_soup)

        response = HttpResponse(soup)

        return response

    post_card = core_forms.blank_alert(**attrs)
    message_div.append(post_card)
    return HttpResponse(soup)


def import_plankton(request, mission_id):

    mission = core_models.Mission.objects.get(pk=mission_id)

    if request.method == 'GET':
        # you can only get the file though a POST request
        url = reverse_lazy('core:form_plankton_import_plankton', args=(mission.pk,))
        component_id = "div_id_plankton_message"
        attrs = {
            'component_id': component_id,
            'message': _("Loading"),
            'alert_type': 'info',
            'hx-trigger': "load",
            'hx-swap-oob': 'true',
            'hx-post': url,
            'hx-ext': "ws",
            'ws-connect': f"/ws/biochem/notifications/{component_id}/"
        }
        load_card = core_forms.save_load_component(**attrs)

        return HttpResponse(load_card)

    soup = BeautifulSoup('', 'html.parser')

    message_div = soup.new_tag('div')
    message_div.attrs['class'] = "mt-2"
    message_div.attrs['id'] = "div_id_plankton_message"
    message_div.attrs['hx-swap-oob'] = "true"
    soup.append(message_div)

    form_div = soup.new_tag('div')
    form_div.attrs['class'] = "row"
    form_div.attrs['id'] = "div_id_plankton_form"
    form_div.attrs['hx-swap-oob'] = "true"
    soup.append(form_div)

    attrs = {
        'component_id': 'div_id_message_alert',
        'message': _("Success"),
        'alert_type': 'success',
        'hx-swap-oob': 'true',
    }

    if 'plankton_file' not in request.FILES:
        attrs['message'] = 'No file chosen'
        attrs['alert_type'] = 'warning'
        message_div.append(core_forms.blank_alert(**attrs))
        return HttpResponse(soup)

    file = request.FILES['plankton_file']

    # the file can only be read once per request
    data = file.read()

    # because this is an excel format, we now need to know what tab and line the header
    # appears on to figure out if this is zoo or phyto plankton
    tab = int(request.POST.get('tab', 1) or 1)
    header = int(request.POST.get('header', 1) or 1)

    try:
        dataframe = get_excel_dataframe(stream=data, sheet_number=(tab - 1), header_row=(header - 1))
        dataframe.columns = map(str.upper, dataframe.columns)

        try:
            if 'WHAT_WAS_IT' in dataframe.columns:
                if 'START_DEPTH' and 'END_DEPTH' in dataframe.columns:
                    parse_zooplankton_bioness(mission, file.name, dataframe)
                else:
                    parse_zooplankton(mission, file.name, dataframe)
            else:
                parse_phytoplankton(mission, file.name, dataframe)

            if (errs := mission.file_errors.filter(file_name__iexact=file.name)).exists():
                # might as well add the list of issues while loading the file to the response so the
                # user knows what went wrong.
                attrs['message'] = _("Completed with issues")
                attrs['alert_type'] = 'warning'
                alert = core_forms.blank_alert(**attrs)
                ul = soup.new_tag('ul')
                ul.attrs['class'] = 'vertical-scrollbar-sm'
                for err in errs:
                    li = soup.new_tag('li')
                    li.string = err.message
                    ul.append(li)
                alert.find('div').find('div').append(ul)
            else:
                alert = core_forms.blank_alert(**attrs)
        except KeyError as e:
            errs = mission.file_errors.filter(file_name__iexact=file.name)
            attrs['message'] = _("Could not load with issues")
            attrs['alert_type'] = 'danger'
            alert = core_forms.blank_alert(**attrs)
            ul = soup.new_tag('ul')
            ul.attrs['class'] = 'vertical-scrollbar-sm'
            for err in errs:
                li = soup.new_tag('li')
                li.string = err.message
                ul.append(li)
            alert.find('div').find('div').append(ul)

        message_div.append(alert)
        # clear the file input upon success
        file_input = soup.new_tag('input')
        file_input.attrs['id'] = "id_input_sample_file"
        file_input.attrs['class'] = "form-control form-control-sm"
        file_input.attrs['hx-swap-oob'] = "true"
        file_input.attrs['type'] = "file"
        file_input.attrs['name'] = "plankton_file"
        file_input.attrs['accept'] = ".xls,.xlsx,.xlsm"
        file_input.attrs['hx-trigger'] = "change"
        file_input.attrs['hx-get'] = reverse_lazy('core:form_plankton_load_plankton', args=(mission_id,))
        file_input.attrs['hx-swap'] = "none"

        soup.append(file_input)
    except ValueError as e:
        logger.exception(e)
        attrs = {
            'component_id': "div_id_plankton_table",
            'alert_type': "danger",
            'message': e.args[0]
        }
        message_div.append(core_forms.blank_alert(**attrs))
    except Exception as e:
        logger.exception(e)
        attrs = {
            'component_id': "div_id_plankton_table",
            'alert_type': "danger",
            'message': _("An unknown issue occurred (see ./logs/error.log).")
        }
        message_div.append(core_forms.blank_alert(**attrs))

    response = HttpResponse(soup)
    response['HX-Trigger'] = 'update_samples'
    return response


def list_plankton(request, mission_id):

    mission = core_models.Mission.objects.get(pk=mission_id)

    soup = BeautifulSoup('', "html.parser")
    div = soup.new_tag('div')
    div.attrs['id'] = "div_id_plankton_data_table"
    div.attrs['hx-trigger'] = 'update_samples from:body'
    div.attrs['hx-get'] = reverse_lazy('core:form_plankton_list_plankton', args=(mission.pk,))
    div.attrs['hx-swap-oob'] = 'true'
    soup.append(div)

    page = int(request.GET.get('page', 0) or 0)
    page_limit = 50
    page_start = page_limit * page

    samples = core_models.PlanktonSample.objects.filter(bottle__event__mission=mission).order_by(
        'bottle__event__instrument__type', 'bottle__bottle_id'
    )
    if samples.exists():
        data_columns = ["Sample", "Pressure", "Station", "Type", "Name", "Modifier", "Sex", "Stage", "Split", "Count",
                        "Wet", "Dry", "Volume", "Percent", "Comments"]

        samples = samples.values("bottle__bottle_id", "bottle__pressure", 'bottle__event__station__name',
                                 "bottle__event__instrument__type", "taxa__taxonomic_name", "modifier", "sex__name",
                                 "stage__name", "split_fraction", "count", "raw_wet_weight", "raw_dry_weight", "volume",
                                 "percent", "comments")
        samples = samples[page_start:(page_start + page_limit)]

        dataframe = read_frame(samples)
        dataframe.columns = data_columns
        dataframe.fillna('---', inplace=True)
        dataframe['Type'] = dataframe['Type'].map({1: "phyto", 2: "zoo"}, na_action='ignore')

        style = dataframe.style.hide(axis="index")

        table_html = style.to_html()
        table_soup = BeautifulSoup(table_html, 'html.parser')

        table = table_soup.find('table')
        sample_th = table.find('thead').find('tr').find('th')
        sample_th.string = ""

        database = settings.DATABASES[mission._state.db]['LOADED']
        button = soup.new_tag('A', attrs={'class': 'btn btn-sm btn-primary', 'href': reverse_lazy("core:mission_gear_type_details", args=(database, mission_id, core_models.InstrumentType.net.value))})
        button.string = _("Sample")
        sample_th.append(button)

        table.attrs['class'] = 'dataframe table table-striped table-sm tscroll horizontal-scrollbar'
        trs = table.find('tbody').find_all('tr')
        if len(trs) > 0:
            url = reverse_lazy('core:form_plankton_list_plankton', args=(mission.pk,))
            last_tr = trs[-1]
            last_tr.attrs['hx-trigger'] = 'intersect once'
            last_tr.attrs['hx-get'] = url + f"?page={page + 1}"
            last_tr.attrs['hx-swap'] = "afterend"

        div.append(table)
        if page > 0:
            return HttpResponse(table.find('tbody').find_all('tr'))

        return HttpResponse(soup)

    alert_attrs = {
        'component_id': 'div_id_plankton_data_table_alert',
        'alert_type': 'info',
        'message': _("No Plankton samples loaded")
    }
    alert_soup = core_forms.blank_alert(**alert_attrs)
    div.append(alert_soup)

    return HttpResponse(soup)


def get_multinet_load_card(request, mission_id, **kwargs):
    context = {}

    initial = {}
    if 'hide_loaded' in request.GET:
        initial = {'hide_loaded': "true"}

    collapsed = False if 'collapsed' in kwargs else True
    mission = core_models.Mission.objects.get(pk=mission_id)
    multinet_load_form = MultinetLoadForm(mission=mission, collapsed=collapsed, initial=initial)
    multinet_load_html = render_crispy_form(multinet_load_form, context=context)
    multinet_load_soup = BeautifulSoup(multinet_load_html, 'html.parser')

    return multinet_load_soup


def get_multinet_data_card(request, mission_id, **kwargs):
    multinet_load_soup = get_multinet_load_card(request, mission_id, **kwargs)
    first_elm = multinet_load_soup.find(recursive=False)
    form_id = first_elm.attrs['id']
    form_soup = BeautifulSoup(f'<form id="form_id_{form_id}"></form>', 'html.parser')
    form = form_soup.find('form')
    form.append(multinet_load_soup)

    return HttpResponse(form_soup)


def upload_multinet(request, mission_id, **kwargs):
    mission = core_models.Mission.objects.get(pk=mission_id)
    result = easygui.fileopenbox("Open multinet file", "Multinet", default="*", filetypes="*.T**", multiple=True)

    if result:
        for file in result:
            parse_bioness(mission, file)

    return HttpResponse()

url_prefix = "plankton"
plankton_urls = [
    path(f'{url_prefix}/card/<int:mission_id>/', get_multinet_data_card, name="form_plankton_multinet_card"),
    path(f'{url_prefix}/multinet/<int:mission_id>/', upload_multinet, name="form_plankton_upload_multinet"),

    path(f'{url_prefix}/load/<int:mission_id>/', load_plankton, name="form_plankton_load_plankton"),
    path(f'{url_prefix}/import/<int:mission_id>/', import_plankton, name="form_plankton_import_plankton"),
    path(f'{url_prefix}/list/<int:mission_id>/', list_plankton, name="form_plankton_list_plankton"),

]
