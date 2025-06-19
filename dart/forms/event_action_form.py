from bs4 import BeautifulSoup
from django import forms
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

    class Meta:
        model = models.Action
        fields = '__all__'


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