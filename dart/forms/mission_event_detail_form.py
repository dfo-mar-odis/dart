import copy
import math
import numpy as np

from bs4 import BeautifulSoup
from django import forms
from django.db.models import Max
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path, reverse_lazy
from django.utils.translation import gettext_lazy as _

from config.utils import load_svg
from dart import models
from dart.forms import event_action_form

from user_settings import models as user_models

import re
from django import forms
from django.core.exceptions import ValidationError

class EventDetailForm(forms.ModelForm):
    mission = forms.ModelChoiceField(
        queryset=models.Mission.objects.all(),
        required=True,
        widget=forms.HiddenInput()
    )
    station = forms.ModelChoiceField(
        queryset=models.Station.objects.all(),
        required=True,
        widget=forms.HiddenInput()
    )
    global_station = forms.ChoiceField(
        required=True,
        choices=[],
        label=_("Station"),
        widget=forms.Select(attrs={
            'hx-swap': 'none',
            'hx-trigger': 'change',
            'hx-get': reverse_lazy('dart:form_events_new_station')  # Replace with your actual URL or use reverse()
        })
    )
    instrument = forms.ModelChoiceField(
        queryset=models.Instrument.objects.all(),
        required=True,
        empty_label="--------",
        widget=forms.Select(attrs={
            'hx-swap': 'none',
            'hx-trigger': 'change',
            'hx-get': reverse_lazy('dart:form_events_new_instrument')  # Replace with your actual URL or use reverse()
        })
    )

    class Meta:
        model = models.Event
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add "New" option (id=0) to the queryset
        station_choices = [('', '--------'), (0, _('New'))]
        station_choices += [
            (gs.pk, str(gs)) for gs in user_models.GlobalStation.objects.all()
        ]
        self.fields['global_station'].choices = station_choices

        self.fields['instrument'].choices = [('', '--------'), (0, _('New'))] + [
            (obj.pk, str(obj)) for obj in models.Instrument.objects.all()
        ]

    def clean_global_station(self):
        station = self.cleaned_data.get('global_station')  # this will be a GlobalStation pk value
        try:
            glb_station = user_models.GlobalStation.objects.get(pk=int(station))
        except user_models.GlobalStation.objects.DoesNotExist as ex:
            # Example: Ensure station is not empty and exists
            raise forms.ValidationError(_("Please select a valid station."))

        local_station = models.Station.objects.get_or_create(name=glb_station.name)[0]
        self.cleaned_data['station'] = local_station

        return station


def get_form(request, mission_id, event_id=None):
    soup = BeautifulSoup('', 'html.parser')
    div_button_col = soup.new_tag("div", id="div_id_card_event_details_button_column",
                                  attrs={'class': "col", 'hx-swap-oob': "true"})
    soup.append(div_button_col)

    label_update = soup.new_tag('label', attrs={'for': "input_id_event_form_new"})
    if event_id and 'copy' not in request.path:
        label_update.attrs['for'] = "input_id_event_form_update"

    label_update.append(BeautifulSoup(load_svg('check'), 'html.parser'))
    label_update.attrs.update({'class': "btn btn-sm btn-primary ms-1", 'title': _("Update Event")})
    div_button_col.append(label_update)

    mission = models.Mission.objects.get(pk=mission_id)
    context = {'mission': mission}
    initial = {'mission': mission.pk}

    event = models.Event.objects.get(pk=event_id) if event_id else None
    if event:
        context['event'] = event

    if request.method == "POST":
        if event and hasattr(event, 'station'):
            station = user_models.GlobalStation.objects.get_or_create(name=event.station)[0]
            initial['global_station'] = station
        elif (station_id := request.POST.get('global_station', '')):
            station = user_models.GlobalStation.objects.get(pk=int(station_id))
            local_stn = models.Station.objects.get_or_create(name=station)[0]
            request.POST = copy.copy(request.POST)
            request.POST['station'] = local_stn.pk

        context['form'] = EventDetailForm(request.POST, instance=event, initial=initial)
        if context['form'].is_valid():
            event = context['form'].save()
            if event.instrument.type == models.InstrumentType.net and any(
                    sub in event.instrument.name.lower() for sub in ["202", "76"]):
                event.surface_area = np.pi * np.power(0.75 / 2, 2)
                event.flowmeter_constant = 0.3
                event.save()
            context.update({'event': event, 'form': EventDetailForm(instance=event, initial={
                'global_station': user_models.GlobalStation.objects.get_or_create(name=event.station)[0].pk
            })})
            context['action_form'] = event_action_form.ActionsModelForm(initial={'event': event.pk})
    elif event and 'copy' not in request.path:
        station = user_models.GlobalStation.objects.get_or_create(name=event.station)[0]
        initial['global_station'] = station.pk
        context.update({
            'form': EventDetailForm(instance=event, initial=initial),
            'action_form': event_action_form.ActionsModelForm(initial={'event': event.pk})
        })
    else:
        if event:
            initial.update({field.name: getattr(event, field.name, None) for field in event._meta.fields
                            if field.name not in ['id', 'event_id']})
            initial['global_station'] = user_models.GlobalStation.objects.get_or_create(name=event.station.name)[0].pk
        initial["event_id"] = mission.events.aggregate(max_id=Max('event_id'))['max_id'] + 1 if mission.events.exists() else 1
        context['form'] = EventDetailForm(initial=initial)

    form_html = render_to_string('dart/forms/event_details_form.html', context=context)
    soup.append(BeautifulSoup(form_html, 'html.parser'))

    response = HttpResponse(soup)
    triggers = []
    triggers.append('deselect')
    if 'update' not in request.path and context.get('event'):
        triggers.append('reload_events')
    if triggers:
        response['HX-Trigger'] = ', '.join(triggers)

    return response


def new_station(request):
    if 'cancel' in request.GET:
        form = EventDetailForm()
        return _render_form(form)

    if request.GET.get('global_station', "0") != "0":
        return HttpResponse()  # User selected an existing station, no action needed.

    if request.method == "POST":
        station_name = request.POST.get('global_station', '').strip()
        if not station_name:
            return _render_field_option(is_invalid=True)

        n_station, _ = user_models.GlobalStation.objects.get_or_create(name__iexact=station_name)
        local_station, _ = models.Station.objects.get_or_create(name=n_station.name)
        form = EventDetailForm(initial={"global_station": n_station.pk, "station": local_station.pk})
        return _render_form(form)

    return _render_field_option()


def _render_form(form):
    html = render_to_string('dart/forms/event_details_form.html', context={'form': form})
    soup = BeautifulSoup(html, 'html.parser')
    for field_id in ['id_global_station', 'id_station']:
        field_elm = soup.find(attrs={'id': field_id})
        if field_elm:
            field_elm.attrs['hx-swap-oob'] = 'true'
    return HttpResponse(soup)


def _render_field_option(is_invalid=False):
    context = {
        "field_swap_id": "id_global_station",
        "field_name": "global_station",
        "placeholder": _("Station Name"),
        "add_url": reverse_lazy("dart:form_events_new_station"),
        "cancel_url": reverse_lazy("dart:form_events_new_station"),
        "is_invalid": is_invalid,
    }
    html = render_to_string('dart/forms/components/field_new_option.html', context=context)
    return HttpResponse(html)


# Python
def new_instrument(request):
    if 'cancel' in request.GET:
        form = EventDetailForm()
        return _render_form(form)

    if request.GET.get('instrument', "0") != "0":
        return HttpResponse()  # User selected an existing instrument, no action needed.

    if request.method == "POST":
        inst_name = request.POST.get('instrument', '').strip()
        if not inst_name:
            return _render_instrument_field_option(is_invalid=True)

        instrument_type = request.POST.get('type')
        if instrument_type:
            n_instrument = models.Instrument(type=instrument_type, name=inst_name)
            n_instrument.save()
            form = EventDetailForm(initial={"instrument": n_instrument.pk})
            return _render_instrument_form(form)

    return _render_instrument_field_option()


def _render_instrument_form(form):
    html = render_to_string('dart/forms/event_details_form.html', context={'form': form})
    soup = BeautifulSoup(html, 'html.parser')
    instrument_elm = soup.find('select', id='id_instrument')
    instrument_elm.attrs['hx-swap-oob'] = 'true'
    return HttpResponse(instrument_elm.parent)


def _render_instrument_field_option(is_invalid=False):
    context = {
        "field_swap_id": "id_instrument",
        "field_name": "instrument",
        "types": [t for t in models.InstrumentType.choices],
        "add_url": reverse_lazy("dart:form_events_new_instrument"),
        "cancel_url": reverse_lazy("dart:form_events_new_instrument"),
        "is_invalid": is_invalid,
    }
    html = render_to_string('dart/forms/components/field_new_option_instrument.html', context=context)
    return HttpResponse(html)


# Python
def delete_event(request, mission_id, event_id):
    if request.method == "POST":
        try:
            mission = models.Mission.objects.get(pk=mission_id)
            event = mission.events.get(pk=event_id)
            event.delete()

            html = render_to_string('dart/partials/event_details_card.html', context={"mission": mission})
            response = HttpResponse(html)
            response['HX-Trigger'] = "reload_events"
            return response
        except models.Mission.DoesNotExist:
            return HttpResponse(status=404, content="Mission not found.")
        except models.Event.DoesNotExist:
            return HttpResponse(status=404, content="Event not found.")
    else:
        return HttpResponse(status=405, content="Method not allowed.")


urlpatterns = [
    path("event/new/<int:mission_id>/", get_form, name="form_events_new"),
    path("event/new/station/", new_station, name="form_events_new_station"),
    path("event/new/instrument/", new_instrument, name="form_events_new_instrument"),
    path("event/update/<int:mission_id>/<int:event_id>/", get_form, name="form_events_update"),
    path("event/copy/<int:mission_id>/<int:event_id>/", get_form, name="form_events_copy"),
    path("event/delete/<int:mission_id>/<int:event_id>/", delete_event, name="form_events_delete"),
]
