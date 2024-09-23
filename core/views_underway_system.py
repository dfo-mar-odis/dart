from django.urls import path
from django.utils.translation import gettext as _

from core.views import MissionMixin
from dart.views import GenericDetailView


class UnderwaySystemView(MissionMixin, GenericDetailView):
    page_title = _("Mission Underway")
    template_name = "core/mission_underway.html"

    def get_page_title(self):
        return _("Mission Underway") + " : " + self.object.name


path_prefix = '<str:database>/underway'
underway_urls = [
    path(f'{path_prefix}/<int:pk>/', UnderwaySystemView.as_view(), name="underway_details"),
]
