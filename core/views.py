from bs4 import BeautifulSoup

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.urls import reverse_lazy

from biochem import models

from dart.views import GenericCreateView, GenericUpdateView, GenericDetailView
from dart import utils

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
    form_class = forms.MissionSettingsForm
    template_name = "core/mission_settings.html"

    def get_success_url(self):
        success = reverse_lazy("core:mission_events_details", args=(self.object.name, self.object.pk, ))
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
        return context


def hx_update_elog_config(request, database, mission_id):
    if request.method == "POST":
        dict_vals = request.POST.copy()
        mission = models.Mission.objects.using(database).get(pk=mission_id)

        config = elog.get_or_create_file_config()

        context = {'object': mission}
        html = render_to_string(template_name='core/mission_elog.html', context=context)
        soup = BeautifulSoup(html, 'html.parser')

        return HttpResponse(soup)
