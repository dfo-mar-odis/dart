import re
import numpy as np

from bs4 import BeautifulSoup
from django import forms
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path

from dart import models

class ActionsModelForm(forms.ModelForm):

    event = forms.ModelChoiceField(
        queryset=models.Event.objects.all(),
        required=True,
        widget=forms.HiddenInput()
    )

    date_time = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={
                'type': 'datetime-local',
                'max': '9999-12-31T23:59'
            }
        ),
        required=True
    )

    latitude = forms.CharField()
    longitude = forms.CharField()

    class Meta:
        model = models.Action
        fields = '__all__'

    def clean_longitude(self):
        data = self.cleaned_data['longitude']
        try:
            if re.match(r'(-{0,1}\d{1,3} \d{1,2}.*\d+( [Ee]|[Ww])*)', data):
                lon_split: [str] = data.split(' ')
                lon = float(lon_split[0])
                negative = False
                if lon < 0:
                    lon *= -1
                    negative = True

                if len(lon_split) > 1:
                    lon += float(lon_split[1])/60
                if negative or (len(lon_split) > 2 and lon_split[2].upper() == 'W'):
                    lon *= -1
                return str(np.round(lon, models.Action.longitude.field.decimal_places))

            lon = float(data)
            return str(np.round(lon, models.Action.longitude.field.decimal_places))
        except ValueError:
            message = _("Longitude is badly formatted. Must be in decimal degrees, or degree minutes with 'W' or 'E'. E.g: 62 24.53 W")
            raise forms.ValidationError(message)

    def clean_latitude(self):
        data = self.cleaned_data['latitude']
        try:
            if re.match(r'(-{0,1}\d{1,2} \d{1,2}\.*\d+( [Nn]|[Ss])*)', data):
                lat_split: [str] = data.split(' ')
                lat = float(lat_split[0])
                negative = False
                if lat < 0:
                    lat *= -1
                    negative = True

                if len(lat_split) > 1:
                    lat += float(lat_split[1])/60
                if negative or (len(lat_split) > 2 and lat_split[2].upper() == 'S'):
                    lat *= -1
                return str(np.round(lat, models.Action.latitude.field.decimal_places))

            lat = float(data)
            return str(np.round(lat, models.Action.latitude.field.decimal_places))
        except ValueError:
            message = _("Latitude is badly formatted. Must be in decimal degrees, or degree minutes with 'N' or 'S'. E.g: 42 12.432 N")
            raise forms.ValidationError(message)

def get_form(request, event_id, action_id=None):

    event = models.Event.objects.get(pk=event_id)
    context = {
        'event': event,
    }

    action = None
    if action_id:
        action = event.actions.get(pk=action_id)
        context['action'] = action

    if request.method == "POST":
        initial = {
            "event": event.pk,
        }

        context['form'] = ActionsModelForm(request.POST or None, instance=action, initial=initial)
        if context['form'].is_valid():
            action = context['form'].save()
            context['form'] = ActionsModelForm(instance=action)
    elif action:
        context['form'] = ActionsModelForm(instance=action)
    else:
        initial = {
            "event": event.pk,
        }

        context['form'] = ActionsModelForm(initial=initial)

    html = render_to_string('dart/forms/action_form.html', context=context)

    response = HttpResponse(html)
    return response


def delete_action(request, event_id, action_id):

    context = {}
    if request.method == "POST":
        event = models.Event.objects.get(pk=event_id)
        context['event'] = event
        action = event.actions.get(pk=action_id)
        initial = {
            "event": event.pk,
            "type": action.type,
            "date_time": action.date_time,
            "latitude": action.latitude,
            "longitude": action.longitude,
            "sounding": action.sounding,
            "comment": action.comment
        }

        context['form'] = ActionsModelForm(initial=initial)
        action.delete()

    html = render_to_string('dart/forms/action_form.html', context=context)

    response = HttpResponse(html)
    return response

urlpatterns = [
    path("event/action/<int:event_id>", get_form, name="form_event_action_new"),
    path("event/action/<int:event_id>/<int:action_id>", get_form, name="form_event_action_update"),
    path("event/action/delete/<int:event_id>/<int:action_id>", delete_action, name="form_event_action_delete"),
]