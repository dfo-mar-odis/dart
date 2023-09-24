from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

from core.views import MissionMixin
from core import forms
from core import models as core_models

from dart2.views import GenericDetailView


class PlanktonDetails(MissionMixin, GenericDetailView):
    page_title = _("Mission Plankton")
    template_name = "core/mission_plankton.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mission'] = self.object
        return context

    def get_page_title(self):
        return _("Mission Plankton") + " : " + self.object.name


def load_plankton(request, **kwargs):

    if request.method == 'GET':
        mission_id = request.GET['mission_id']
        url = reverse_lazy('core:load_plankton',)
        attrs = {
            'component_id': 'div_id_plankton',
            'message': _("Loading"),
            'alert_type': 'info',
            'hx-trigger': "load",
            'hx-target': '#div_id_message',
            'hx-post': url,
        }
        load_card = forms.save_load_component(**attrs)
        return HttpResponse(load_card)
    elif request.method == 'POST':
        file = request.FILES['plankton_file']
        pass
    return HttpResponse("Hi")