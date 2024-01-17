from django.core.cache import caches
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core import forms, form_event_details, form_mission_trip
from core.views import MissionMixin, reports
from dart2.views import GenericDetailView


class EventDetails(MissionMixin, GenericDetailView):
    page_title = _("Missions Events")
    template_name = "core/mission_events.html"

    def get_page_title(self):
        return _("Mission Events") + " : " + self.object.name

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if caches['default'].touch('selected_event'):
            caches['default'].delete('selected_event')

        context['search_form'] = forms.MissionSearchForm(initial={'mission': self.object.pk})

        if 'trip_id' in self.kwargs:
            context['trip_id'] = self.kwargs['trip_id']
        elif self.object.trips.last():
            context['trip_id'] = self.object.trips.last().pk

        context['reports'] = {key: reverse_lazy(reports[key], args=(self.object.pk,)) for key in reports.keys()}

        return context


mission_event_urls = [
    path('mission/event/<int:pk>/', EventDetails.as_view(), name="mission_events_details"),
    path('mission/event/<int:pk>/<int:trip_id>/', EventDetails.as_view(), name="mission_events_details"),
] + form_mission_trip.trip_load_urls + form_event_details.event_detail_urls
