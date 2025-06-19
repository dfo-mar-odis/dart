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

class EventDetailForm(forms.ModelForm):
    mission = forms.ModelChoiceField(
        queryset=models.Mission.objects.all(),
        required=True,
        widget=forms.HiddenInput()
    )
    station = forms.ChoiceField(
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
        widget = forms.Select(attrs={
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
        self.fields['station'].choices = station_choices

        self.fields['instrument'].choices = [('', '--------'), (0, _('New'))] + [
            (obj.pk, str(obj)) for obj in models.Instrument.objects.all()
        ]

    def clean_station(self):
        station = self.cleaned_data.get('station')  # this will be a GlobalStation pk value
        try:
            glb_station = user_models.GlobalStation.objects.get(pk=int(station))
        except user_models.GlobalStation.objects.DoesNotExist as ex:
            # Example: Ensure station is not empty and exists
            raise forms.ValidationError(_("Please select a valid station."))

        station = models.Station.objects.get_or_create(name=glb_station.name)

        return station[0]


def get_form(request, mission_id, event_id=None):

    soup = BeautifulSoup('', 'html.parser')

    # 1) get the root object this child object will be attached to
    mission = models.Mission.objects.get(pk=mission_id)
    context = {'mission': mission}

    # 2) if an ID for the child object is provided then store it for using with the form as an update instance
    event = None
    if event_id:
        event = models.Event.objects.get(pk=event_id)
        context['event'] = event
        # if we're editing an existing event we want to put labels on the card header to accept changes
        div_button_col = soup.new_tag("div", id="div_id_card_event_details_button_column", attrs={'class':"col", 'hx-swap-oob':"true"})
        soup.append(div_button_col)

        #These labels are for inputs in the dart/forms/event_details_form.html template
        div_button_col.append(label_new:=soup.new_tag('label', attrs={'for':"input_id_event_form_new"}))
        div_button_col.append(label_update:=soup.new_tag('label', attrs={'for':"input_id_event_form_update"}))

        label_new.append(BeautifulSoup(load_svg('copy')))
        label_new.attrs['class'] = "btn btn-sm btn-secondary"
        label_new.attrs['title'] = _("Copy to New Event")

        label_update.append(BeautifulSoup(load_svg('check')))
        label_update.attrs['class'] = "btn btn-sm btn-primary ms-1"
        label_update.attrs['title'] = _("Update Event")

    if request.method == "POST":
        # 3) update only create or update the object if in a post request.
        # 3a) All forms should have a hidden field for whatever object the new element is being tied to.
        initial = {
            "mission": mission.pk,
        }

        # Special case: have to convert the dart.models.Station to a user_settings.models.GlobalStation
        if hasattr(event, 'station'):
            station = user_models.GlobalStation.objects.get_or_create(name=event.station)[0]
            initial['station'] = station.pk

        # 3b) populate the form and store it in the context. Either it's valid and you'll return the
        #   form with the new instance that was just created or you'll return the form with errors
        #   the user needs to update.
        context['form'] = EventDetailForm(request.POST or None, instance=event, initial=initial)

        # 3c) validate the form, if valid a new child object will be created and returned.
        if context['form'].is_valid():
            event = context['form'].save()
            context['event'] = event
            context['form'] = EventDetailForm(instance=event)
            context['action_form'] = event_action_form.ActionsModelForm(initial={'event': event.pk})
    elif event:
        # 4) If this is a GET request, but the object we're creating exists then we want a form for updating
        # 4a) Create a version of the form that has an instance for updating and any required subforms.
        station = user_models.GlobalStation.objects.get_or_create(name=event.station)[0]
        context['form'] = EventDetailForm(instance=event, initial={'station': station.pk})
        context['action_form'] = event_action_form.ActionsModelForm(initial={'event': event.pk})
    else:
        # 5) If this is a GET request, but no object is provided then we're creating a new object.
        # 5a) Populate the inital values for the form
        initial = {
            "mission": mission.pk,
            "event_id": (mission.events.aggregate(max_id=Max('event_id'))['max_id'] + 1) if mission.events.exists() else 1
        }
        # 5b) create the blank form to be returned
        context['form'] = EventDetailForm(initial=initial)

    # 6) Link the actual form to the page it's to be displayed on.
    form_html = render_to_string('dart/forms/event_details_form.html', context=context)
    form_soup = BeautifulSoup(form_html, 'html.parser')
    soup.append(form_soup)

    response = HttpResponse(soup)

    # Special Case: In the case of the event form we want to deselect a selected event if we're
    #   creating a new event and reload the events list to include the event we just created.
    triggers = []
    if 'update' not in request.path:
        triggers.append('deselect')  # deselected the selected event if there's an event selected

        if context.get('event', None):
            triggers.append('reload_events')

    if triggers:
        response['HX-Trigger'] = ', '.join(triggers)
    return response


def new_station(request):

    form = None

    if 'cancel' in request.GET:
        form = EventDetailForm()
    elif request.GET.get('station', "0") != "0":
        return HttpResponse()  # user selected an element that wasn't 0, "new"
    elif station:=request.POST.get('station', None):
        n_station = user_models.GlobalStation(name=station)
        n_station.save()

        form = EventDetailForm(initial={"station": n_station.pk})

    if form:
        html = render_to_string('dart/forms/event_details_form.html', context={'form': form})
        soup = BeautifulSoup(html, 'html.parser')
        station_elm = soup.find('select', id='id_station')
        station_elm.attrs['hx-swap-oob'] = 'true'
        return HttpResponse(station_elm.parent)

    context = {
        "field_swap_id": "id_station",
        "field_name": "station",
        "add_url": reverse_lazy("dart:form_events_new_station"),
        "cancel_url": reverse_lazy("dart:form_events_new_station"),
    }
    html = render_to_string('dart/forms/components/field_new_option.html', context=context)
    return HttpResponse(html)


def new_instrument(request):

    form = None

    if 'cancel' in request.GET:
        form = EventDetailForm()
    elif request.GET.get('instrument', "0") != "0":
        return HttpResponse()  # user selected an element that wasn't 0, "new"
    elif (type:=request.POST.get('type', None)) and (inst_name:=request.POST.get('instrument', None)):
        n_instrument = models.Instrument(type=type, name=inst_name)
        n_instrument.save()

        form = EventDetailForm(initial={"instrument": n_instrument.pk})

    if form:
        html = render_to_string('dart/forms/event_details_form.html', context={'form': form})
        soup = BeautifulSoup(html, 'html.parser')
        station_elm = soup.find('select', id='id_instrument')
        station_elm.attrs['hx-swap-oob'] = 'true'
        return HttpResponse(station_elm.parent)

    context = {
        "field_swap_id": "id_instrument",
        "field_name": "instrument",
        "types": [t for t in models.InstrumentType.choices],
        "add_url": reverse_lazy("dart:form_events_new_instrument"),
        "cancel_url": reverse_lazy("dart:form_events_new_instrument"),
    }
    html = render_to_string('dart/forms/components/field_new_option_instrument.html', context=context)
    response = HttpResponse(html)
    return response


urlpatterns = [
    path("event/new/<int:mission_id>/", get_form, name="form_events_new"),
    path("event/new/station/", new_station, name="form_events_new_station"),
    path("event/new/instrument/", new_instrument, name="form_events_new_instrument"),
    path("event/update/<int:mission_id>/<int:event_id>/", get_form, name="form_events_update"),
]