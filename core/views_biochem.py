
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core import form_biochem_mission_summary
from core.views import MissionMixin, reports
from config.views import GenericTemplateView


class BiochemDetails(GenericTemplateView):
    page_title = _("Biochem")
    help_text = _("The Biochem page allows for managing biochem connections, checking out biochem tables and loading"
                  "BCS/BCD tables. This is not a replacement for the Biochem Loader application.")
    template_name = "core/Biochem.html"

    def get_page_title(self):
        return self.page_title

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        return context

path_prefix = 'biochem'
urlpatterns = [
    path(f'{path_prefix}/', BiochemDetails.as_view(), name="biochem_details"),
] + form_biochem_mission_summary.urlpatterns
