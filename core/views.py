from bs4 import BeautifulSoup
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.urls import reverse_lazy

from biochem import models
from dart2.views import GenericFlilterMixin, GenericCreateView, GenericUpdateView, GenericDetailView
from dart2 import utils

from core import forms, filters, models

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


class MissionFilterView(MissionMixin, GenericFlilterMixin):
    filterset_class = filters.MissionFilter
    new_url = reverse_lazy("core:mission_new")
    home_url = ""
    fields = ["id", "name", "biochem_table"]


class MissionCreateView(MissionMixin, GenericCreateView):
    form_class = forms.MissionSettingsForm
    template_name = "core/mission_settings.html"

    def get_success_url(self):
        success = reverse_lazy("core:mission_events_details", args=(self.object.pk, ))
        return success


class MissionUpdateView(MissionCreateView, GenericUpdateView):
    pass


class ElogDetails(GenericDetailView):
    template_name = 'core/mission_elog.html'
    page_title = _('Mission Elog Configuration')
    model = models.Mission

    def get_context_data(self, **kwargs):
        if not hasattr(self.object, 'elogconfig'):
            models.ElogConfig.get_default_config(self.object)

        context = super().get_context_data(**kwargs)
        return context


def hx_update_elog_config(request, **kwargs):
    if request.method == "POST":
        dict_vals = request.POST.copy()
        mission = models.Mission.objects.get(pk=kwargs['mission_id'])

        config = models.ElogConfig.get_default_config(mission)
        update_models = {'fields': set(), 'models': []}
        for field_name, map_value in dict_vals.items():
            mapping = config.mappings.filter(field=field_name)
            if mapping.exists():
                mapping = mapping[0]
                updated = utils.updated_value(mapping, 'mapped_to', map_value)
                if updated:
                    update_models['models'].append(mapping)

        if len(update_models['models']) > 0:
            models.FileConfigurationMapping.objects.bulk_update(update_models['models'], ['mapped_to'])

        config.save()
        context = {'object': mission}
        html = render_to_string(template_name='core/mission_elog.html', context=context)
        soup = BeautifulSoup(html, 'html.parser')
        for mapping in update_models['models']:
            input = soup.find(id=f'mapping_{mapping.id}')
            input.attrs['class'].append("bg-success-subtle")

        return HttpResponse(soup)