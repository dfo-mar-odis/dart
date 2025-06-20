import csv
import os
from pathlib import Path
import logging

from bs4 import BeautifulSoup
from django.conf import settings

from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core.views import MissionMixin
from core import models, forms, form_biochem_database, form_biochem_plankton
from core.form_biochem_batch import get_mission_batch_id

from biochem import models as biochem_models
from biochem import upload

from config.utils import load_svg

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
        return context

    def get_page_title(self):
        return _("Mission Plankton") + " : " + self.object.name

def download_samples(request, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    div = soup.new_tag('div')
    div.attrs = {
        'id': "div_id_biochem_alert_biochem_db_details",
        'hx-swap-oob': 'true'
    }
    soup.append(div)

    alert_soup = form_biochem_database.confirm_uploader(request)
    if alert_soup:
        div.append(alert_soup)
        return HttpResponse(soup)

    uploader = request.POST['uploader2'] if 'uploader2' in request.POST else \
        request.POST['uploader'] if 'uploader' in request.POST else "N/A"

    mission = models.Mission.objects.get(pk=mission_id)

    plankton_samples = models.PlanktonSample.objects.filter(
        bottle__event__mission=mission).values_list('pk', flat=True).distinct()
    bottles = models.Bottle.objects.filter(plankton_data__id__in=plankton_samples).distinct()

    # because we're not passing in a link to a database for the bcs_d_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create = upload.get_bcs_p_rows(uploader=uploader, bottles=bottles)

    bcs_headers = [field.name for field in biochem_models.BcsPReportModel._meta.fields]

    file_name = f'{mission.name}_BCS_P.csv'
    report_path = os.path.join(settings.BASE_DIR, "reports")
    Path(report_path).mkdir(parents=True, exist_ok=True)

    try:
        with open(os.path.join(report_path, file_name), 'w', newline='', encoding="UTF8") as f:

            writer = csv.writer(f)
            writer.writerow(bcs_headers)

            for bcs_row in create:
                row = [getattr(bcs_row, header, '') for header in bcs_headers]
                writer.writerow(row)
    except PermissionError:
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': _("Could not save report, the file may be opened and/or locked"),
        }
        alert_soup = forms.blank_alert(**attrs)
        div.append(alert_soup)

        return HttpResponse(soup)

    plankton_samples = models.PlanktonSample.objects.filter(bottle__event__mission=mission)

    # because we're not passing in a link to a database for the bcd_p_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create = upload.get_bcd_p_rows(uploader=uploader, samples=plankton_samples)

    bcd_headers = [field.name for field in biochem_models.BcdPReportModel._meta.fields]

    file_name = f'{mission.name}_BCD_P.csv'
    report_path = os.path.join(settings.BASE_DIR, "reports")
    Path(report_path).mkdir(parents=True, exist_ok=True)

    try:
        with open(os.path.join(report_path, file_name), 'w', newline='', encoding="UTF8") as f:

            writer = csv.writer(f)
            writer.writerow(bcd_headers)

            for idx, bcs_row in enumerate(create):
                row = [str(idx + 1) if header == 'dis_data_num' else getattr(bcs_row, header, '')
                       for header in bcd_headers]
                writer.writerow(row)
    except PermissionError:
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': _("Could not save report, the file may be opened and/or locked"),
        }
        alert_soup = forms.blank_alert(**attrs)
        div.append(alert_soup)

        return HttpResponse(soup)

    attrs = {
        'component_id': 'div_id_upload_biochem',
        'alert_type': 'success',
        'message': _("Success - Reports saved at : ") + f'{report_path}',
    }
    alert_soup = forms.blank_alert(**attrs)

    div.append(alert_soup)

    return HttpResponse(soup)


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


def get_download_bcs_bcd_button(soup, mission_id):
    icon = BeautifulSoup(load_svg('arrow-down-square'), 'html.parser').svg
    button = soup.new_tag('button')
    button.append(icon)
    button.attrs['class'] = 'btn btn-sm btn-primary ms-2'
    button.attrs['title'] = _("Build BCS/BCD Staging table CSV file")
    button.attrs['hx-get'] = reverse_lazy("core:mission_plankton_download_plankton", args=(mission_id,))
    button.attrs['hx-swap'] = 'none'

    return button


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

    path(f'plankton/download/<int:mission_id>/', download_samples, name="mission_plankton_download_plankton"),
    path(f'plankton/clear/<int:mission_id>/', clear_plankton, name="mission_plankton_clear"),
]
