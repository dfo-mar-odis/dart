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
from dart2.views import GenericFlilterMixin, GenericCreateView, GenericUpdateView, GenericDetailView, GenericViewMixin, \
    GenericTemplateView

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


# We get different data from kwargs depending on if this is a view to
# create a new event or a view to update an existing event
# so we have respective EventCreate and EventUpdate views
class EventCreateView(EventMixin, GenericTemplateView):
    template_name = "core/event_settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = forms.EventForm(initial={'mission': self.kwargs['mission_id']})

        return context


class EventUpdateView(EventMixin, GenericTemplateView):
    template_name = "core/event_settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = models.Event.objects.get(pk=self.kwargs['event_id'])
        context['event'] = event
        context['form'] = forms.EventForm(instance=event)
        context['actionform'] = forms.ActionForm(initial={'event': event.pk})
        context['attachmentform'] = forms.AttachmentForm(initial={'event': event.pk})

        return context


# This hx call assumes the form is on a Django view that has already laid out the page.
# The method's job is to update the existing content on the page
def hx_update_event(request, mission_id, event_id):
    context = {}

    if request.method == "GET":
        if mission_id != 0 and event_id == 0:
            context['form'] = forms.EventForm(initial={'mission': mission_id})
            response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'event_content', context=context))
            return response
        else:
            event = models.Event.objects.get(pk=event_id)
            context['event'] = event
            context['form'] = forms.EventForm(instance=event)
            context['actionform'] = forms.ActionForm(initial={'event': event.pk})
            context['attachmentform'] = forms.AttachmentForm(initial={'event': event.pk})
            response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'event_content', context=context))
            return response
    if request.method == "POST":
        mission_id = request.POST['mission']
        event_id = request.POST['event_id']
        context.update(csrf(request))
        update = models.Event.objects.filter(mission_id=mission_id, event_id=event_id).exists()

        if update:
            event = models.Event.objects.get(mission_id=mission_id, event_id=event_id)
            form = forms.EventForm(request.POST, instance=event)
        else:
            form = forms.EventForm(request.POST, initial={'mission': mission_id})

        if form.is_valid():
            event = form.save()
            form = forms.EventForm(instance=event)
            context['form'] = form
            context['event'] = event
            context['actionform'] = forms.ActionForm(initial={'event': event.pk})
            context['attachmentform'] = forms.AttachmentForm(initial={'event': event.pk})
            context['page_title'] = _("Event : ") + str(event.event_id)
            if update:
                # if updating an event, everything is already on the page, just update the event form area
                response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'event_form', context=context))
                response['HX-Trigger'] = 'update_actions, update_attachments'
            else:
                # if creating a new event, update the entire event block to add other blocks to the page
                response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'event_content', context=context))
                response['HX-Trigger'] = "event_updated"
                # response['HX-Push-Url'] = reverse_lazy('core:event_edit', args=(event.pk,))
            return response

        context['form'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'event_form', context=context))
        return response


def hx_update_action(request, action_id):
    context = {}
    context.update(csrf(request))

    if 'reset' in request.GET:
        # I'm passing the event id to initialize the form through the 'action_id' variable
        # it's not stright forward, but the action form needs to maintain an event or the
        # next action won't know what event it should be attached to.
        form = forms.ActionForm(initial={'event': action_id})
        context['actionform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'action_form', context=context))
        return response
    else:
        action = models.Action.objects.get(pk=action_id)
        event = action.event
    context['event'] = event

    if request.method == "GET":
        form = forms.ActionForm(instance=action, initial={'event': event.pk})
        context['actionform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'action_form', context=context))
        return response
    elif request.method == "POST":
        action.delete()
        response = HttpResponse(render_block_to_string('core/partials/action_table.html', 'action_table',
                                                       context=context))
        return response


def hx_new_action(request, event_id):
    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        # if the get method is used with this function the form will be cleared.
        event_id = request.GET['event']
        context['event'] = models.Event.objects.get(pk=event_id)
        context['actionform'] = forms.ActionForm(initial={'event': event_id})
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'action_form', context=context))
        return response
    elif request.method == "POST":
        action = None
        if 'id' in request.POST:
            action = models.Action.objects.get(pk=request.POST['id'])
            event_id = action.event.pk
            form = forms.ActionForm(request.POST, instance=action)
            event = action.event
        else:
            event_id = request.POST['event']
            event = models.Event.objects.get(pk=event_id)
            form = forms.ActionForm(request.POST, initial={'event': event_id})

        context['event'] = event

        if form.is_valid():
            action = form.save()
            # context['actionforms'] = [forms.ActionForm(instance=action) for action in event.actions.all()]
            context['actionform'] = forms.ActionForm(initial={'event': event_id})
            response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'action_form', context=context))
            response['HX-Trigger'] = 'update_actions'
            return response

        context['actionform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'action_form', context=context))
        return response


def hx_update_attachment(request, action_id):
    context = {}
    context.update(csrf(request))

    if 'reset' in request.GET:
        # I'm passing the event id to initialize the form through the 'action_id' variable
        # it's not stright forward, but the action form needs to maintain an event or the
        # next action won't know what event it should be attached to.
        form = forms.AttachmentForm(initial={'event': action_id})
        context['attachmentform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'attachments_form', context=context))
        return response
    else:
        attachment = models.InstrumentSensor.objects.get(pk=action_id)
        event = attachment.event
    context['event'] = event

    if request.method == "GET":
        form = forms.AttachmentForm(instance=attachment, initial={'event': event.pk})
        context['attachmentform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'attachments_form', context=context))
        return response
    elif request.method == "POST":
        attachment.delete()
        response = HttpResponse(render_block_to_string('core/partials/attachment_table.html', 'attachments_table',
                                                       context=context))
        return response


def hx_new_attachment(request):
    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        # if the get method is used with this function the form will be cleared.
        event_id = request.GET['event']
        context['event'] = models.Event.objects.get(pk=event_id)
        context['attachmentform'] = forms.AttachmentForm(initial={'event': event_id})
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'attachments_form', context=context))
        return response
    elif request.method == "POST":
        attachment = None
        if 'id' in request.POST:
            attachment = models.InstrumentSensor.objects.get(pk=request.POST['id'])
            event_id = attachment.event.pk
            form = forms.AttachmentForm(request.POST, instance=attachment)
            event = attachment.event
        else:
            event_id = request.POST['event']
            event = models.Event.objects.get(pk=event_id)
            form = forms.AttachmentForm(request.POST, initial={'event': event_id})

        context['event'] = event

        if form.is_valid():
            attachment = form.save()
            # context['actionforms'] = [forms.ActionForm(instance=action) for action in event.actions.all()]
            context['attachmentform'] = forms.AttachmentForm(initial={'event': event_id})
            response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'attachments_form', context=context))
            response['HX-Trigger'] = 'update_attachments'
            return response

        context['attachmentform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'attachments_form', context=context))
        return response


def hx_list_action(request, event_id, editable=False):
    event = models.Event.objects.get(pk=event_id)
    context = {'event': event, 'editable': editable}
    response = HttpResponse(render_block_to_string('core/partials/action_table.html', 'action_table', context=context))
    return response


def hx_list_attachment(request, event_id, editable=False):
    event = models.Event.objects.get(pk=event_id)
    context = {'event': event, 'editable': editable}
    response = HttpResponse(render_block_to_string('core/partials/attachment_table.html', 'attachments_table',
                                                   context=context))
    return response


def hx_list_event(request, mission_id):
    mission = models.Mission.objects.get(pk=mission_id)
    context = {'mission': mission}
    response = HttpResponse(render_block_to_string('core/partials/table_event.html', 'event_table',
                                                   context=context))
    return response
