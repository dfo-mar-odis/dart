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
from core import models, forms, form_biochem_database

from biochem import models as biochem_models
from biochem import upload

from dart.utils import load_svg

from dart.views import GenericDetailView

debug_logger = logging.getLogger('dart.debug')
logger = logging.getLogger('dart')


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


def biochem_upload_card(request, database, mission_id):
    # upload_url = reverse_lazy("core:mission_samples_upload_bio_chem", args=(database, mission_id,))
    # download_url = reverse_lazy("core:mission_samples_download_bio_chem", args=(database, mission_id,))

    button_url = reverse_lazy('core:mission_plankton_update_biochem_buttons', args=(database, mission_id))

    soup = BeautifulSoup('', 'html.parser')
    soup.append(biochem_card_wrapper := soup.new_tag('div', id="div_id_biochem_card_wrapper"))
    biochem_card_wrapper.attrs['class'] = "mb-2"
    biochem_card_wrapper.attrs['hx-get'] = button_url
    biochem_card_wrapper.attrs['hx-trigger'] = 'load, biochem_db_update from:body'
    # the method to update the upload/download buttons on the biochem form will be hx-swap-oob
    biochem_card_wrapper.attrs['hx-swap'] = 'none'

    form_soup = form_biochem_database.get_database_connection_form(request, database, mission_id)
    biochem_card_wrapper.append(form_soup)

    return HttpResponse(soup)


def sample_data_upload(database, mission: models.Mission, uploader: str):
    # clear previous errors if there were any from the last upload attempt
    mission.errors.filter(type=models.ErrorType.biochem).delete()
    models.Error.objects.using(database).filter(mission=mission, type=models.ErrorType.biochem).delete()

    # send_user_notification_queue('biochem', _("Validating Sensor/Sample Datatypes"))
    # user_logger.info(_("Validating Sensor/Sample Datatypes"))
    samples_types_for_upload = [bcupload.type for bcupload in
                                models.BioChemUpload.objects.using(database).filter(type__mission=mission)]
    # errors = validation.validate_samples_for_biochem(mission=mission, sample_types=samples_types_for_upload)

    # if errors:
    #     # send_user_notification_queue('biochem', _("Datatypes missing see errors"))
    #     user_logger.info(_("Datatypes missing see errors"))
    #     models.Error.objects.using(database).bulk_create(errors)

    # create and upload the BCS data if it doesn't already exist
    form_biochem_database.upload_bcs_p_data(mission, uploader)
    form_biochem_database.upload_bcd_p_data(mission, uploader)


def upload_samples(request, database, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div := soup.new_tag('div'))
    div.attrs['id'] = "div_id_biochem_alert_biochem_db_details"
    div.attrs['hx-swap-oob'] = 'true'

    # are we connected?
    if not form_biochem_database.is_connected():
        alert_soup = forms.blank_alert("div_id_biochem_alert", _("Not Connected"), alert_type="danger")
        div.append(alert_soup)
        return HttpResponse(soup)

    # do we have an uploader?
    alert_soup = form_biochem_database.confirm_uploader(request)
    if alert_soup:
        div.append(alert_soup)
        return HttpResponse(soup)

    try:
        uploader = request.POST['uploader2'] if 'uploader2' in request.POST else \
            request.POST['uploader'] if 'uploader' in request.POST else "N/A"

        mission = models.Mission.objects.using(database).get(pk=mission_id)
        sample_data_upload(database, mission, uploader)
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'success',
            'message': _("Thank you for uploading"),
        }
    except Exception as e:
        logger.exception(e)
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': str(e),
        }

    alert_soup = forms.blank_alert(**attrs)
    div.append(alert_soup)
    return HttpResponse(soup)


def download_samples(request, database, mission_id):
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

    mission = models.Mission.objects.using(database).get(pk=mission_id)
    batch_name = f'{mission.start_date.strftime("%Y%m")}{mission.end_date.strftime("%Y%m")}'

    plankton_samples = models.PlanktonSample.objects.using(database).filter(
        bottle__event__mission=mission).values_list('pk', flat=True).distinct()
    bottles = models.Bottle.objects.using(database).filter(plankton_data__id__in=plankton_samples).distinct()

    # because we're not passing in a link to a database for the bcs_d_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create, update, fields = upload.get_bcs_p_rows(uploader=uploader, bottles=bottles,
                                                   batch_name=mission.get_batch_name)

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

    plankton_samples = models.PlanktonSample.objects.using(database).filter(bottle__event__mission=mission)

    # because we're not passing in a link to a database for the bcd_p_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create, update, fields = upload.get_bcd_p_rows(database=database, uploader=uploader, samples=plankton_samples,
                                                   batch_name=mission.get_batch_name)

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


def clear_plankton(request, database, mission_id):
    mission = models.Mission.objects.using(database).get(pk=mission_id)

    if request.method == 'POST':
        samples = models.PlanktonSample.objects.using(database).filter(bottle__event__mission_id=mission_id)
        files = samples.values_list('file', flat=True).distinct()
        errors = mission.file_errors.filter(file_name__in=files)
        errors.delete()
        samples.delete()

    response = HttpResponse()
    response['HX-Trigger'] = 'update_samples'

    return response


def get_biochem_buttons(request, database, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(button_area := soup.new_tag('div'))
    button_area.attrs['id'] = form_biochem_database.get_biochem_additional_button_id()
    button_area.attrs['class'] = 'col-auto align-self-center'
    button_area.attrs['hx-swap-oob'] = 'true'

    icon = BeautifulSoup(load_svg('arrow-down-square'), 'html.parser').svg
    button_area.append(download_button := soup.new_tag('button'))
    download_button.append(icon)
    download_button.attrs['class'] = 'btn btn-sm btn-primary'
    download_button.attrs['title'] = _("Build BCS/BCD Staging table CSV file")
    download_button.attrs['hx-get'] = reverse_lazy("core:mission_plankton_download_plankton",
                                                   args=(database, mission_id))
    download_button.attrs['hx-swap'] = 'none'

    icon = BeautifulSoup(load_svg('database-add'), 'html.parser').svg
    button_area.append(download_button := soup.new_tag('button'))
    download_button.append(icon)
    download_button.attrs['title'] = _("Upload Plankton data to Database")
    download_button.attrs['class'] = 'btn btn-sm btn-primary ms-2'
    download_button.attrs['hx-get'] = reverse_lazy("core:mission_plankton_biochem_upload_plankton",
                                                   args=(database, mission_id))
    download_button.attrs['hx-swap'] = 'none'

    return HttpResponse(soup)


# ###### Plankton loading ###### #
url_prefix = "<str:database>/plankton"
plankton_urls = [
    path(f'{url_prefix}/<int:pk>/', PlanktonDetails.as_view(), name="mission_plankton_plankton_details"),

    path(f'{url_prefix}/db/<int:mission_id>/', biochem_upload_card, name="mission_plankton_get_plankton_db_card"),

    path(f'{url_prefix}/upload/<int:mission_id>/', upload_samples,name="mission_plankton_biochem_upload_plankton"),
    path(f'{url_prefix}/download/<int:mission_id>/', download_samples, name="mission_plankton_download_plankton"),
    path(f'{url_prefix}/clear/<int:mission_id>/', clear_plankton, name="mission_plankton_clear"),

    path(f'{url_prefix}/biochem/<int:mission_id>/', get_biochem_buttons,
         name="mission_plankton_update_biochem_buttons"),
]
