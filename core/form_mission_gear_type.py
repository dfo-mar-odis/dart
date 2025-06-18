import os
import threading
import time
import numpy as np

from tkinter import filedialog

import pandas as pd
from bs4 import BeautifulSoup
from django.db.models import Count

from django.http import HttpResponse
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.urls import path, reverse_lazy
from django import forms as django_forms
from django.db.models import Q
from django_pandas.io import read_frame
from core import models, forms, utils

from bio_tables import models as biochem_models

import logging

user_logger = logging.getLogger('dart.user.gear_type')
logger = logging.getLogger('dart')


class GearTypeFilterForm(django_forms.ModelForm):
    set_gear_type = django_forms.ChoiceField(
        required=False,
        label=_("Set Gear Type"),
        widget=django_forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = models.Bottle
        fields = '__all__'
        widgets = {
            'event': django_forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, mission_id, instrument_type=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        instrument_type = instrument_type if instrument_type else models.InstrumentType.other
        if instrument_type is not None:
            # get events mathing the instrument type, but only if it has samples
            self.fields['event'].queryset = self.fields['event'].queryset.filter(
                instrument__type=instrument_type
            ).annotate(
                sample_count=Count('bottles__samples'), pk_sample_count=Count('bottles__plankton_data')
            ).filter(
                Q(sample_count__gt=0) | Q(pk_sample_count__gt=0)
            )

        self.fields['event'].widget.attrs.update({
            'hx-get': reverse_lazy('core:form_gear_type_list_samples', args=(mission_id, instrument_type,)),
            'hx-trigger': 'change',
            'hx-swap': 'none',
        })

        gear_type_choices = [('', '--------------')] + [
            (g.gear_seq,
             f"{g.gear_seq} - {g.type} - {(g.description[:100] + "...") if len(g.description) > 100 else g.description}")
            for g in biochem_models.BCGear.objects.all().order_by("type", "gear_seq")
        ]
        self.fields['set_gear_type'].choices = gear_type_choices


def query_samples(mission_id, instrument_type, arguments: dict = None):
    bottles = models.Bottle.objects.filter(event__mission_id=mission_id,
                                           event__instrument__type=instrument_type).order_by("bottle_id")

    if arguments is None:
        return bottles

    if event := arguments.get('event', None):
        bottles = bottles.filter(event__pk=event)

    return bottles


def list_samples(request, mission_id, instrument_type, **kwargs):
    soup = BeautifulSoup('', 'html.parser')

    # When ever the table list is updated we'll clear any notifications from the forms card.
    soup.append('<div id="div_id_sample_card_notifications" hx-swap-oob="true" ></div>')

    bottles = query_samples(mission_id, instrument_type, request.GET if request.method == "GET" else request.POST)

    # if the table is being paged then we want to truncate the result set to just what we're working with
    page = None
    if 'page' in request.GET:
        page = int(request.GET.get('page', 0))
        results = 100
        start = int(page) * results
        end = start + results
        bottles = bottles[start:end]

    bottles = bottles.values(
        'bottle_id',
        'event__event_id',
        'mesh_size',
        'volume',
        'gear_type__gear_seq',
        'gear_type__description',
    )

    df = read_frame(bottles)

    # Note:
    #   The template 'mission_gear_type.html' has the table header, but if I was going to set
    #   the human-readable column names, I'd do it here. The table header has to agree with
    #   the 'bottles = bottles.values' statement above, they have to have the same elements
    #   in the same order

    # df.columns = ["Sample", "Event", "Mesh", "Volume", "GearType", "Description"]

    html = df.to_html(index=False)
    table_soup = BeautifulSoup(html, 'html.parser')

    table = table_soup.find('table')
    # we don't need the head of the table, just the body. It's a waste of bandwidth to send it.
    table.find('thead').decompose()

    table_body = table.find('tbody')
    table_body.attrs['id'] = "tbody_id_gear_type_sample_table"
    table_body.attrs['hx-swap-oob'] = "true"

    if isinstance(page, int):
        # add a pageing trigger to the second last row of the table. This way the next table update will
        # start before the user reaches the end of the table.
        page_trigger = 2
        if len(tr_list := table_body.findAll('tr', recursive=False)) > page_trigger:
            url = request.path
            last_tr = tr_list[-page_trigger]
            last_tr.attrs['hx-target'] = '#tbody_id_gear_type_sample_table'
            last_tr.attrs['hx-trigger'] = 'intersect once'
            last_tr.attrs['hx-get'] = url + f"?page={page + 1}"
            last_tr.attrs['hx-swap'] = "beforeend"

        # after the initial load of the table, we now only want to send
        # back rows to be swapped in at the end of the table.
        if page > 0:
            return HttpResponse(tr_list)

    soup.append(table)
    return HttpResponse(soup.prettify())


def delete_samples(request, mission_id, instrument_type):
    bottles = query_samples(mission_id, instrument_type, request.POST)
    bottles.delete()

    mission = models.Mission.objects.get(pk=mission_id)
    form = GearTypeFilterForm(mission_id, instrument_type)

    context = {
        'form': form,
        'mission': mission,
        'instrument_type': instrument_type
    }
    context.update(csrf(request))

    html = render_to_string('core/partials/mission_gear_type_filter.html', context=context)
    soup = BeautifulSoup(html, 'html.parser')
    form_soup = soup.find('form')
    form_soup.attrs['hx-swap-oob'] = "true"

    response = HttpResponse(form_soup.parent)
    response['HX-Trigger'] = 'reload_sample_list'

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
            event = models.Event.objects.get(event_id=event_id)
            try:
                bottle = models.Bottle.objects.get(event=event, bottle_id=sample_id)
            except models.Bottle.DoesNotExist:
                errors.append((idx + 1, f"No Bottle with bottle_id={sample_id} for Event {event_id}"))
                continue

            bottle.volume = volume
            update_bottles.append(bottle)
        except models.Event.DoesNotExist:
            errors.append((idx + 1, f"No Bottle with bottle_id={sample_id} for Event {event_id}"))

    if len(errors) == 0 and len(update_bottles) > 0:
        models.Bottle.objects.bulk_update(update_bottles, ['volume'])
        return None

    return errors


def process_file(mission, file_path):
    file_name = os.path.basename(file_path)
    models.FileError.objects.filter(mission=mission, file_name=file_name).delete()

    expected_columns = ["mission", "tow", "event", "sample_id", "net_number", "volume"]
    df = pd.read_excel(file_path)
    if list(df.columns) != expected_columns:
        raise ValueError(f"Header does not match expected columns: {expected_columns}")

    errors = validate_event_and_bottle(df)
    if errors:
        for error in errors:
            models.FileError.objects.create(mission=mission, message=error[1], line=error[0],
                                            file_name=file_name, type=models.ErrorType.validation, code=1000)


def load_volume(request, mission_id, thread_id=None, **kwargs):
    soup = BeautifulSoup('', 'html.parser')
    mission = models.Mission.objects.get(pk=mission_id)

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

        errors = models.FileError.objects.filter(mission=mission, type=models.ErrorType.validation, code=1000)
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
    bottles = query_samples(mission_id, instrument_type, request.POST)
    gear_type = request.POST.get('set_gear_type', None)

    for bottle in bottles:
        bottle.gear_type = biochem_models.BCGear.objects.get(gear_seq=int(gear_type)) if utils.is_number(
            gear_type) else gear_type

    models.Bottle.objects.bulk_update(bottles, ['gear_type'])

    response = HttpResponse(soup)
    response['HX-Trigger'] = 'reload_sample_list'
    return response


url_patterns = [
    path(f'geartype/<int:mission_id>/<int:instrument_type>/list_samples/', list_samples,
         name="form_gear_type_list_samples"),
    path(f'geartype/load_volume/<int:mission_id>/', load_volume, name="form_gear_type_load_volume"),
    path(f'geartype/load_volume/<int:mission_id>/<str:thread_id>/', load_volume, name="form_gear_type_load_volume"),

    path(f'geartype/delete/<int:mission_id>/<str:instrument_type>/', delete_samples,
         name="form_gear_type_delete_samples"),
    path(f'geartype/apply/<int:mission_id>/<str:instrument_type>/', apply_gear_type_samples,
         name="form_gear_type_apply_samples"),
]
