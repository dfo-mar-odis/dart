import logging

from bs4 import BeautifulSoup

from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core.views import MissionMixin
from core import models, forms, form_biochem_batch_plankton

from config.views import GenericDetailView

debug_logger = logging.getLogger('dart.debug')
logger = logging.getLogger('dart')
user_logger = logger.getChild('user')


class PlanktonDetails(MissionMixin, GenericDetailView):
    page_title = _("Mission Plankton")
    template_name = "core/mission_plankton.html"

    def get_upload_url(self):
        return reverse_lazy("core:form_plankton_list_plankton", args=(self.kwargs['database'], self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mission'] = self.object
        context['database'] = self.kwargs['database']

        context['biochem_batch_form'] = form_biochem_batch_plankton.BiochemPlanktonBatchForm(mission_id=self.object.pk)

        return context

    def get_page_title(self):
        return _("Mission Plankton") + " : " + self.object.name


def clear_plankton(request, mission_id):
    mission = models.Mission.objects.get(pk=mission_id)

    soup = BeautifulSoup('', 'html.parser')

    alert_id = "div_id_plankton_db_details"
    if request.method == 'GET':
        alert_attrs = {
            "component_id": alert_id,
            "alerty_type": "info",
            "message": _("Deleting Plankton Samples"),
            "hx-post": request.path,
            "hx-trigger": "load",
            "hx-swap-oob": "true",
        }
        alert = forms.save_load_component(**alert_attrs)
        soup.append(alert)
        return HttpResponse(soup)

    nets = models.Bottle.objects.filter(event__mission_id=mission_id, event__instrument__type=models.InstrumentType.net)
    samples = models.PlanktonSample.objects.filter(bottle__in=nets)
    files = samples.values_list('file', flat=True).distinct()
    errors = mission.file_errors.filter(file_name__in=files)
    errors.delete()
    samples.delete()
    nets.delete()

    soup.append(alert_row := soup.new_tag("div"))
    alert_row.attrs['class'] = "row"
    alert_row.attrs['id'] = alert_id
    alert_row.attrs['hx-swap-oob'] = "true"

    response = HttpResponse(soup)
    response['HX-Trigger'] = 'update_samples'

    return response


# ###### Plankton loading ###### #
plankton_urls = [
    path(f'<str:database>/plankton/<int:pk>/', PlanktonDetails.as_view(), name="mission_plankton_plankton_details"),
    path(f'plankton/clear/<int:mission_id>/', clear_plankton, name="mission_plankton_clear"),
]
