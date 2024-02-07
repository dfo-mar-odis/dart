import csv
import os
from pathlib import Path
import logging

from bs4 import BeautifulSoup
from django.conf import settings

from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core.form_plankton_load import list_plankton
from core.views import MissionMixin
from core import forms, form_biochem_database
from core import models

import biochem.upload
from biochem import models as biochem_models

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


def get_plankton_db_card(request, database, mission_id):
    upload_url = reverse_lazy("core:mission_plankton_biochem_upload_plankton", args=(database, mission_id,))
    download_url = reverse_lazy("core:mission_plankton_download_plankton", args=(database, mission_id,))

    form_soup = form_biochem_database.get_database_connection_form(request, database, mission_id,
                                                                   upload_url, download_url)

    return HttpResponse(form_soup)


def upload_plankton(request, database, mission_id):

    def upload_samples(mission: models.Mission, uploader: str):
        form_biochem_database.upload_bcs_p_data(mission, uploader)
        form_biochem_database.upload_bcd_p_data(mission, uploader)

    return form_biochem_database.upload_bio_chem(request, database, mission_id, upload_samples)


def download_plankton(request, database, mission_id):

    soup = BeautifulSoup('', 'html.parser')
    div = soup.new_tag('div')
    div.attrs = {
        'id': "div_id_biochem_alert_biochem_db_details",
        'hx-swap-oob': 'true'
    }
    soup.append(div)

    def get_progress_alert():
        progress_url = reverse_lazy("core:mission_plankton_download_plankton", args=(database, mission_id, ))
        progress_message_component_id = 'div_id_upload_biochem'
        msg_attrs = {
            'component_id': progress_message_component_id,
            'alert_type': 'info',
            'message': _("Saving to file"),
            'hx-post': progress_url,
            'hx-swap': 'none',
            'hx-trigger': 'load',
            'hx-target': "#div_id_biochem_alert_biochem_db_details",
            'hx-ext': "ws",
            'ws-connect': f"/ws/biochem/notifications/{progress_message_component_id}/"
        }

        msg_alert_soup = forms.save_load_component(**msg_attrs)

        # add a message area for websockets
        msg_div = msg_alert_soup.find(id="div_id_upload_biochem_message")
        msg_div.string = ""

        msg_div_status = soup.new_tag('div')
        msg_div_status['id'] = 'status'
        msg_div_status.string = _("Loading")
        msg_div.append(msg_div_status)

        return msg_alert_soup

    if request.method == "GET":

        alert_soup = get_progress_alert()

        div.append(alert_soup)

        return HttpResponse(soup)

    has_uploader = 'uploader' in request.POST and request.POST['uploader']
    if 'uploader2' not in request.POST and not has_uploader:
        url = reverse_lazy("core:mission_plankton_download_plankton", args=(database, mission_id, ))
        message_component_id = 'div_id_upload_biochem'
        attrs = {
            'component_id': message_component_id,
            'alert_type': 'warning',
            'message': _("Require Uploader")
        }
        alert_soup = forms.blank_alert(**attrs)

        input_div = soup.new_tag('div')
        input_div['class'] = 'form-control input-group'

        uploader_input = soup.new_tag('input')
        uploader_input.attrs['id'] = 'input_id_uploader'
        uploader_input.attrs['type'] = "text"
        uploader_input.attrs['name'] = "uploader2"
        uploader_input.attrs['class'] = 'textinput form-control'
        uploader_input.attrs['maxlength'] = '20'
        uploader_input.attrs['placeholder'] = _("Uploader")

        icon = BeautifulSoup(load_svg('check-square'), 'html.parser').svg

        submit = soup.new_tag('button')
        submit.attrs['class'] = 'btn btn-primary'
        submit.attrs['hx-post'] = url
        submit.attrs['id'] = 'input_id_uploader_btn_submit'
        submit.attrs['name'] = 'submit'
        submit.append(icon)

        icon = BeautifulSoup(load_svg('x-square'), 'html.parser').svg
        cancel = soup.new_tag('button')
        cancel.attrs['class'] = 'btn btn-danger'
        cancel.attrs['hx-post'] = url
        cancel.attrs['id'] = 'input_id_uploader_btn_cancel'
        cancel.attrs['name'] = 'cancel'
        cancel.append(icon)

        input_div.append(uploader_input)
        input_div.append(submit)
        input_div.append(cancel)

        msg = alert_soup.find(id='div_id_upload_biochem_message')
        msg.string = msg.string + " "
        msg.append(input_div)

        div.append(alert_soup)

        return HttpResponse(soup)
    elif request.htmx.trigger == 'input_id_uploader_btn_submit':
        alert_soup = get_progress_alert()
        # div_id_upload_biochem_message is the ID given to the component in the get_progress_alert() function
        message = alert_soup.find(id="div_id_upload_biochem")
        hidden = soup.new_tag("input")
        hidden.attrs['type'] = 'hidden'
        hidden.attrs['name'] = 'uploader2'
        hidden.attrs['value'] = request.POST['uploader2']
        message.append(hidden)

        div.append(alert_soup)
        return HttpResponse(soup)
    elif request.htmx.trigger == 'input_id_uploader_btn_cancel':
        return HttpResponse(soup)

    uploader = request.POST['uploader2'] if 'uploader2' in request.POST else \
        request.POST['uploader'] if 'uploader' in request.POST else "N/A"

    mission = models.Mission.objects.using(database).get(pk=mission_id)
    plankton_samples = models.PlanktonSample.objects.using(database).filter(
        bottle__event__trip__mission=mission).values_list('pk', flat=True).distinct()
    bottles = models.Bottle.objects.using(database).filter(plankton_data__id__in=plankton_samples).distinct()

    # because we're not passing in a link to a database for the bcs_d_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create, update, fields = biochem.upload.get_bcs_p_rows(uploader=uploader, bottles=bottles)

    headers = [field.name for field in biochem_models.BcsPReportModel._meta.fields]

    file_name = f'{mission.name}_BCS_P.csv'
    report_path = os.path.join(settings.BASE_DIR, "reports")
    Path(report_path).mkdir(parents=True, exist_ok=True)

    try:
        with open(os.path.join(report_path, file_name), 'w', newline='', encoding="UTF8") as f:

            writer = csv.writer(f)
            writer.writerow(headers)

            for bcs_row in create:
                row = []
                for header in headers:
                    val = getattr(bcs_row, header) if hasattr(bcs_row, header) else ''
                    row.append(val)

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

    plankton_samples = models.PlanktonSample.objects.using(database).filter(bottle__event__trip__mission=mission)

    # because we're not passing in a link to a database for the bcd_p_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create, update, fields = biochem.upload.get_bcd_p_rows(uploader=uploader, samples=plankton_samples)

    headers = [field.name for field in biochem_models.BcdPReportModel._meta.fields]

    file_name = f'{mission.name}_BCD_P.csv'
    report_path = os.path.join(settings.BASE_DIR, "reports")
    Path(report_path).mkdir(parents=True, exist_ok=True)

    try:
        with open(os.path.join(report_path, file_name), 'w', newline='', encoding="UTF8") as f:

            writer = csv.writer(f)
            writer.writerow(headers)

            for row_number, bcs_row in enumerate(create):
                row = []
                for header in headers:
                    if header == 'dis_data_num':
                        val = str(row_number+1)
                    else:
                        val = getattr(bcs_row, header) if hasattr(bcs_row, header) else ''
                    row.append(val)

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
        'message': _("Success - Reports saved at : ") + f'{path}',
    }
    alert_soup = forms.blank_alert(**attrs)

    div.append(alert_soup)

    return HttpResponse(soup)


def clear_plankton(request, database, mission_id):
    mission = models.Mission.objects.using(database).get(pk=mission_id)

    if request.method == 'POST':
        samples = models.PlanktonSample.objects.using(database).filter(bottle__event__trip__mission_id=mission_id)
        files = samples.values_list('file', flat=True).distinct()
        errors = mission.file_errors.filter(file_name__in=files)
        errors.delete()
        samples.delete()

    response = HttpResponse()
    response['HX-Trigger'] = 'update_samples'

    return response


# ###### Plankton loading ###### #
url_prefix = "<str:database>/plankton"
plankton_urls = [
    path(f'{url_prefix}/<int:pk>/', PlanktonDetails.as_view(), name="mission_plankton_plankton_details"),

    path(f'{url_prefix}/db/<int:mission_id>/', get_plankton_db_card, name="mission_plankton_get_plankton_db_card"),
    path(f'{url_prefix}/biochem/upload/<int:mission_id>/', upload_plankton,
         name="mission_plankton_biochem_upload_plankton"),
    path(f'{url_prefix}/biochem/download/<int:mission_id>/', download_plankton,
         name="mission_plankton_download_plankton"),
    path(f'{url_prefix}/clear/<int:mission_id>/', clear_plankton, name="mission_plankton_clear"),
]
