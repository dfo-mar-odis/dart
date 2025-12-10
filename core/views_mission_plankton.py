import logging

from bs4 import BeautifulSoup

from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core.views import MissionMixin
from core import models, forms, form_biochem_plankton, form_biochem_batch2_plankton

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

        context['biochem_batch_form'] = form_biochem_batch2_plankton.BiochemPlanktonBatchForm(mission_id=self.object.pk)

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


def biochem_batches_card(request, mission_id):

    # The first time we get into this function will be a GET request from the mission_samples.html template asking
    # to put the UI component on the web page.

    # The second time will be whenever a database is connected to or disconnected from which will be a POST
    # request that should update the Batch selection drop down and then fire a trigger to clear the tables

    soup = BeautifulSoup('', 'html.parser')
    form_soup = form_biochem_plankton.get_batches_form(request, mission_id)

    if request.method == "POST":
        batch_div = form_soup.find('div', {"id": "div_id_selected_batch"})
        batch_div.attrs['hx-swap-oob'] = 'true'
        soup.append(batch_div)
        response = HttpResponse(soup)
        response['HX-Trigger'] = 'clear_batch'
        return response

    soup.append(biochem_card_wrapper := soup.new_tag('div', id="div_id_biochem_batches_card_wrapper"))
    biochem_card_wrapper.attrs['class'] = "mb-2"
    biochem_card_wrapper.attrs['hx-trigger'] = 'biochem_db_connect from:body'
    biochem_card_wrapper.attrs['hx-post'] = request.path
    # the method to update the upload/download buttons on the biochem form will be hx-swap-oob
    biochem_card_wrapper.attrs['hx-swap'] = 'none'

    biochem_card_wrapper.append(form_soup)
    return HttpResponse(soup)


# ###### Plankton loading ###### #
plankton_urls = [
    path(f'<str:database>/plankton/<int:pk>/', PlanktonDetails.as_view(), name="mission_plankton_plankton_details"),

    path(f'plankton/plankton/batch/<int:mission_id>/', biochem_batches_card, name="mission_plankton_biochem_plankton_card"),
    path(f'plankton/clear/<int:mission_id>/', clear_plankton, name="mission_plankton_clear"),
]
