from django.utils.translation import gettext as _
from django.urls import reverse_lazy

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
    form_class = forms.EventForm
    template_name = "core/event_settings.html"

    def get_success_url(self):
        success = reverse_lazy("core:event_edit", args=(self.object.pk, ))
        return success

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)

        return data

    def get_initial(self):
        initial = super().get_initial()
        if 'mission_id' in self.kwargs:
            mission_id = self.kwargs['mission_id']
            mission = models.Mission.objects.get(pk=mission_id)
            initial['mission'] = mission

            event_id = 1
            event = mission.events.order_by("event_id").last()
            if event:
                event_id = event.event_id + 1

            initial['event_id'] = event_id

        return initial

    def form_valid(self, form):
        data = super().form_valid(form)
        return data


class EventUpdateView(EventCreateView, GenericUpdateView):
    pass

