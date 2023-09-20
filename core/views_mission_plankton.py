from django.utils.translation import gettext as _

from core.views import MissionMixin
from dart2.views import GenericDetailView


class PlanktonDetails(MissionMixin, GenericDetailView):
    page_title = _("Mission Plankton")
    template_name = "core/mission_plankton.html"

    def get_page_title(self):
        return _("Mission Plankton") + " : " + self.object.name