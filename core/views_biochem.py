
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core import form_biochem_mission_summary
from core.views import MissionMixin, reports
from config.views import GenericDetailView


class BiochemDetails(MissionMixin, GenericDetailView):
    page_title = _("Biochem")
    help_text = _("The Biochem page allows for managing biochem connections, checking out biochem tables and loading"
                  "BCS/BCD tables. This is not a replacement for the Biochem Loader application.")
    template_name = "core/Biochem.html"

    def get_page_title(self):
        return self.page_title + " : " + self.object.name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        database = context['database']

        context['reports'] = {key: reverse_lazy(reports[key], args=(self.object.pk,))
                              for key in reports.keys()}

        return context

path_prefix = '<str:database>/biochem'
urlpatterns = [
    path(f'{path_prefix}/<int:pk>', BiochemDetails.as_view(), name="biochem_details"),
] + form_biochem_mission_summary.urlpatterns
