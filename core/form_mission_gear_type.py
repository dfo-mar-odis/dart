import os
import threading
import time
import numpy as np

from tkinter import filedialog

import pandas as pd
from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.db.models import QuerySet

from django.http import HttpResponse
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.urls import path, reverse_lazy
from django_pandas.io import read_frame

from config.utils import load_svg
from core import models as core_models
from core import forms, utils

from core import form_mission_sample_filter
from core.form_mission_sample_filter import SampleFilterForm, get_samples_card, SAMPLES_CARD_NAME, SAMPLES_CARD_ID
from bio_tables import models as biochem_models

import logging

user_logger = logging.getLogger('dart.user.gear_type')
logger = logging.getLogger('dart')

class GearTypeFilterForm(SampleFilterForm):

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
    df.columns = table_headers

    if instrument_type == core_models.InstrumentType.net:
        bottle_dict = {b.bottle_id: b for b in queryset}
        for i, row in df.iterrows():
            if row['volume'] is None:
                volume = bottle_dict[row['bottle_id']].computed_volume[1]

                df.at[i, 'volume'] = volume if volume else "-----"

    html = df.to_html(index=False)
    return BeautifulSoup(html, 'html.parser')

def list_samples(request, mission_id, instrument_type, **kwargs):
    card_title = _('Samples')
    delete_samples_url = reverse_lazy("core:form_gear_type_delete_samples", args=[mission_id, instrument_type])
    queryset = get_samples_queryset(request.GET, mission_id, instrument_type)

    return form_mission_sample_filter.list_samples(request, queryset, card_title, delete_samples_url,
                                                   process_samples_func, instrument_type=instrument_type)


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

    if thread_id:
        user_logger.info("checking logger")
        thread = None
        for t in threading.enumerate():
            if t.ident == int(thread_id):
                thread = t
                break

        attrs = {
            'component_id': 'div_id_sample_card_notifications',
            'message': _("Success"),
            'alert_type': 'success'
        }
        while thread.is_alive():
            time.sleep(2)

        errors = core_models.FileError.objects.filter(mission=mission, type=core_models.ErrorType.validation, code=1000)
        if errors.exists():
            attrs['alert_type'] = 'danger'
            attrs['message'] = _("Errors found in the file:")
            alert_soup = forms.blank_alert(**attrs)
            message_div = alert_soup.find('div', id='div_id_sample_card_notifications_message')
            message_div.append(ul_elm := soup.new_tag('ul'))
            for error in errors:
                ul_elm.append(li_elm := soup.new_tag('li'))
                error_msg = f"Line {error.line} - {error.message}"
                li_elm.string = error_msg
                logger.error(error_msg)

            soup.append(alert_soup)
            return HttpResponse(soup)

        soup.append(forms.blank_alert(**attrs))
        response = HttpResponse(soup)
        response['HX-Trigger'] = 'reload_sample_list'
        return response

    file_path = filedialog.askopenfilename(title="Select a file")

    if file_path:
        (t := threading.Thread(target=process_file, args=(mission, file_path,), daemon=True)).start()

        attrs = {
            'alert_area_id': 'div_id_sample_card_notifications',
            'logger': user_logger.name,
            'message': _("Loading"),
            'hx-get': reverse_lazy('core:form_gear_type_load_volume', args=(mission_id, t.ident,)),
            'hx-trigger': 'load',
        }

        return HttpResponse(forms.websocket_post_request_alert(**attrs))

    return HttpResponse(soup)


def apply_gear_type_samples(request, mission_id, instrument_type=None, **kwargs):
    soup = BeautifulSoup('', 'html.parser')
    bottles = core_models.Bottle.objects.filter(
        event__mission_id=mission_id, event__instrument__type=instrument_type
    ).order_by("bottle_id")

    bottles = get_samples_queryset(request.POST, bottles)
    gear_type = request.POST.get('set_gear_type', None)

    for bottle in bottles:
        bottle.gear_type = biochem_models.BCGear.objects.get(gear_seq=int(gear_type)) if utils.is_number(
            gear_type) else gear_type

    core_models.Bottle.objects.bulk_update(bottles, ['gear_type'])

    response = HttpResponse(soup)
    response['HX-Trigger'] = 'reload_sample_list'
    return response

def clear_filters(request, mission_id, instrument_type):

    form = GearTypeFilterForm(mission_id=mission_id, instrument_type=instrument_type, collapsed=False)
    return form_mission_sample_filter.clear_filters(form)


url_patterns = [
    path(f'geartype/load_volume/<int:mission_id>/', load_volume, name="form_gear_type_load_volume"),
    path(f'geartype/load_volume/<int:mission_id>/<str:thread_id>/', load_volume, name="form_gear_type_load_volume"),

    path(f'geartype/delete/<int:mission_id>/<str:instrument_type>/', delete_samples, name="form_gear_type_delete_samples"),
    path(f'geartype/apply/<int:mission_id>/<str:instrument_type>/', apply_gear_type_samples, name="form_gear_type_apply_samples"),

    path(f'geartype/clear/<int:mission_id>/<int:instrument_type>/', clear_filters, name="form_mission_sample_type_clear"),

    path(f'geartype/<int:mission_id>/<int:instrument_type>/list_samples/', list_samples,
         name="mission_gear_type_sample_list"),
]
