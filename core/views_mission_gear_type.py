from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core import models, form_mission_gear_type
from core.form_mission_gear_type import GearTypeFilterForm
from config.views import GenericDetailView


class GearTypeDetails(GenericDetailView):
    model = models.Mission
    page_title = _("Gear Type")
    template_name = "core/mission_gear_type.html"

    def get_page_title(self):
        return _(
            "Mission Gear Type") + f" {models.InstrumentType(self.kwargs['instrument_type']).label}: {self.object.name}"

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['database'] = self.kwargs['database']
        context['mission'] = self.object
        context['instrument_type'] = models.InstrumentType(self.kwargs['instrument_type'])
        context['gear_type_filter_form'] = GearTypeFilterForm(mission_id=self.object.pk, instrument_type=context['instrument_type'])

        return context


# ###### Mission Sample ###### #
url_patterns = [
    path(f'<str:database>/geartype/<int:pk>/<int:instrument_type>/', GearTypeDetails.as_view(),
         name="mission_gear_type_details"),
]
url_patterns.extend(form_mission_gear_type.url_patterns)
