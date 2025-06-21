from django.http import Http404
from django.urls import path
from django.utils.translation import gettext_lazy as _

from config import generic_views

from dart import models

from dart.forms.database_location_form import DatabaseLocationForm
from dart.forms.mission_settings_form import MissionSettingsForm
from dart.forms.mission_list_filter_form import MissionListFilterForm


class GenericMissionView(generic_views.GenericTemplateView):

    def get_page_title(self):
        mission = None
        if 'mission_id' in self.kwargs:
            mission = models.Mission.objects.get(pk=self.kwargs['mission_id'])
        return mission.name if mission else self.page_title


class MissionEvents(GenericMissionView):
    template_name = 'dart/mission_events.html'

    page_title = "Events"

    def get_context_data(self, **kwargs):
        if 'mission_id' not in kwargs:
            raise Http404(_("Mission ID is required."))

        context = super().get_context_data(**kwargs)
        context['wide_format'] = True
        context['object'] = models.Mission.objects.get(pk=int(kwargs.get('mission_id')))

        return context


class MissionSettings(GenericMissionView):
    template_name = 'dart/mission_settings.html'

    page_title = "Mission Metadata"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if 'mission_id' in kwargs:
            context['object'] = models.Mission.objects.get(pk=int(kwargs.get('mission_id')))
            context['mission_form'] = MissionSettingsForm(instance=context['object'])
        else:
            context['mission_form'] = MissionSettingsForm()

        return context


class MissionFilter(GenericMissionView):
    template_name = 'dart/mission_filter.html'

    page_title = "Mission Selection"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['location_form'] = DatabaseLocationForm()
        context['mission_form'] = MissionListFilterForm()
        context['missions'] = models.Mission.objects.all()

        return context


urlpatterns = [
    path("", MissionFilter.as_view(), name="mission_filter"),

    path("mission/new/", MissionSettings.as_view(), name="mission_new"),
    path("<str:database>/mission/<int:mission_id>/", MissionSettings.as_view(), name="mission_update"),

    path("<str:database>/mission/events/<int:mission_id>", MissionEvents.as_view(), name="mission_events"),
]