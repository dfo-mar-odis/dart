import csv
import io
from pathlib import Path

import numpy as np
import os
import threading
import easygui

from threading import Thread

import bs4
import pandas as pd
from bs4 import BeautifulSoup

from crispy_forms.utils import render_crispy_form
from django.conf import settings

from django.db.models import Max, QuerySet, Q
from django.http import HttpResponse, Http404
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django_pandas.io import read_frame

from render_block import render_block_to_string

import biochem.upload
import core.form_btl_load
from biochem import models as biochem_models
from bio_tables import models as bio_models

from core import forms, form_biochem_database, validation
from core import models
from core import views
from core.htmx import send_user_notification_html_update
from core.parsers import SampleParser

from dart2.utils import load_svg

from dart2.views import GenericDetailView

import logging

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')


def process_file(file) -> [str, str, str]:
    file_name = file.name
    file_type = file_name.split('.')[-1].lower()

    # the file can only be read once per request
    data = file.read()

    return file_name, file_type, data


def get_file_config_forms(data, file_type):
    config_forms = []
    file_configs = SampleParser.get_file_configs(data, file_type)

    if file_configs:
        for config in file_configs:
            config_forms.append(

            )

    return config_forms


def get_error_list(soup, card_id, errors):
    msg_div = soup.find(id=f'{card_id}_message')
    if not msg_div:
        msg_div = soup.new_tag('div')
        msg_div.attrs['class'] = ''
        msg_div.attrs['id'] = f'{card_id}_message'
        soup.append(msg_div)

    msg_div_error_card = soup.new_tag('div')
    msg_div_error_card.attrs['class'] = 'card mt-2'
    msg_div.append(msg_div_error_card)

    msg_div_error_card_header = soup.new_tag('div')
    msg_div_error_card_header.attrs['class'] = 'card-header text-bg-warning'
    msg_div_error_card.append(msg_div_error_card_header)

    msg_div_error_title = soup.new_tag('div')
    msg_div_error_title.string = _("Warnings")
    msg_div_error_title.attrs['class'] = 'card-title'
    msg_div_error_card_header.append(msg_div_error_title)

    msg_div_error_card_body = soup.new_tag('div')
    msg_div_error_card_body.attrs['class'] = 'card-body vertical-scrollbar-sm'
    msg_div_error_card.append(msg_div_error_card_body)

    ul_list = soup.new_tag('ul')
    ul_list['id'] = f'{card_id}_error_list'
    ul_list['class'] = 'list-group'
    msg_div_error_card_body.append(ul_list)
    for error in errors:
        li = soup.new_tag('li')
        li['class'] = 'list-group-item'
        li.string = error.message
        ul_list.append(li)


def get_sensor_table_button(soup: BeautifulSoup, mission_id: int, sampletype_id: int):
    sampletype = models.MissionSampleType.objects.get(pk=sampletype_id)

    sensor: QuerySet[models.BioChemUpload] = sampletype.uploads.all()

    dc_samples = models.DiscreteSampleValue.objects.filter(
        sample__bottle__event__mission_id=mission_id, sample__type_id=sampletype_id)

    row_datatype = dc_samples.values_list("sample_datatype", flat=True).distinct().first()
    datatype = sampletype.datatype if sampletype.datatype else None

    # if no datatype is applied
    button_colour = 'btn-danger'

    title = sampletype.long_name if sampletype.long_name else sampletype.name
    if datatype:
        # if the datatype is applied at the 'standard'
        button_colour = 'btn-secondary'
        title += f': {datatype}'
    elif row_datatype:
        # if the datatype is applied at the mission level or row level
        button_colour = 'btn-warning'
    else:
        title += f': ' + _('Missing Biochem datatype')

    if sensor.exists():
        uploaded = sensor.first().upload_date
        modified = sensor.first().modified_date

        if uploaded:
            if modified < uploaded:
                # if the sensor was uploaded
                button_colour = 'btn-success'
            else:
                button_colour = 'btn-primary'

    button = soup.new_tag("button")
    button.string = f'{sampletype.name}'
    button.attrs['id'] = f'button_id_sample_type_details_{sampletype.pk}'
    button.attrs['class'] = 'btn btn-sm ' + button_colour
    button.attrs['style'] = 'width: 100%'
    button.attrs['hx-get'] = reverse_lazy('core:mission_samples_sample_details', args=(mission_id, sampletype.pk,))
    button.attrs['hx-target'] = "#sample_table"
    button.attrs['hx-push-url'] = 'true'
    button.attrs['title'] = title

    return button


def get_sensor_table_upload_checkbox(soup: BeautifulSoup, mission_id: int, sampletype_id: int):

    enabled = False
    sample_type = models.MissionSampleType.objects.get(pk=sampletype_id)
    if sample_type.datatype:
        # a sample must have either a Standard level or Mision level data type to be uploadable.
        enabled = True

    check = soup.new_tag('input')
    check.attrs['id'] = f'input_id_sample_type_{sampletype_id}'
    check.attrs['type'] = 'checkbox'
    check.attrs['value'] = sampletype_id
    check.attrs['hx-swap'] = 'outerHTML'
    check.attrs['hx-target'] = f"#{check.attrs['id']}"
    check.attrs['hx-post'] = reverse_lazy('core:mission_samples_add_sensor_to_upload',
                                          args=(mission_id, sampletype_id,))

    if enabled:
        if models.BioChemUpload.objects.filter(type_id=sampletype_id).exists():
            check.attrs['name'] = 'remove_sensor'
            check.attrs['checked'] = 'checked'
        else:
            check.attrs['name'] = 'add_sensor'
    else:
        check.attrs['disabled'] = 'true'
        check.attrs['title'] = _("Requires a Standard or Mission level Biochem Datatype")

    return check


class SampleDetails(views.MissionMixin, GenericDetailView, ):
    page_title = _("Mission Samples")
    template_name = "core/mission_samples.html"

    def get_page_title(self):
        return _("Mission Samples") + " : " + self.object.name

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reports'] = {key: reverse_lazy(views.reports[key], args=(self.object.pk,)) for key in
                              views.reports.keys()}

        context['mission'] = self.object
        if 'sample_type_id' in self.kwargs:
            sample_type = models.MissionSampleType.objects.get(pk=self.kwargs['sample_type_id'])
            context['sample_type'] = sample_type
            data_type_seq = sample_type.datatype

            initial = {}
            initial['sample_type_id'] = sample_type.id
            initial['mission_id'] = self.object.id
            if data_type_seq:
                initial['data_type_code'] = data_type_seq.data_type_seq

            context['biochem_form'] = forms.BioChemDataType(initial=initial)
        else:
            context['bottle_form'] = core.form_btl_load.BottleLoadForm(mission_id=self.object.pk,
                                                                       initial={'hide_loaded': "true"})

        return context


def get_sample_config_form(request, sample_type, **kwargs):
    if sample_type == -1:
        config_form = render_crispy_form(forms.SampleTypeConfigForm(file_type="", field_choices=[]))
        soup = BeautifulSoup(config_form, 'html.parser')

        # Drop the current existing dropdown from the form and replace it with a new sample type form
        sample_drop_div = soup.find(id='div_id_sample_type')
        sample_drop_div.attrs['class'] = 'col'

        children = sample_drop_div.findChildren()
        for child in children:
            child.decompose()

        sample_type_form = kwargs['sample_type_form'] if 'sample_type_form' in kwargs else forms.SampleTypeForm
        context = {'sample_type_form': sample_type_form, "expanded": True}
        new_sample_form = render_to_string('core/partials/form_sample_type.html', context=context)

        new_form_div = BeautifulSoup(new_sample_form, 'html.parser')
        sample_drop_div.append(new_form_div)

        # add a back button to the forms button_row/button_column
        url = reverse_lazy('core:mission_samples_new_sample_config') + "?sample_type="
        back_button = soup.new_tag('button')
        back_button.attrs = {
            'id': 'id_new_sample_back',
            'class': 'btn btn-primary btn-sm ms-2',
            'name': 'back_sample',
            'hx-target': '#div_id_sample_type',
            'hx-select': '#div_id_sample_type',
            'hx-swap': 'outerHTML',
            'hx-get': url
        }
        icon = BeautifulSoup(load_svg('arrow-left-square'), 'html.parser').svg
        back_button.append(icon)
        sample_drop_div.find(id="div_id_sample_type_button_col").insert(0, back_button)

        # redirect the submit button to this forms save function
        submit_button = sample_drop_div.find(id="button_id_new_sample_type_submit")

        url = reverse_lazy('core:mission_samples_save_sample_config')
        submit_button.attrs['hx-target'] = '#div_id_sample_type'
        submit_button.attrs['hx-select'] = '#div_id_sample_type'
        submit_button.attrs['hx-swap'] = 'outerHTML'
        submit_button.attrs['hx-post'] = url
    else:
        config_form = render_crispy_form(forms.SampleTypeConfigForm(file_type="", field_choices=[],
                                                                    initial={'sample_type': sample_type}))
        soup = BeautifulSoup(config_form, 'html.parser')

    return soup


def save_sample_config(request, **kwargs):
    # Validate and save the mission form once the user has filled out the details
    #
    # Template: 'core/partials/form_sample_type.html template
    #
    # return the sample_type_block if the sample_type or the file configuration forms fail
    # returns the loaded_samples_block if the forms validate and the objects are created

    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        if 'config_id' in kwargs and 'update_sample_type' in request.GET:
            sample_type = models.SampleTypeConfig.objects.get(pk=kwargs['config_id'])
            url = reverse_lazy("core:mission_samples_save_sample_config", args=(sample_type.pk,))
            oob_select = f"#div_id_sample_type_holder"
        else:
            url = reverse_lazy("core:mission_samples_save_sample_config")
            oob_select = "#div_id_sample_type_holder, #div_id_loaded_samples_list:beforeend"

        attrs = {
            'component_id': "div_id_loaded_sample_type_message",
            'message': _('Saving'),
            'alert_type': 'info',
            'hx-trigger': "load",
            'hx-target': "#div_id_sample_type_holder",
            'hx-post': url,
            'hx-select-oob': oob_select
        }
        soup = forms.save_load_component(**attrs)

        return HttpResponse(soup)
    elif request.method == "POST":

        if 'new_sample' in request.POST:
            # if the new_sample_config method requires the user to create a new sample type we'll
            # save the sample_type form here and return the whole sample_config_form with either the
            # new sample type or the config form with the invalid sample_type_form
            sample_form = forms.SampleTypeForm(request.POST)
            if sample_form.is_valid():
                sample_type = sample_form.save()
                soup = get_sample_config_form(request, sample_type=sample_type.pk)
                return HttpResponse(soup)

            soup = get_sample_config_form(request, sample_type=-1, sample_type_form=sample_form)
            return HttpResponse(soup)

        # mission_id is a hidden field in the 'core/partials/form_sample_type.html' template, if it's needed
        # mission_id = request.POST['mission_id']

        # I don't know how to tell the user what is going on here if no sample_file has been chosen
        # They shouldn't even be able to view the rest of the form with out it.
        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        tab = int(request.POST['tab']) if 'tab' in request.POST else 0
        skip = int(request.POST['skip']) if 'skip' in request.POST else 0

        tab, skip, field_choices = SampleParser.get_headers(data, file_type, tab, skip)

        config = None
        if 'config_id' in kwargs:
            config = models.SampleTypeConfig.objects.get(pk=kwargs['config_id'])
            sample_type_config_form = forms.SampleTypeConfigForm(request.POST, instance=config,
                                                                 field_choices=field_choices)
        else:
            sample_type_config_form = forms.SampleTypeConfigForm(request.POST, field_choices=field_choices)

        if sample_type_config_form.is_valid():
            sample_config: models.SampleTypeConfig = sample_type_config_form.save()
            # the load form is immutable to the user it just allows them the delete, send for edit or load the
            # sample into the mission
            html = render_to_string('core/partials/card_sample_config.html',
                                    context={'sample_config': sample_config})
            soup = BeautifulSoup(html, 'html.parser')

            div_id = f"div_id_sample_config_card_{sample_config.id}"
            div = soup.find(id=div_id)
            if 'config_id' in kwargs:
                div.attrs['hx-swap-oob'] = f"#{div_id}"
            else:
                new_root = soup.new_tag('div')
                new_root.attrs['id'] = "div_id_loaded_samples_list"
                new_root.append(div)
                soup.append(new_root)

            return HttpResponse(soup)

        html = render_crispy_form(sample_type_config_form)
        return HttpResponse(html)


def new_sample_config(request, **kwargs):
    context = {}
    context.update(csrf(request))

    if request.method == "GET":

        if 'sample_type' in request.GET:
            sample_type = int(request.GET['sample_type']) if request.GET['sample_type'] else 0
            soup = get_sample_config_form(request, sample_type, **kwargs)
            return HttpResponse(soup)

        # return a loading alert that calls this methods post request
        # Let's make some soup
        url = reverse_lazy("core:mission_samples_new_sample_config")

        attrs = {
            'component_id': "div_id_loaded_sample_type_message",
            'message': _("Loading"),
            'alert_type': 'info',
            'hx-post': url,
            'hx-target': "#div_id_sample_type_holder",
            'hx-trigger': "load"
        }
        soup = forms.save_load_component(**attrs)

        return HttpResponse(soup)
    elif request.method == "POST":

        if 'sample_file' not in request.FILES:
            soup = BeautifulSoup('<div id="div_id_sample_type_holder"></div>', 'html.parser')

            div = soup.new_tag('div')
            div.attrs['class'] = 'alert alert-warning mt-2'
            div.string = _("File is required before adding sample")
            soup.find(id="div_id_sample_type_holder").append(div)
            return HttpResponse(soup)

        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        if 'config_id' in kwargs:
            config = models.SampleTypeConfig.objects.get(pk=kwargs['config_id'])
            tab, skip, field_choices = SampleParser.get_headers(data, config.file_type, config.tab, config.skip)
            sample_config_form = forms.SampleTypeConfigForm(instance=config, field_choices=field_choices)
        else:
            tab = int(request.POST['tab']) if 'tab' in request.POST else 0
            skip = int(request.POST['skip']) if 'skip' in request.POST else -1
            field_choices = []

            try:
                tab, skip, field_choices = SampleParser.get_headers(data, file_type, tab, skip)
            except Exception as ex:
                logger.exception(ex)
                if isinstance(ex, ValueError):
                    logger.error("Likely chosen tab or header line is outside of the workbook")
                pass

            file_initial = {"file_type": file_type, "skip": skip, "tab": tab}
            if 'sample_type' in kwargs:
                file_initial['sample_type'] = kwargs['sample_type']
            sample_config_form = forms.SampleTypeConfigForm(initial=file_initial, field_choices=field_choices)

        html = render_crispy_form(sample_config_form)
        return HttpResponse(html)


def get_file_error_card(request, **kwargs):
    soup = BeautifulSoup("", "html.parser")

    errors = models.FileError.objects.filter(mission_id=request.GET['mission_id'], file_name=request.GET['file_name'])
    if errors.exists():
        attrs = {
            'card_name': "file_warnings",
            'card_title': _("File Warnings"),
            'card_class': "text-bg-warning"
        }
        error_card_form = forms.CollapsableCardForm(**attrs)
        error_card_html = render_crispy_form(error_card_form)
        error_card = BeautifulSoup(error_card_html, 'html.parser')

        card_div = error_card.find("div")

        card_body = card_div.find(id=error_card_form.get_card_body_id())
        card_body.attrs['class'].append('vertical-scrollbar-sm')

        ul = soup.new_tag("ul")
        card_body.append(ul)
        for error in errors:
            li = soup.new_tag('li')
            li.string = error.message
            ul.append(li)

        soup.append(card_div)
    return HttpResponse(soup)


def load_sample_config(request, **kwargs):
    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        if 'reload' in request.GET:
            response = HttpResponse()
            response['HX-Trigger'] = 'reload_sample_file'
            return response

        mission_id = request.GET['mission'] if 'mission' in request.GET else None
        loading = 'sample_file' in request.GET

        if loading:
            # Let's make some soup
            url = reverse_lazy("core:mission_samples_load_sample_config")

            soup = BeautifulSoup('', "html.parser")

            div_sampletype_holder = soup.new_tag("div")
            div_sampletype_holder.attrs['id'] = "div_id_sample_type_holder"
            div_sampletype_holder.attrs['hx-swap-oob'] = "true"

            div_loaded_sample_types = soup.new_tag("div")
            div_loaded_sample_types.attrs['id'] = "div_id_loaded_samples_list"
            div_loaded_sample_types.attrs['hx-swap-oob'] = "true"

            attrs = {
                'component_id': "div_id_loaded_sample_type_message",
                'message': _("Loading"),
                'alert_type': 'info',
                'hx-post': url,
                'hx-trigger': "load",
                'hx-swap-oob': "#div_id_sample_type_holder",
            }
            dialog_soup = forms.save_load_component(**attrs)

            div_sampletype_holder.append(dialog_soup)

            soup.append(div_sampletype_holder)
            soup.append(div_loaded_sample_types)

            return HttpResponse(soup)

        if request.htmx:
            # if this is an htmx request it's to grab an updated element from the form, like the BioChem Datatype
            # field after the Datatype_filter has been triggered.
            sample_config_form = forms.SampleTypeConfigForm(file_type="", field_choices=[], initial=request.GET)
            html = render_crispy_form(sample_config_form)
            return HttpResponse(html)

        if mission_id is None:
            raise Http404(_("Mission does not exist"))

        context['mission'] = models.Mission.objects.get(pk=mission_id)
        html = render_to_string("core/mission_samples.html", request=request, context=context)
        return HttpResponse(html)
    elif request.method == "POST":

        if 'sample_file' not in request.FILES:
            context['message'] = _("File is required before adding sample")
            html = render_block_to_string("core/partials/form_sample_type.html", "sample_type_block", context=context)
            return HttpResponse(html)

        if 'config' in kwargs:
            return new_sample_config(request, config=kwargs['config'])
        mission_id = request.POST['mission_id']
        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        # If mission ID is present this is an initial page load from the sample_file input
        # We want to locate file configurations that match this file_type
        file_configs = SampleParser.get_file_configs(data, file_type)

        soup = BeautifulSoup("", 'html.parser')
        div_sample_type_holder = soup.new_tag("div")
        div_sample_type_holder.attrs['id'] = "div_id_sample_type_holder"
        div_sample_type_holder.attrs['hx-swap-oob'] = 'true'

        soup.append(div_sample_type_holder)

        div_sample_type_list = soup.new_tag("div")
        div_sample_type_list.attrs['id'] = "div_id_loaded_samples_list"
        div_sample_type_list.attrs['class'] = "mt-2"
        div_sample_type_holder.append(div_sample_type_list)

        if file_configs:

            file_error_url = reverse_lazy("core:mission_samples_get_file_errors")
            file_error_url += f"?mission_id={mission_id}&file_name={file_name}"
            div_error_list = soup.new_tag('div')
            div_error_list.attrs['id'] = "div_id_error_list"
            div_error_list.attrs['hx-get'] = file_error_url
            div_error_list.attrs['hx-trigger'] = "load, file_errors_updated from:body"
            div_sample_type_list.append(div_error_list)

            for config in file_configs:
                html = render_to_string('core/partials/card_sample_config.html', context={'sample_config': config})
                sample_type = BeautifulSoup(html, 'html.parser')
                div_sample_type_list.append(sample_type.find("div"))
        else:
            attrs = {
                'component_id': "div_id_loaded_samples_alert",
                'message': _("No File Configurations Found"),
                'type': 'info'
            }
            alert_div = forms.blank_alert(**attrs)
            soup.find(id="div_id_sample_type_holder").append(alert_div)

        # html = render_block_to_string("core/partials/form_sample_type.html", "loaded_samples_block",
        #                               context=context)
        return HttpResponse(soup)


def load_samples(request, **kwargs):
    # Either delete a file configuration or load the samples from the sample file

    if 'config_id' not in kwargs:
        raise Http404("Missing Sample ID")

    config_id = kwargs['config_id']
    load_block = "loaded_sample_list_block"

    if request.method == "GET":

        message_div_id = f'div_id_sample_config_card_{config_id}'
        soup = BeautifulSoup(f'', 'html.parser')
        root_div = soup.new_tag("div")
        root_div.attrs['id'] = f'{message_div_id}_message'

        url = reverse_lazy("core:mission_samples_load_samples", args=(config_id,))
        attrs = {
            'component_id': f'div_id_loading_{message_div_id}',
            'message': _("Loading"),
            'alert_type': 'info',
            'hx-select': f"#{message_div_id}_load_button",
            'hx-target': f'#{message_div_id}_load_button',
            'hx-post': url,
            'hx-trigger': "load",
            'hx-swap': "outerHTML",
            'hx-select-oob': f"#{message_div_id}_message"
        }
        dialog_soup = forms.save_load_component(**attrs)
        message_div = dialog_soup.find(id=f'div_id_loading_{message_div_id}')

        button = soup.new_tag('button')
        button.attrs['id'] = f'{message_div_id}_load_button'
        button.attrs['class'] = "btn btn-secondary btn-sm placeholder-glow"
        button.attrs['disabled'] = "True"
        icon = BeautifulSoup(load_svg("folder"), 'html.parser').svg
        icon.attrs['class'] = 'placeholder'

        button.append(icon)

        soup.append(button)
        root_div.append(message_div)
        soup.append(root_div)

        return HttpResponse(soup)

    elif request.method == "POST":
        mission_id = request.POST['mission_id']
        message_div_id = f'div_id_sample_config_card_{config_id}'

        context = {}
        if 'sample_file' not in request.FILES:
            context['message'] = _("File is required before adding sample")
            html = render_block_to_string("core/partials/form_sample_type.html", load_block,
                                          context=context)
            return HttpResponse(html)

        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        sample_config = models.SampleTypeConfig.objects.get(pk=config_id)
        mission = models.Mission.objects.get(pk=mission_id)

        mission_sample_config = models.MissionSampleConfig.objects.filter(mission=mission, config=sample_config)
        if mission_sample_config.exists():
            mission_sample_config = mission_sample_config[0]
        else:
            mission_sample_config = models.MissionSampleConfig(mission=mission, config=sample_config)
            mission_sample_config.save()

        if file_type == 'csv' or file_type == 'dat':
            io_stream = io.BytesIO(data)
            dataframe = pd.read_csv(filepath_or_buffer=io_stream, header=sample_config.skip)
        else:
            dataframe = SampleParser.get_excel_dataframe(stream=data, sheet_number=sample_config.tab,
                                                         header_row=sample_config.skip)

        soup = BeautifulSoup('', 'html.parser')

        button_class = "btn btn-success btn-sm"
        icon = BeautifulSoup(load_svg("arrow-down-square"), 'html.parser').svg
        try:
            logger.info(f"Starting sample load for file {file_name}")

            # Remove any row that is *all* nan values
            dataframe.dropna(axis=0, how='all', inplace=True)

            SampleParser.parse_data_frame(settings=mission_sample_config, file_name=file_name, dataframe=dataframe)

            # if the datatypes are valid, then before we upload we should copy any 'standard' level biochem data types
            # to the mission level
            user_logger.info(_("Copying Mission Datatypes"))

            # once loaded apply the default sample type as a mission sample type so that if the default type is ever
            # changed it won't affect the data type for this mission
            sample_type = mission_sample_config.config.sample_type
            if sample_type.datatype and not mission.mission_sample_types.filter(sample_type=sample_type).exists():
                mst = models.MissionSampleType(mission=mission, sample_type=sample_type,
                                               datatype=sample_type.datatype)
                mst.save()

            if (errors := models.FileError.objects.filter(mission_id=mission_id, file_name=file_name)).exists():
                button_class = "btn btn-warning btn-sm"
                # get_error_list(soup, message_div_id, errors)

            # create an empty message div to remove the loading alert
            msg_div = soup.new_tag('div')
            msg_div.attrs['id'] = f'{message_div_id}_message'
            soup.append(msg_div)

        except Exception as ex:
            logger.error(f"Failed to load file {file_name}")
            logger.exception(ex)
            button_class = "btn btn-danger btn-sm"

        # url = reverse_lazy('core:mission_samples_load_samples', args=(file_config.pk,))
        button = soup.new_tag('button')
        button.attrs = {
            'id': f"{message_div_id}_load_button",
            'class': button_class,
            'name': "load",
            'hx-get': reverse_lazy('core:mission_samples_load_samples', args=(config_id,)),
            'hx-swap': "outerHTML",
            'hx-target': f"#{message_div_id}_load_button",
            'hx-select': f"#{message_div_id}_load_button",
            'hx-select-oob': f"#{message_div_id}_message"
        }

        soup.append(button)
        button.append(icon)

        response = HttpResponse(soup)

        # This will trigger the Sample table on the 'core/mission_samples.html' template to update
        response['HX-Trigger'] = 'update_samples, file_errors_updated'
        return response


def delete_sample_config(request, **kwargs):
    config_id = kwargs['config_id']
    if request.method == "POST":
        if models.MissionSampleConfig.objects.filter(config_id=config_id).exists():
            models.MissionSampleConfig.objects.get(config_id=config_id).delete()
        models.SampleTypeConfig.objects.get(pk=config_id).delete()

    return HttpResponse()


def sample_upload_ctd(request, mission_id):
    context = {}
    context.update(csrf(request))

    thread_name = "load_ctd_files"

    if request.method == "GET":
        if 'show_all' not in request.GET and 'file_name' in request.GET:
            # We're going to throw up a loading alert to call the hx-post and clear the selection form off the page,
            # then we'll swap in the Websocket connected dialog from the POST method to give feedback to the user
            url = reverse_lazy('core:mission_samples_sample_upload_ctd', args=(mission_id,))
            attrs = {
                'component_id': "div_id_upload_ctd_load",
                'alert_type': 'info',
                'message': _("Loading"),
                'hx-post': url,
                'hx-trigger': 'load',
                'hx-target': "#form_id_ctd_bottle_upload",
                'hx-swap': 'innerHTML'
            }
            soup = forms.save_load_component(**attrs)
            response = HttpResponse(soup)
            return response

        mission = models.Mission.objects.get(pk=mission_id)
        bottle_dir = mission.bottle_directory
        if 'bottle_dir' in request.GET:
            bottle_dir = request.GET['bottle_dir']

        initial_args = {'mission': mission_id, 'bottle_dir': bottle_dir}
        if bottle_dir:
            files = [f for f in os.listdir(bottle_dir) if f.upper().endswith('.BTL')]
            if 'show_all' not in request.GET:
                initial_args['show_some'] = True
                loaded_files = [f.upper() for f in models.Sample.objects.filter(
                    type__is_sensor=True,
                    bottle__event__mission_id=mission_id).values_list('file', flat=True).distinct()]
                files = [f for f in files if f.upper() not in loaded_files]
                initial_args['show_some'] = True

            files.sort(key=lambda fn: os.path.getmtime(os.path.join(bottle_dir, fn)))

            initial_args['file_name'] = files

        context['file_form'] = forms.BottleSelection(initial=initial_args)
        html = render_block_to_string('core/partials/card_bottle_load_header.html', 'ctd_list', context=context)
        response = HttpResponse(html)
        response['HX-Trigger'] = 'update_samples, event_updated'

        mission.bottle_directory = bottle_dir
        mission.save()

        return response
    elif request.method == "POST":
        bottle_dir = request.POST['bottle_dir']
        files = request.POST.getlist('file_name')
        mission = models.Mission.objects.get(pk=mission_id)

        logger.info(views.sample_file_queue.empty())
        for file in files:
            views.sample_file_queue.put((mission, file,))

        start = True
        for thread in threading.enumerate():
            if thread.name == thread_name:
                start = False

        if start:
            Thread(target=views.load_ctd_files, name=thread_name, daemon=True, args=(mission,)).start()

        context['object'] = mission

        attrs = {
            'component_id': "div_id_upload_ctd_load",
            'alert_type': 'info',
            'message': _("Loading"),
            'hx-target': "#form_id_ctd_bottle_upload",
            'hx-ext': "ws",
            'ws-connect': "/ws/notifications/"
        }
        soup = forms.save_load_component(**attrs)
        # add a message area for websockets
        msg_div = soup.find(id="div_id_upload_ctd_load_message")
        msg_div.string = ""

        # The core.consumer.processing_elog_message() function is going to write output to a div
        # with the 'status' id, we'll stick that in the loading alerts message area and bam! Instant notifications!
        msg_div_status = soup.new_tag('div')
        msg_div_status['id'] = 'status'
        msg_div_status.string = _("Loading")
        msg_div.append(msg_div_status)

        response = HttpResponse(soup)
        return response


def soup_split_column(soup: BeautifulSoup, column: bs4.Tag) -> bs4.Tag:
    # if the th colspan is > 1 it's because there are replicates, the column should be split up
    # return the last column
    if 'colspan' in column.attrs and int(column.attrs['colspan']) > 1:
        label = column.string
        col_count = int(column.attrs['colspan'])
        column.attrs['colspan'] = 1
        column.string = f'{label}-1'
        for i in range(1, col_count):
            new_th = soup.new_tag('th')
            new_th.attrs = column.attrs
            new_th.string = f'{label}-{str(i + 1)}'
            column.insert_after(new_th)
            column = new_th

    return column


def list_samples(request, **kwargs):
    context = {}

    mission_id = kwargs['mission_id']
    sensor_id = kwargs['sensor_id'] if 'sensor_id' in kwargs else None

    page = int(request.GET['page'] if 'page' in request.GET else 0)
    page_limit = 50
    page_start = page_limit * page

    soup = BeautifulSoup('<table id="sample_table"></table>', 'html.parser')

    mission = models.Mission.objects.get(pk=mission_id)
    if sensor_id:
        # unfortunately if a page doesn't contain columns for 1 or 2 replicates when there's more the
        # HTML table that gets returned to the interface will be missing columns and it throws everything
        # out of alignment. We'll get the replicate columns here and use that value to insert blank
        # columns into the dataframe if a replicate column is missing from the query set.
        replicates = models.DiscreteSampleValue.objects.filter(
            sample__type__id=sensor_id).aggregate(Max('replicate'))['replicate__max']

        queryset = models.Sample.objects.filter(type_id=sensor_id)
        queryset = queryset.order_by('bottle__bottle_id')[page_start:(page_start + page_limit)]
        queryset = queryset.values(
            'bottle__bottle_id',
            'bottle__pressure',
            'discrete_values__replicate',
            'discrete_values__value',
            'discrete_values__flag',
            'discrete_values__sample_datatype',
            'discrete_values__comment',
        )
        headings = ['Value', 'Flag', 'Datatype', 'Comments']
        df = read_frame(queryset)
        df.columns = ["Sample", "Pressure", "Replicate", ] + headings
        df = df.pivot(index=['Sample', 'Pressure', ], columns=['Replicate'])

        for j, column in enumerate(headings):
            for i in range(1, replicates + 1):
                col_index = (column, i,)
                if col_index not in df.columns:
                    index = j * replicates + i - 1
                    if index < df.shape[1]:
                        df.insert(index, col_index, np.nan)
                    else:
                        df[col_index] = np.nan
        soup = format_sensor_table(request, df, mission_id, sensor_id)
    else:
        bottle_limit = models.Bottle.objects.filter(event__mission=mission).order_by('bottle_id')[
                       page_start:(page_start + page_limit)]
        queryset = models.Sample.objects.filter(bottle__in=bottle_limit)
        queryset = queryset.order_by('bottle__bottle_id')
        queryset = queryset.values(
            'bottle__bottle_id',
            'bottle__pressure',
            'type__id',
            'discrete_values__replicate',
            'discrete_values__value',
        )
        df = read_frame(queryset)
        df.columns = ["Sample", "Pressure", "Sensor", "Replicate", "Value"]

        try:
            sensors = mission.mission_sample_types.all()
            df = pd.pivot_table(df, values='Value', index=['Sample', 'Pressure'], columns=['Sensor', 'Replicate'])
            # we want a column for every sensor and then a column for every replicate for every sensor
            # for all sensors in the mission
            for sensor in sensors:
                # compute the maximum number of columns this sensor will require by figuring out th maximum number
                # of replicate the sensor/sample has
                replicate_count = sensor.samples.aggregate(replicates=Max('discrete_values__replicate'))
                if replicate_count['replicates']:
                    for i in range(0, replicate_count['replicates']):
                        replicate = i + 1
                        if not df.columns.isin([(sensor.pk, replicate)]).any():
                            # if the replicate column doesn't currently have any values, insert a nan as a placeholder
                            df[(sensor.pk, replicate)] = df.apply(lambda _: np.nan, axis=1)

            df = df.reindex(sorted(df.columns), axis=1)
            soup = format_all_sensor_table(df, mission_id)
        except Exception as ex:
            logger.exception(ex)

    if not queryset.exists():
        response = HttpResponse(soup)
        return response

    # add styles to the table so it's consistent with the rest of the application
    table = soup.find('table')
    table.attrs['class'] = 'dataframe table table-striped ' \
                           'table-sm tscroll horizontal-scrollbar'

    # now we'll attach an HTMX call to the last queried table row so when the user scrolls to it the next batch
    # of samples will be loaded into the table.
    args = (mission_id, sensor_id,) if sensor_id else (mission_id,)
    table_head = table.find('thead')

    table_body = table.find('tbody')

    last_tr = table_body.find_all('tr')[-1]
    last_tr.attrs['hx-target'] = 'this'
    last_tr.attrs['hx-trigger'] = 'intersect once'
    last_tr.attrs['hx-get'] = reverse_lazy('core:mission_samples_sample_list', args=args) + f"?page={page + 1}"
    last_tr.attrs['hx-swap'] = "afterend"

    # finally, align all text in each column to the center of the cell
    tds = soup.find('table').find_all('td')
    for td in tds:
        td['class'] = 'text-center text-nowrap'

    if page > 0:
        response = HttpResponse(soup.find('tbody').findAll('tr', recursive=False))
    else:
        response = HttpResponse(soup)

    return response


def format_all_sensor_table(df, mission_id):
    # start by replacing nan values with '---'
    df.fillna('---', inplace=True)

    # Pandas has the ability to render dataframes as HTML and it's super fast, but the default table looks awful.
    html = '<div id="sample_table">' + df.to_html() + "</div>"

    # Use BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup(html, 'html.parser')

    # this will be a big table add scrolling
    sample_table = soup.find(id="sample_table")
    sample_table.attrs['class'] = "vertical-scrollbar"

    # The next few rows will be the 'Sensor' row with labels like C0SM, T090C, and oxy
    # followed by the 'replicate' row that describes if this is a single, double, triple, etc. column sample.

    # We're going to flatten the headers down to one row then remove the other thead rows.
    # this is the row containing the sensor/sample short names
    sensor_headers = soup.find("thead").find("tr")

    # this is the replicate row, but we aren't doing anything with this row so get rid of it
    replicate_headers = sensor_headers.findNext("tr")
    replicate_headers.decompose()

    # we now have two header rows. The first contains all the sensor/sample names. The second contains the "Sample"
    # and "Pressure" labels with a bunch of empty columns afterward. I want to copy the first two columns
    # from the second header to the sensor_header row (because the labels might be translated)
    # then delete the second row
    index_headers = sensor_headers.findNext('tr')

    # copy the 'Sample' label
    index_column = index_headers.find('th')
    sensor_column = sensor_headers.find('th')
    sensor_column.string = index_column.string

    # copy the 'Pressure' label
    index_column = index_column.findNext('th')
    sensor_column = sensor_column.findNext('th')
    sensor_column.string = index_column.string

    # remove the now unneeded index_header row
    index_headers.decompose()

    # Now add a row to the table header that will contain checkbox inputs for the user to select
    # a sensor or sample to upload to biochem
    upload_row = soup.new_tag('tr')
    soup.find("thead").insert(0, upload_row)

    # the first column of the table will have the 'Sample' and 'Pressure' lables under it so it spans two columns
    upload_row_title = soup.new_tag('th')
    upload_row_title.attrs['colspan'] = 2
    upload_row_title.string = _("Biochem upload")
    upload_row.append(upload_row_title)

    # Now we're going to convert all of the sensor/sample column labels, which are actually the
    # core.models.SampleType ids, into buttons the user can press to open up a specific sensor to set
    # data types at a row level
    column = sensor_column.findNext('th')  # Sensor column
    while column:
        column['class'] = 'text-center text-nowrap'

        sampletype_id = column.string

        button = get_sensor_table_button(soup, mission_id, sampletype_id)

        # clear the column string and add the button instead
        column.string = ''
        column.append(button)

        # add the upload checkbox to the upload_row we created above, copy the attributes of the button column
        upload = soup.new_tag('th')
        upload.attrs = column.attrs

        check = get_sensor_table_upload_checkbox(soup, mission_id, sampletype_id)
        upload.append(check)
        upload_row.append(upload)

        # we're done with this column, get the next column and start again
        column = column.find_next_sibling('th')

    return soup


def format_sensor_table(request, df, mission_id, sensor_id):
    # Pandas has the ability to render dataframes as HTML and it's super fast, but the default table looks awful.

    # start by replacing nan values with '---'
    df.fillna('---', inplace=True)

    # reformat the Datatype columns, which will be represented as floats, but we want them as integers
    for i in range(1, df['Datatype'].shape[1] + 1):
        df[('Datatype', i,)] = df[('Datatype', i)].astype('string')
        df[('Datatype', i,)] = df[('Datatype', i,)].map(lambda x: int(float(x)) if x != '---' else x)

    # convert the dataframe to an HTML table
    html = '<div id="sample_table">' + df.to_html() + "</div>"

    # Using BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup(html, 'html.parser')

    # this will be a big table add scrolling
    sample_table = soup.find(id="sample_table")
    sample_table.attrs['class'] = "vertical-scrollbar"

    # add a message area that will hold saving, loading, error alerts
    msg_div = soup.new_tag("div")
    msg_div.attrs['id'] = "div_id_sample_table_msg"
    sample_table.insert(0, msg_div)

    # delete the row with the 'replicates' labels
    # soup.find("thead").find('tr').findNext('tr').decompose()

    # The next few rows will be the 'Sensor' row with labels like C0SM, T090C, and oxy
    # followed by the 'replicate' row that describes if this is a single, double, triple sample.

    # We're going to flatten the headers down to one row then remove the others.

    sensor_headers = soup.find("thead").find("tr")

    # we now have two header rows. The first contains all the sensor/sample names. The second contains the "Sample"
    # and "Pressure" labels. I want to copy the first two columns from the second header to the first two columns
    # of the first header (because the labels might be translated) then delete the second row
    replicate_header = soup.find('tr').findNext('tr')
    if replicate_header:
        replicate_header.decompose()

    sensor_column = sensor_headers.find('th')
    column = sensor_column.findNext('th')  # 'Value' column

    # if the sensor_id is present then we want to show the specific details for this sensor/sample
    sampletype = models.GlobalSampleType.objects.get(pk=sensor_id)
    column.string = f'{sampletype.short_name}'

    root = soup.findChildren()[0]

    # create a button so the user can go back to viewing all loaded sensors/samples

    upload_button = soup.new_tag('button')
    if 'biochem_session' in request.session:
        upload_button.attrs['class'] = 'btn btn-primary btn-sm'
    else:
        upload_button.attrs['class'] = 'btn btn-disabled btn-sm'

    # The response to this should do a hx-swap-oob="#div_id_sample_table_msg"
    # upload_button.attrs['hx-get'] = reverse_lazy('core:mission_samples_upload_bio_chem', args=(mission_id, sensor_id,))
    # upload_button.attrs['hx-swap'] = 'none'
    #
    # upload_button_icon = BeautifulSoup(load_svg('database-add'), 'html.parser').svg
    # upload_button.append(upload_button_icon)

    table = soup.find('table')
    table.attrs['id'] = 'table_id_sample_table'
    th = table.find('tr').find('th')
    th.attrs['class'] = 'text-center'
    th.append(upload_button)

    # center all of the header text
    while (th := th.findNext('th')):
        th.attrs['class'] = 'text-center'
        if th.string == 'Comments':
            th.attrs['class'] += ' w-100'

    root.append(table)

    return soup


def sample_delete(request, **kwargs):
    mission = kwargs['mission_id']
    sample_type = kwargs['sample_type_id']
    if request.method == "POST":
        models.Sample.objects.filter(type=sample_type).delete()

        # return a loading dialog that will send the user back to the Mission Sample page
        attrs = {
            'component_id': "div_id_delete_samples",
            'alert_type': 'info',
            'message': _("Loading"),
            'hx-get': reverse_lazy('core:mission_samples_sample_details', args=(mission,)),
            'hx-trigger': 'load',
            'hx-push-url': 'true'
        }
        soup = forms.save_load_component(**attrs)
        return HttpResponse(soup)

    return list_samples(request, mission_id=mission)


def update_sample_type_row(request, **kwargs):
    if request.method == "POST":

        mission_id = request.POST['mission_id']
        sample_type_id = request.POST['sample_type_id']
        data_type_code = request.POST['data_type_code']
        start_sample = request.POST['start_sample']
        end_sample = request.POST['end_sample']

        data_type = None
        if data_type_code:
            data_type = bio_models.BCDataType.objects.get(data_type_seq=data_type_code)

        discrete_update = models.DiscreteSampleValue.objects.filter(sample__bottle__event__mission_id=mission_id,
                                                                    sample__bottle__bottle_id__gte=start_sample,
                                                                    sample__bottle__bottle_id__lte=end_sample,
                                                                    sample__type__id=sample_type_id, )
        for value in discrete_update:
            value.sample_datatype = data_type
        models.DiscreteSampleValue.objects.bulk_update(discrete_update, ['sample_datatype'])

        response = list_samples(request, mission_id=mission_id, sensor_id=sample_type_id)
        return response

    return Http404("Invalid action")


def update_sample_type_mission(request, **kwargs):
    if request.method == "POST":

        mission_id = request.POST['mission_id']
        sample_type_id = request.POST['sample_type_id']
        data_type_code = request.POST['data_type_code']

        data_type = bio_models.BCDataType.objects.get(data_type_seq=data_type_code)

        sample_type = models.MissionSampleType.objects.get(pk=sample_type_id)
        sample_type.datatype = data_type
        sample_type.save()

        response = list_samples(request, mission_id=mission_id, sensor_id=sample_type_id)
        return response

    return Http404("Invalid action")


def update_sample_type(request, **kwargs):
    if request.method == "GET":
        attrs = {
            'component_id': 'div_id_data_type_update_save',
            'message': _("Saving"),
            'hx-trigger': 'load',
            'hx-target': '#div_id_data_type_message',
            'hx-select': '#div_id_data_type_message',
            'hx-select-oob': '#table_id_sample_table'
        }
        if 'apply_data_type_row' in request.GET:
            attrs['hx-post'] = reverse_lazy('core:mission_samples_update_sample_type_row')
            soup = forms.save_load_component(**attrs)
            return HttpResponse(soup)
        elif 'apply_data_type_sensor' in request.GET:
            attrs['hx-post'] = reverse_lazy('core:mission_samples_update_sample_type_mission')
            soup = forms.save_load_component(**attrs)
            return HttpResponse(soup)

        if 'data_type_filter' in request.GET:
            biochem_form = forms.BioChemDataType(initial={'data_type_filter': request.GET['data_type_filter']})
            html = render_crispy_form(biochem_form)
            return HttpResponse(html)

        data_type_code = request.GET['data_type_code'] if 'data_type_code' in request.GET else \
            request.GET['data_type_description']

        biochem_form = forms.BioChemDataType(initial={'data_type_code': data_type_code})
        html = render_crispy_form(biochem_form)
        return HttpResponse(html)


def choose_bottle_dir(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = models.Mission.objects.get(pk=mission_id)

    result = easygui.diropenbox(title="Choose BTL directory")
    logger.info(result)
    if result:
        mission.bottle_directory = result
        mission.save()

    soup = BeautifulSoup("", 'html.parser')
    input = soup.new_tag('input')
    input.attrs['id'] = "input_id_bottle_dir"
    input.attrs['class'] = "input-group-sm form-control form-control-sm"
    input.attrs['type'] = "text"
    input.attrs['name'] = "bottle_dir"
    input.attrs['value'] = mission.bottle_directory
    input.attrs['placeholder'] = _("Location of the.BTL /.ROS fiels to be loaded.")
    input.attrs['hx-swap-oob'] = 'true'
    soup.append(input)

    return HttpResponse(soup)


def add_sensor_to_upload(request, **kwargs):
    mission_id = kwargs['mission_id']
    sensor_id = kwargs['sensor_id']
    soup = BeautifulSoup('', 'html.parser')
    if request.method == 'POST':
        button = get_sensor_table_button(soup, mission_id, sensor_id)
        button.attrs['hx-swap-oob'] = 'true'

        upload_sensors: QuerySet[models.BioChemUpload] = models.BioChemUpload.objects.filter(mission_id=mission_id)

        if 'add_sensor' in request.POST:
            if not upload_sensors.filter(type_id=sensor_id).exists():
                add_sensor = models.BioChemUpload(mission_id=mission_id, type_id=sensor_id)
                add_sensor.save()
        else:
            upload_sensors.filter(type_id=sensor_id).delete()

        check = get_sensor_table_upload_checkbox(soup, mission_id, sensor_id)
        soup.append(check)
        soup.append(button)

        return HttpResponse(soup)

    logger.error("user has entered an unmanageable state")
    logger.error(kwargs)
    logger.error(request.method)
    logger.error(request.GET)
    logger.error(request.POST)

    return Http404("You shouldn't be here")


def get_all_discrete_upload_db_card(request, **kwargs):
    mission_id = kwargs['mission_id']
    upload_url = reverse_lazy("core:mission_samples_upload_bio_chem", args=(mission_id,))
    download_url = reverse_lazy("core:mission_samples_download_bio_chem", args=(mission_id,))

    form_soup = form_biochem_database.get_database_connection_form(request, mission_id, upload_url,
                                                                   download_url=download_url)

    return HttpResponse(form_soup)


def sample_data_upload(mission: models.Mission, uploader: str):
    sample_type_ids = models.BioChemUpload.objects.filter(mission=mission).values_list("type", flat=True).distinct()

    # clear previous errors if there were any from the last upload attempt
    models.Error.objects.filter(mission=mission, type=models.ErrorType.biochem).delete()

    # validate that the checked off sensors/samples have a biochem datatypes
    sample_types = models.GlobalSampleType.objects.filter(id__in=sample_type_ids)

    # send_user_notification_queue('biochem', _("Validating Sensor/Sample Datatypes"))
    user_logger.info(_("Validating Sensor/Sample Datatypes"))
    errors = validation.validate_samples_for_biochem(mission=mission, sample_types=sample_types)

    if errors:
        # send_user_notification_queue('biochem', _("Datatypes missing see errors"))
        user_logger.info(_("Datatypes missing see errors"))
        models.Error.objects.bulk_create(errors)

    # create and upload the BCS data if it doesn't already exist
    form_biochem_database.upload_bcs_d_data(mission, uploader)
    form_biochem_database.upload_bcd_d_data(mission, uploader)


def upload_samples(request, **kwargs):
    return form_biochem_database.upload_bio_chem(request, sample_data_upload, **kwargs)


def download_samples(request, **kwargs):
    mission_id = kwargs['mission_id']

    soup = BeautifulSoup('', 'html.parser')
    div = soup.new_tag('div')
    div.attrs = {
        'id': "div_id_biochem_alert_biochem_db_details",
        'hx-swap-oob': 'true'
    }
    soup.append(div)

    def get_progress_alert():
        url = reverse_lazy("core:mission_samples_download_bio_chem", args=(mission_id, ))
        message_component_id = 'div_id_upload_biochem'
        attrs = {
            'component_id': message_component_id,
            'alert_type': 'info',
            'message': _("Saving to file"),
            'hx-post': url,
            'hx-swap': 'none',
            'hx-trigger': 'load',
            'hx-target': "#div_id_biochem_alert_biochem_db_details",
            'hx-ext': "ws",
            'ws-connect': f"/ws/biochem/notifications/{message_component_id}/"
        }

        alert_soup = forms.save_load_component(**attrs)

        # add a message area for websockets
        msg_div = alert_soup.find(id="div_id_upload_biochem_message")
        msg_div.string = ""

        msg_div_status = soup.new_tag('div')
        msg_div_status['id'] = 'status'
        msg_div_status.string = _("Loading")
        msg_div.append(msg_div_status)

        return alert_soup

    if request.method == "GET":

        alert_soup = get_progress_alert()

        div.append(alert_soup)

        return HttpResponse(soup)

    has_uploader = 'uploader' in request.POST and request.POST['uploader']
    if 'uploader2' not in request.POST and not has_uploader:
        url = reverse_lazy("core:mission_samples_download_bio_chem", args=(mission_id, ))
        message_component_id = 'div_id_upload_biochem'
        attrs = {
            'component_id': message_component_id,
            'alert_type': 'warning',
            'message': _("Require Uploader")
        }
        alert_soup = forms.blank_alert(**attrs)

        input_div = soup.new_tag('div')
        input_div['class'] = 'form-control input-group'

        input = soup.new_tag('input')
        input.attrs['id'] = 'input_id_uploader'
        input.attrs['type'] = "text"
        input.attrs['name'] = "uploader2"
        input.attrs['class'] = 'textinput form-control'
        input.attrs['maxlength'] = '20'
        input.attrs['placeholder'] = _("Uploader")

        icon = BeautifulSoup(load_svg('check-square'), 'html.parser').svg

        submit = soup.new_tag('button')
        submit.attrs['class'] = 'btn btn-primary'
        submit.attrs['hx-post'] = url
        submit.attrs['id'] = 'input_id_uploader_btn_submit'
        submit.attrs['name'] = 'submit'
        submit.append(icon)

        icon = BeautifulSoup(load_svg('x-square'), 'html.parser').svg
        cancel = soup.new_tag('button')
        cancel.attrs['class'] = 'btn btn-danger'
        cancel.attrs['hx-post'] = url
        cancel.attrs['id'] = 'input_id_uploader_btn_cancel'
        cancel.attrs['name'] = 'cancel'
        cancel.append(icon)

        input_div.append(input)
        input_div.append(submit)
        input_div.append(cancel)

        msg = alert_soup.find(id='div_id_upload_biochem_message')
        msg.string = msg.string + " "
        msg.append(input_div)

        div.append(alert_soup)

        return HttpResponse(soup)
    elif request.htmx.trigger == 'input_id_uploader_btn_submit':
        alert_soup = get_progress_alert()
        # div_id_upload_biochem_message is the ID given to the component in the get_progress_alert() function
        message = alert_soup.find(id="div_id_upload_biochem")
        hidden = soup.new_tag("input")
        hidden.attrs['type'] = 'hidden'
        hidden.attrs['name'] = 'uploader2'
        hidden.attrs['value'] = request.POST['uploader2']
        message.append(hidden)

        div.append(alert_soup)
        return HttpResponse(soup)
    elif request.htmx.trigger == 'input_id_uploader_btn_cancel':
        return HttpResponse(soup)

    uploader = request.POST['uploader2'] if 'uploader2' in request.POST else \
        request.POST['uploader'] if 'uploader' in request.POST else "N/A"

    mission = models.Mission.objects.get(pk=mission_id)
    events = models.Event.objects.filter(mission=mission, instrument__type=models.InstrumentType.ctd)
    bottles = models.Bottle.objects.filter(event__in=events)

    # because we're not passing in a link to a database for the bcs_d_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create, update, fields = biochem.upload.get_bcs_d_rows(uploader=uploader, bottles=bottles)

    headers = [field.name for field in biochem_models.BcsDReportModel._meta.fields]

    file_name = f'{mission.name}_BCS_D.csv'
    path = os.path.join(settings.BASE_DIR, "reports")
    Path(path).mkdir(parents=True, exist_ok=True)

    try:
        with open(os.path.join(path, file_name), 'w', newline='', encoding="UTF8") as f:

            writer = csv.writer(f)
            writer.writerow(headers)

            for bcs_row in create:
                row = []
                for header in headers:
                    val = getattr(bcs_row, header) if hasattr(bcs_row, header) else ''
                    row.append(val)

                writer.writerow(row)
    except PermissionError:
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': _("Could not save report, the file may be opened and/or locked"),
        }
        alert_soup = forms.blank_alert(**attrs)
        div.append(alert_soup)

        return HttpResponse(soup)

    datatypes = models.BioChemUpload.objects.filter(mission=mission).values_list('type', flat=True).distinct()

    discreate_samples = models.DiscreteSampleValue.objects.filter(sample__bottle__event__mission=mission)
    discreate_samples = discreate_samples.filter(sample__type_id__in=datatypes)

    # because we're not passing in a link to a database for the bcd_d_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create, update, fields = biochem.upload.get_bcd_d_rows(uploader=uploader, samples=discreate_samples)

    headers = [field.name for field in biochem_models.BcdDReportModel._meta.fields]

    file_name = f'{mission.name}_BCD_D.csv'
    path = os.path.join(settings.BASE_DIR, "reports")
    Path(path).mkdir(parents=True, exist_ok=True)

    try:
        with open(os.path.join(path, file_name), 'w', newline='', encoding="UTF8") as f:

            writer = csv.writer(f)
            writer.writerow(headers)

            for row_number, bcs_row in enumerate(create):
                row = []
                for header in headers:
                    if header == 'dis_data_num':
                        val = str(row_number+1)
                    else:
                        val = getattr(bcs_row, header) if hasattr(bcs_row, header) else ''
                    row.append(val)

                writer.writerow(row)
    except PermissionError:
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': _("Could not save report, the file may be opened and/or locked"),
        }
        alert_soup = forms.blank_alert(**attrs)
        div.append(alert_soup)

        return HttpResponse(soup)

    attrs = {
        'component_id': 'div_id_upload_biochem',
        'alert_type': 'success',
        'message': _("Success - Reports saved at : ") + f'{path}',
    }
    alert_soup = forms.blank_alert(**attrs)

    div.append(alert_soup)

    return HttpResponse(soup)


# ###### Mission Sample ###### #
mission_sample_urls = [
    # for testing the sample config form
    path('mission/sample/test/<int:pk>/', SampleDetails.as_view()),

    # used to reload elements on the sample form if a GET htmx request
    path('sample_config/hx/', load_sample_config, name="mission_samples_load_sample_config"),
    path('sample_config/hx/<int:config>/', load_sample_config, name="mission_samples_load_sample_config"),
    path('sample_config/hx/file_errors/', get_file_error_card, name="mission_samples_get_file_errors"),

    # show the create a sample config form
    path('sample_config/hx/new/', new_sample_config, name="mission_samples_new_sample_config"),
    path('sample_config/hx/new/<int:config_id>/', new_sample_config, name="mission_samples_new_sample_config"),

    # save the sample config
    path('sample_config/hx/save/', save_sample_config, name="mission_samples_save_sample_config"),
    path('sample_config/hx/update/<int:config_id>/', save_sample_config, name="mission_samples_save_sample_config"),

    # delete a sample file configuration or load samples using that file configuration
    path('sample_config/hx/load/<int:config_id>/', load_samples, name="mission_samples_load_samples"),
    path('sample_config/hx/delete/<int:config_id>/', delete_sample_config, name="mission_samples_delete_sample_config"),

    # ###### sample details ###### #

    path('mission/sample/bottledir/<int:mission_id>/', choose_bottle_dir, name="mission_samples_choose_bottle_dir"),
    path('mission/sample/<int:pk>/', SampleDetails.as_view(), name="mission_samples_sample_details"),
    path('mission/sample/<int:pk>/<int:sample_type_id>/', SampleDetails.as_view(),
         name="mission_samples_sample_details"),
    path('mission/sample/hx/ctd/<int:mission_id>/', sample_upload_ctd, name="mission_samples_sample_upload_ctd"),
    path('mission/sample/hx/delete/<int:mission_id>/<int:sample_type_id>/', sample_delete,
         name="mission_samples_sample_sample_delete"),
    path('mission/sample/hx/list/<int:mission_id>', list_samples, name="mission_samples_sample_list"),
    path('mission/sample/hx/list/<int:mission_id>/<int:sensor_id>', list_samples,
         name="mission_samples_sample_list"),

    path('mission/sample/hx/datatype/', update_sample_type, name="mission_samples_update_sample_type"),
    path('mission/sample/hx/datatype/row/', update_sample_type_row, name="mission_samples_update_sample_type_row"),
    path('mission/sample/hx/datatype/mission/', update_sample_type_mission,
         name="mission_samples_update_sample_type_mission"),
    path('mission/sample/hx/upload/sensor/<int:mission_id>/<int:sensor_id>/', add_sensor_to_upload,
         name="mission_samples_add_sensor_to_upload"),
    path('mission/sample/hx/upload/sensor/<int:mission_id>/', get_all_discrete_upload_db_card,
         name="mission_samples_get_all_discrete_upload_db_card"),
    path('mission/sample/hx/upload/biochem/<int:mission_id>/', upload_samples, name="mission_samples_upload_bio_chem"),
    path('mission/sample/hx/download/biochem/<int:mission_id>/', download_samples,
         name="mission_samples_download_bio_chem"),
]
