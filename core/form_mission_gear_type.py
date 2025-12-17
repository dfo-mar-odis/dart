import os
import threading
import time

import numpy as np

import pandas as pd

from PyQt6.QtWidgets import QFileDialog

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Column, Field, Div, Row
from crispy_forms.utils import render_crispy_form

from django.conf import settings
from django.db.models import QuerySet

from django import forms
from django.http import HttpResponse
from django.utils.translation import gettext as _
from django.urls import path, reverse_lazy
from django_pandas.io import read_frame

from config.utils import load_svg

from core import form_mission_sample_filter
from core.form_mission_sample_filter import SampleFilterForm
from core import models as core_models
from core import forms as core_forms
from core import utils

from bio_tables import models as biochem_models

import logging

user_logger = logging.getLogger('dart.user.gear_type')
logger = logging.getLogger('dart')

class GearTypeFilterForm(SampleFilterForm):

    filter_gear_type_description = forms.ChoiceField(
        help_text=_("Filter Samples based on existing gear type assigned"),
        required=False,
    )

    class GearTypeFilterIdBuilder(SampleFilterForm.SampleFilterIdBuilder):

        def get_select_gear_type_description_id(self):
            return f'select_id_gear_type_description_{self.card_name}'

    @staticmethod
    def get_id_builder_class():
        return GearTypeFilterForm.GearTypeFilterIdBuilder

    def get_select_gear_type_description(self):
        attrs = self.htmx_attributes.copy()

        return Field('filter_gear_type_description', css_class='form-select form-select-sm',
                     id=self.get_id_builder().get_select_gear_type_description_id(), **attrs)

    def get_card_body(self) -> Div:
        body = super().get_card_body()

        row = Row(
            Column(
                self.get_select_gear_type_description()
            )
        )

        body.append(row)
        return body

    def get_samples_card_update_url(self):
        return reverse_lazy('core:mission_gear_type_sample_list', args=[self.mission_id, self.instrument_type])

    def get_clear_filters_url(self):
        return reverse_lazy("core:form_mission_sample_type_clear", args=[self.mission_id, self.instrument_type])

    def __init__(self, *args, mission_id, instrument_type, collapsed=True, **kwargs):
        self.card_name = "gear_type_filter"
        self.mission_id = mission_id
        self.instrument_type = instrument_type
        self.events = core_models.Event.objects.filter(mission_id=mission_id, instrument__type=instrument_type)

        super().__init__(*args, card_name=self.card_name, collapsed=collapsed, **kwargs)

        gear_list = biochem_models.BCGear.objects.all().order_by('type', 'gear_seq')
        self.fields['filter_gear_type_description'].choices = ([(0, '------')] +
                                                               [(g.pk, f'{g.gear_seq} : {g.type} : {g.description}')
                                                               for g in gear_list])


class GearTypeSelectionForm(core_forms.CollapsableCardForm):

    class GearTypeSelectionIdBuilder(core_forms.CollapsableCardForm.CollapsableCardIDBuilder):
        def get_button_apply_id(self):
            return f'btn_id_apply_gear_type_{self.card_name}'

        def get_button_volume_id(self):
            return f'btn_id_apply_gear_type_{self.card_name}'

        def get_input_gear_code_id(self):
            return f'input_id_gear_code_{self.card_name}'

        def get_select_gear_description_id(self):
            return f'input_id_gear_description_{self.card_name}'

    @staticmethod
    def get_id_builder_class():
        return GearTypeSelectionForm.GearTypeSelectionIdBuilder

    gear_type_code = forms.IntegerField(label=_("Gear Type Code"), required=False)
    gear_type_description = forms.ChoiceField(label=_("Gear Type Description"), required=False)

    def get_btn_apply_gear_type(self):
        attrs = {
            'id': self.get_id_builder().get_button_apply_id(),
            'hx-post': reverse_lazy('core:form_mission_gear_type_update_gear_type', args=[self.mission_id, self.instrument_type]),
            'hx-swap': 'none',
        }
        icon = load_svg("check-square")

        return StrictButton(icon, css_class='btn btn-sm btn-primary', **attrs)

    def get_btn_load_volume(self):
        attrs = {
            'id': self.get_id_builder().get_button_volume_id(),
            'hx-get': reverse_lazy('core:form_gear_type_load_volume', args=[self.mission_id]),
            'hx-swap': 'none',
        }
        icon = load_svg("check-square")

        return StrictButton(icon, css_class='btn btn-sm btn-primary', **attrs)

    def get_input_gear_code(self):
        attrs = {
            'id': self.get_id_builder().get_input_gear_code_id(),
            'hx-trigger': 'keyup changed delay:500ms',
            'hx-swap': 'none',
            'hx-get': self.update_form_url,
            'hx-select-oob': f"#{self.get_id_builder().get_select_gear_description_id()}",
        }
        return Field('gear_type_code', css_class="form-control-sm", **attrs)

    def get_select_gear_description(self):
        attrs = {
            'id': self.get_id_builder().get_select_gear_description_id(),
            'hx-swap': 'none',
            'hx-get': self.update_form_url,
            'hx-select-oob': f"#{self.get_id_builder().get_input_gear_code_id()}",
        }
        return Field('gear_type_description', css_class="form-select form-select-sm", **attrs)

    def get_card_header(self):
        header = super().get_card_header()
        spacer_row = Column(
            css_class="col"
        )

        button_row = Column(
            self.get_btn_apply_gear_type(),
            css_class="col-auto"
        )

        header.fields[0].fields.append(spacer_row)
        header.fields[0].fields.append(button_row)
        return header

    def get_card_body(self) -> Div:
        body = super().get_card_body()

        gear_details_row = Row(
            Column(
                self.get_input_gear_code(),
                css_class='col-auto'
            ),
            Column(
                self.get_select_gear_description(),
            )
        )

        body.append(gear_details_row)
        return body

    def __init__(self, mission_id, instrument_type, render_description_list=True, *args, **kwargs):
        self.mission_id = mission_id
        self.instrument_type = instrument_type
        self.update_form_url = reverse_lazy('core:form_mission_gear_type_filter_datatype', args=[self.mission_id, self.instrument_type])

        super().__init__(*args, card_name="gear_type_selection", card_title=_("Gear Type Selection"), **kwargs)

        self.fields['gear_type_description'].choices = [(0, '------')]
        if render_description_list:
            gear_qs = biochem_models.BCGear.objects.all().order_by('type', 'gear_seq')
            self.fields['gear_type_description'].choices += [(b.gear_seq, f"{b.gear_seq} : {b.type} : {b.description}") for b in gear_qs]
            if 'gear_type_code' in self.initial:
                self.fields['gear_type_description'].initial = self.initial['gear_type_code']


def get_samples_queryset(filter_dict: dict, mission_id, instrument_type) -> QuerySet:
    queryset = core_models.Bottle.objects.filter(
        event__mission_id=mission_id,
        event__instrument__type=instrument_type
    ).order_by("bottle_id")

    event_id = int(filter_dict.get('event', 0) or 0)
    if event_id > 0:
        event = core_models.Event.objects.get(pk=event_id)
        sample_id_start = event.sample_id
        sample_id_end = event.end_sample_id
    else:
        sample_id_start = int(filter_dict.get('sample_id_start', 0) or 0)
        sample_id_end = int(filter_dict.get('sample_id_end', 0) or 0)

    if bool(sample_id_start) and not bool(sample_id_end):
        queryset = queryset.filter(bottle_id=sample_id_start)
    elif bool(sample_id_start) and bool(sample_id_end):
        queryset = queryset.filter(bottle_id__gte=sample_id_start, bottle_id__lte=sample_id_end)

    gear_code = int(filter_dict.get('filter_gear_type_code', 0) or filter_dict.get('filter_gear_type_description', 0) or 0)

    if gear_code:
        queryset = queryset.filter(gear_type_id=gear_code)

    return queryset

def process_samples_func(queryset, **kwargs) -> BeautifulSoup:

    instrument_type = kwargs['instrument_type']

    headers = [
        ('bottle_id', _("Sample")),
        ('event__event_id', _("Event")),
        ('mesh_size', _("Mesh")),
        ('gear_type__gear_seq', _("Gear Type ID")),
        ('gear_type__description', _("Gear Type Description"))
    ]
    if instrument_type == core_models.InstrumentType.net:
        headers.insert(3, ('volume', _("Volume")))

    value_headers = [h[0] for h in headers]
    table_headers = [h[1] for h in headers]

    bottle_list = queryset.values(*value_headers)

    df = read_frame(bottle_list)

    if instrument_type == core_models.InstrumentType.net:
        bottle_dict = {b.bottle_id: b for b in queryset}
        for i, row in df.iterrows():
            if row['volume'] is None:
                volume = bottle_dict[row['bottle_id']].computed_volume[1]

                df.at[i, 'volume'] = volume if volume else "-----"

    df.columns = table_headers

    html = df.to_html(index=False)
    return BeautifulSoup(html, 'html.parser')

def list_samples(request, mission_id, instrument_type, **kwargs):
    card_title = _('Samples')
    delete_samples_url = reverse_lazy("core:form_gear_type_delete_samples", args=[mission_id, instrument_type])
    queryset = get_samples_queryset(request.POST, mission_id, instrument_type)

    soup = form_mission_sample_filter.list_samples(request, queryset, card_title, delete_samples_url,
                                                   process_samples_func, instrument_type=instrument_type)

    if instrument_type == core_models.InstrumentType.net:
        button_row = soup.find(id=f"div_id_card_title_buttons_{form_mission_sample_filter.SAMPLES_CARD_NAME}")

        attrs = {
            'id': f'btn_id_load_volumes_{form_mission_sample_filter.SAMPLES_CARD_NAME}',
            'name': 'load_volumes',
            'title': _('Load Volume File'),
            'class': 'btn btn-sm btn-primary me-2',
            'hx-swap': 'none',
            'hx-get': reverse_lazy('core:form_gear_type_load_volume', args=[mission_id])
        }
        icon = BeautifulSoup(load_svg('plus-square'), 'html.parser').svg
        button_load_volumes = soup.new_tag('button', attrs=attrs)
        button_load_volumes.append(icon)

        button_row.insert(0, button_load_volumes)

    return HttpResponse(soup)


def delete_samples(request, mission_id, instrument_type):
    bottles = get_samples_queryset(request.POST, mission_id, instrument_type)
    bottles.delete()

    response = HttpResponse()
    response['HX-Trigger'] = 'reload_samples'
    return response


def validate_event_and_bottle(df):
    errors = []
    update_bottles = []
    max = df.shape[0]
    for idx, row in df.iterrows():
        user_logger.info(_("Processing row") + " %d/%d", idx + 1, max)
        event_id = row['event']
        sample_id = row['sample_id']
        volume = float(row['volume']) if utils.is_number(row['volume']) else np.nan
        try:
            event = core_models.Event.objects.get(event_id=event_id)
            try:
                bottle = core_models.Bottle.objects.get(event=event, bottle_id=sample_id)
            except core_models.Bottle.DoesNotExist:
                errors.append((idx + 1, f"No Bottle with bottle_id={sample_id} for Event {event_id}"))
                continue

            bottle.volume = volume
            update_bottles.append(bottle)
        except core_models.Event.DoesNotExist:
            errors.append((idx + 1, f"No Bottle with bottle_id={sample_id} for Event {event_id}"))

    if len(errors) == 0 and len(update_bottles) > 0:
        core_models.Bottle.objects.bulk_update(update_bottles, ['volume'])
        return None

    return errors


def process_file(mission, file_path):
    file_name = os.path.basename(file_path)
    core_models.FileError.objects.filter(mission=mission, file_name=file_name).delete()

    expected_columns = ["mission", "tow", "event", "sample_id", "net_number", "volume"]
    df = pd.read_excel(file_path)
    if list(df.columns) != expected_columns:
        raise ValueError(f"Header does not match expected columns: {expected_columns}")

    errors = validate_event_and_bottle(df)
    if errors:
        for error in errors:
            core_models.FileError.objects.create(mission=mission, message=error[1], line=error[0],
                                            file_name=file_name, type=core_models.ErrorType.validation, code=1000)


def load_volume(request, mission_id, thread_id=None, **kwargs):
    soup = BeautifulSoup('', 'html.parser')
    mission = core_models.Mission.objects.get(pk=mission_id)
    base_notifications_id = f'div_id_card_notifications_{form_mission_sample_filter.SAMPLES_CARD_NAME}'

    if thread_id:
        user_logger.info("checking logger")
        thread = None
        for t in threading.enumerate():
            if t.ident == int(thread_id):
                thread = t
                break

        if thread:
            while thread.is_alive():
                time.sleep(2)

        attrs = {
            'component_id': base_notifications_id,
            'message': _("Success"),
            'alert_type': 'success'
        }

        errors = core_models.FileError.objects.filter(mission=mission, type=core_models.ErrorType.validation, code=1000)
        if errors.exists():
            attrs['alert_type'] = 'danger'
            attrs['message'] = _("Errors found in the file:")
            alert_soup = core_forms.blank_alert(**attrs)
            message_div = alert_soup.find('div', id=f'{base_notifications_id}_message')
            message_div.append(ul_elm := soup.new_tag('ul'))
            for error in errors:
                ul_elm.append(li_elm := soup.new_tag('li'))
                error_msg = f"Line {error.line} - {error.message}"
                li_elm.string = error_msg
                logger.error(error_msg)

            soup.append(alert_soup)
            return HttpResponse(soup)

        soup.append(core_forms.blank_alert(**attrs))
        response = HttpResponse(soup)
        response['HX-Trigger'] = 'reload_samples'
        return response

    app = settings.app if hasattr(settings, 'app') else None
    if not app:
        return HttpResponse(soup)

    start_dir = settings.dir if hasattr(settings, 'dir') else None

    # Create and configure the file dialog
    file_dialog = QFileDialog()
    file_dialog.setWindowTitle("Select a BIONESS_volume File")
    file_dialog.setNameFilter("xlsx (*.xlsx)")
    file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    file_dialog.setDirectory(start_dir)

    # Open the dialog and get the selected file
    if not file_dialog.exec():
        return HttpResponse(soup)

    file_path = file_dialog.selectedFiles()[0]
    settings.dir = os.path.dirname(file_path)
    logger.info(f"Selected file: {file_path}")

    if file_path:
        (t := threading.Thread(target=process_file, args=(mission, file_path,), daemon=True)).start()

        attrs = {
            'alert_area_id': base_notifications_id,
            'logger': user_logger.name,
            'message': _("Loading"),
            'hx-get': reverse_lazy('core:form_gear_type_load_volume', args=(mission_id, t.ident,)),
            'hx-trigger': 'load',
        }

        return HttpResponse(core_forms.websocket_post_request_alert(**attrs))

    return HttpResponse(soup)


def update_gear_type_samples(request, mission_id, instrument_type=None, **kwargs):
    bottles = get_samples_queryset(request.POST, mission_id, instrument_type)
    gear_type = request.POST.get('gear_type_code', None)

    for bottle in bottles:
        bottle.gear_type = biochem_models.BCGear.objects.get(gear_seq=int(gear_type)) if utils.is_number(
            gear_type) else gear_type

    core_models.Bottle.objects.bulk_update(bottles, ['gear_type'])

    response = HttpResponse()
    response['HX-Trigger'] = 'reload_samples'
    return response

def clear_filters(request, mission_id, instrument_type):

    form = GearTypeFilterForm(mission_id=mission_id, instrument_type=instrument_type, collapsed=False)
    return form_mission_sample_filter.clear_filters(form)


def filter_gear_type(request, mission_id, instrument_type):
    render_description_list = True

    gear_code = 0
    initial = {}
    if (gear_code := int(request.GET.get('gear_type_code', 0) or 0)):
        initial = {'gear_type_code': gear_code}
    elif (gear_code := int(request.GET.get('gear_type_description', 0) or 0)):
        initial = {'gear_type_code': gear_code}
        render_description_list = False

    form = GearTypeSelectionForm(mission_id=mission_id, instrument_type=instrument_type, collapsed=False,
                                 render_description_list=render_description_list, initial=initial)
    html = render_crispy_form(form)
    return HttpResponse(html)


url_patterns = [
    path(f'geartype/load_volume/<int:mission_id>/', load_volume, name="form_gear_type_load_volume"),
    path(f'geartype/load_volume/<int:mission_id>/<str:thread_id>/', load_volume, name="form_gear_type_load_volume"),

    path(f'geartype/delete/<int:mission_id>/<str:instrument_type>/', delete_samples, name="form_gear_type_delete_samples"),

    path(f'geartype/<int:mission_id>/<str:instrument_type>/', filter_gear_type, name="form_mission_gear_type_filter_datatype"),
    path(f'geartype/apply/<int:mission_id>/<str:instrument_type>/', update_gear_type_samples, name="form_mission_gear_type_update_gear_type"),
    path(f'geartype/clear/<int:mission_id>/<int:instrument_type>/', clear_filters, name="form_mission_sample_type_clear"),

    path(f'geartype/<int:mission_id>/<int:instrument_type>/list_samples/', list_samples,
         name="mission_gear_type_sample_list"),
]
