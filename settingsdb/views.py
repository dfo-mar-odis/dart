from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from render_block import render_block_to_string

from core import models
from settingsdb import filters

from dart2.views import GenericTemplateView


def get_mission_dictionary():
    # this method presumes the databases were loaded by the settingsdb app.py ready function, but we may want to just
    # list available databases and then not load, run migrations and update fixtures until a user actually opens the
    # database. By using the app.py ready function we'll be running migrations and installing fixtures on possibly
    # dozens of databases every time the dart application starts.
    missions = {}
    keys = [key for key in settings.DATABASES.keys() if key != 'default']
    for key in keys:
        missions[key] = models.Mission.objects.using(key).first()

    return missions


class MissionFilterView(GenericTemplateView):
    model = models.Mission
    page_title = _("Mission")
    template_name = 'settingsdb/mission_filter.html'

    filterset_class = filters.MissionFilter
    new_url = reverse_lazy("core:mission_new")
    home_url = ""
    fields = ["id", "name", "biochem_table"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['new_url'] = self.new_url

        context['missions'] = get_mission_dictionary()

        return context


def list_missions(request):
    context = {'missions': get_mission_dictionary()}
    html = render_block_to_string('settingsdb/mission_filter.html', 'mission_table_block', context)
    response = HttpResponse(html)

    return response
