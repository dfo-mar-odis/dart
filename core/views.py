from crispy_forms.templatetags.crispy_forms_filters import as_crispy_form
from crispy_forms.utils import render_crispy_form
from django.forms import model_to_dict
from django.http import HttpResponse, HttpResponseRedirect
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.urls import reverse_lazy
from render_block import render_block_to_string

from biochem import models
from dart2.views import GenericFlilterMixin, GenericCreateView, GenericUpdateView, GenericDetailView

from core import forms, filters, models, validation


class MissionMixin:
    model = models.Mission
    page_title = _("Missions")


class EventMixin:
    model = models.Event
    page_title = _("Event Details")


class MissionFilterView(MissionMixin, GenericFlilterMixin):
    filterset_class = filters.MissionFilter
    new_url = reverse_lazy("core:mission_new")
    home_url = ""
    fields = ["id", "name", "start_date", "end_date", "biochem_table"]


class MissionCreateView(MissionMixin, GenericCreateView):
    form_class = forms.MissionSettingsForm
    template_name = "core/mission_settings.html"

    def get_success_url(self):
        success = reverse_lazy("core:event_details", args=(self.object.pk, ))
        return success


class MissionUpdateView(MissionCreateView, GenericUpdateView):

    def form_valid(self, form):
        events = self.object.events.all()
        errors = []
        for event in events:
            event.validation_errors.all().delete()
            errors += validation.validate_event(event)

        models.ValidationError.objects.bulk_create(errors)
        return super().form_valid(form)


class EventDetails(MissionMixin, GenericDetailView):
    page_title = _("Missions Events")
    template_name = "core/mission_events.html"

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk, ))


class EventCreateView(EventMixin, GenericCreateView):
    template_name = "core/event_settings.html"
    form_class = forms.EventForm

    def get_initial(self):
        initial = super().get_initial()

        mission = models.Mission.objects.get(pk=self.kwargs['mission_id'])
        initial['mission'] = mission

        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['mission'] = models.Mission.objects.get(pk=self.kwargs['mission_id'])
        return context


def new_event(request, mission_id):
    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        context['mission'] = models.Mission.objects.get(pk=mission_id)
        form = forms.EventForm(initial={'mission': mission_id})
        context['form'] = form
        response = HttpResponse(render_to_string('core/event_settings.html', context=context))
        return response
    elif request.method == "POST":
        form = forms.EventForm(request.POST, initial={'mission': mission_id})

        if form.is_valid():
            event = form.save()
            form = forms.EventForm(instance=event)
            context['form'] = form
            context['event'] = event
            context['actionform'] = forms.ActionForm(initial={'event': event.pk})
            context['page_title'] = _("Event : ") + str(event.event_id)
            response = HttpResponse(render_block_to_string('core/event_settings.html', 'content', context=context))
            response['HX-Trigger'] = "event_updated"
            response['HX-Push-Url'] = reverse_lazy('core:event_update', args=(event.pk,))
            return response

        context['form'] = form
        response = HttpResponse(render_block_to_string('core/event_settings.html', 'event_form', context=context))
        return response


def update_event(request, event_id):
    context = {}
    context.update(csrf(request))

    event = models.Event.objects.get(pk=event_id)
    context['event'] = event
    context['page_title'] = _("Event : ") + str(event.event_id)
    if request.method == "GET":
        form = forms.EventForm(instance=event, initial={'mission': event.mission.pk})
        context['form'] = form
        context['actionform'] = forms.ActionForm(initial={'event': event_id})
        context['actions'] = event.actions.all()

        # this is the initial page load so we need to load all elements on the page.
        response = HttpResponse(render_to_string('core/event_settings.html', context=context))
        response['HX-Trigger'] = 'update_actions'
        return response
    elif request.method == "POST":
        form = forms.EventForm(request.POST, instance=event)
        context['form'] = form

        if form.is_valid():
            event = form.save()
            context['event'] = event
            context['actionform'] = forms.ActionForm(initial={'event': event_id})
            context['actions'] = event.actions.all()
            context['page_title'] = _("Event : ") + str(event.event_id)
            response = HttpResponse(render_block_to_string('core/event_settings.html', 'event_form', context=context))
            response['HX-Trigger'] = 'update_actions'
            return response

        response = HttpResponse(render_block_to_string('core/event_settings.html', 'event_form', context=context))
        return response


def new_action(request, event_id):
    context = {}
    context.update(csrf(request))

    event = models.Event.objects.get(pk=event_id)
    context['event'] = event
    if request.method == "GET":
        form = forms.ActionForm(initial={'event': event_id})
        context['actionform'] = form
        context['actions'] = event.actions.all()
        response = HttpResponse(render_block_to_string('core/event_settings.html', 'action_block', context=context))
        return response
    elif request.method == "POST":
        form = forms.ActionForm(request.POST, initial={'event': event_id})
        if form.is_valid():
            action = form.save()
            # context['actionforms'] = [forms.ActionForm(instance=action) for action in event.actions.all()]
            context['actionform'] = forms.ActionForm(initial={'event': event_id})
            context['actions'] = event.actions.all()
            response = HttpResponse(render_block_to_string('core/event_settings.html', 'action_block', context=context))
            response['HX-Trigger'] = 'update_actions'
            return response

        context['actionform'] = form
        response = HttpResponse(render_block_to_string('core/event_settings.html', 'action_block', context=context))
        return response


def update_action(request):
    context = {}
    context.update(csrf(request))

    action = models.Action.objects.last()
    if request.method == "GET":
        form = forms.ActionForm(instance=action)
        context['form'] = form
        response = HttpResponse(render_block_to_string('core/event_settings.html', 'add_action_block', context=context))
        return response
    elif request.method == "POST":
        form = forms.ActionForm(request.POST)
        context['form'] = form

        if form.is_valid():
            action = form.save()
            context['action'] = action
            response = HttpResponse(render_block_to_string('core/event_settings.html', 'add_action_block', context=context))
            return response

        response = HttpResponse(render_block_to_string('core/event_settings.html', 'add_action_block', context=context))
        return response


def list_action(request, event_id):
    event = models.Event.objects.get(pk=event_id)
    context = {'event': event}
    response = HttpResponse(render_block_to_string('core/event_settings.html', 'action_table_block', context=context))
    return response