from bs4 import BeautifulSoup

from django.http import HttpResponse
from django.utils.translation import gettext as _
from django.urls import reverse_lazy
from render_block import render_block_to_string

import core.form_mission_settings
from biochem import models

from dart.views import GenericCreateView, GenericUpdateView, GenericDetailView

from core import forms, models
from core.parsers import elog

import logging

logger = logging.getLogger('dart')

reports = {
    "Chlorophyll Summary": "core:hx_report_chl",
    "Oxygen Summary": "core:hx_report_oxygen",
    "Salinity Summary": "core:hx_report_salt",
    "Profile Summary": "core:hx_report_profile",
    "Elog Report": "core:hx_report_elog",
    "Error Report": "core:hx_report_error",
}


class MissionMixin:
    model = models.Mission
    page_title = _("Missions")


class EventMixin:
    model = models.Event
    page_title = _("Event Details")


class MissionCreateView(MissionMixin, GenericCreateView):
    form_class = core.form_mission_settings.MissionSettingsForm
    template_name = "core/mission_settings.html"

    def get_success_url(self):
        database_name = f"DART_{self.object.name}"
        success = reverse_lazy("core:mission_events_details", args=(database_name, self.object.pk, ))
        return success


class MissionUpdateView(MissionCreateView, GenericUpdateView):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['database'] = self.kwargs['database']

        return context


class ElogDetails(GenericDetailView):
    template_name = 'core/mission_elog.html'
    page_title = _('Mission Elog Configuration')
    model = models.Mission

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['file_config'] = elog.get_or_create_file_config()
        return context


def hx_update_elog_config(request, database, mission_id):
    mission = models.Mission.objects.using(database).get(pk=mission_id)
    config = elog.get_or_create_file_config()

    context = {'database': database, 'object': mission}
    if request.method == "POST":
        key = [key for key in request.POST.keys()][0]
        mapping = config.get(required_field=key)
        mapping.mapped_field = request.POST[key]
        mapping.save()  # elog configs are part of the user settings so they save to the 'default' database
    else:
        key = [key for key in request.GET.keys()][0]
        mapping = config.get(required_field=key)
        if mapping.mapped_field != request.GET[key]:
            context['enabled'] = 'ture'
        context["mapping"] = mapping

    context["mapping"] = mapping
    html = render_block_to_string('core/mission_elog.html', "config_input", context)
    soup = BeautifulSoup(html, 'html.parser')

    return HttpResponse(soup)
