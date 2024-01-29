import csv
import os
from pathlib import Path
import logging

from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.conf import settings

from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django_pandas.io import read_frame

from core.parsers.PlanktonParser import parse_phytoplankton, parse_zooplankton
from core.parsers.SampleParser import get_excel_dataframe
from core.views import MissionMixin
from core import forms, form_biochem_database
from core import models

import biochem.upload
from biochem import models as biochem_models

from dart2.utils import load_svg

from dart2.views import GenericDetailView

debug_logger = logging.getLogger('dart.debug')
logger = logging.getLogger('dart')


class PlanktonDetails(MissionMixin, GenericDetailView):
    page_title = _("Mission Plankton")
    template_name = "core/mission_plankton.html"

    def get_upload_url(self):
        return reverse_lazy("core:mission_plankton_list_plankton", args=(self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mission'] = self.object
        return context

    def get_page_title(self):
        return _("Mission Plankton") + " : " + self.object.name


def load_plankton(request, **kwargs):
    mission_id = kwargs['mission_id']

    if request.method == 'GET':
        # you can only get the file though a POST request
        url = reverse_lazy('core:mission_plankton_load_plankton', args=(mission_id,))
        attrs = {
            'component_id': 'div_id_message',
            'message': _("Loading"),
            'alert_type': 'info',
            'hx-trigger': "load",
            'hx-swap-oob': 'true',
            'hx-post': url,
        }
        load_card = forms.save_load_component(**attrs)
        return HttpResponse(load_card)
    elif request.method == 'POST':

        soup = BeautifulSoup('', 'html.parser')

        message_div = soup.new_tag('div')
        message_div.attrs['class'] = "mt-2"
        message_div.attrs['id'] = "div_id_message"
        message_div.attrs['hx-swap-oob'] = "true"
        soup.append(message_div)

        form_div = soup.new_tag('div')
        form_div.attrs['class'] = "row"
        form_div.attrs['id'] = "div_id_plankton_form"
        form_div.attrs['hx-swap-oob'] = "true"
        soup.append(form_div)

        attrs = {
            'component_id': 'div_id_message_alert',
            'message': _("Success"),
            'alert_type': 'success',
            'hx-swap-oob': 'true',
        }
        if 'plankton_file' not in request.FILES:
            attrs['message'] = 'No file chosen'
            attrs['alert_type'] = 'warning'
            post_card = forms.blank_alert(**attrs)
            message_div.append(post_card)

            return HttpResponse(soup)

        file = request.FILES['plankton_file']

        #determine the file type
        debug_logger.debug(file)

        # the file can only be read once per request
        data = file.read()
        file_type: str = file.name.split('.')[-1].lower()

        if file_type.startswith('xls'):
            debug_logger.debug("Excel format detected")

            # because this is an excel format, we now need to know what tab and line the header
            # appears on to figure out if this is zoo or phyto plankton
            tab = int(request.POST['tab'] if 'tab' in request.POST else 1)
            tab = 1 if tab <= 0 else tab

            header = int(request.POST['header'] if 'header' in request.POST else -1)
            dict_vals = request.POST.copy()
            dict_vals['tab'] = tab
            dict_vals['header'] = header

            try:
                dataframe = get_excel_dataframe(stream=data, sheet_number=(tab-1), header_row=(header-1))
                start = dataframe.index.start if hasattr(dataframe.index, 'start') else 0
                dict_vals['header'] = max(start + 1, header)

                # If the file contains a 'What_was_it' column, then this is a zooplankton file.
                # problem is the column may be uppercase, lowercase, may be a mix, may contain spaces or
                # underscores and may or may not end with a question mark. It very typically is the last column,
                # unless a 'comment' column is present.

                table_html = dataframe.head(10).to_html()
                table_soup = BeautifulSoup(table_html, 'html.parser')
                table = table_soup.find('table')
                table.attrs['class'] = "table table-striped"

                table_div = soup.new_tag('div')
                table_div.attrs['class'] = 'vertical-scrollbar'
                table_div.append(table)
            except ValueError as e:
                logger.exception(e)
                attrs = {
                    'component_id': "div_id_plankton_table",
                    'alert_type': "danger",
                    'message': e.args[0]
                }
                table_div = forms.blank_alert(**attrs)

            form = forms.PlanktonForm(dict_vals, mission_id=mission_id)
            form_html = render_crispy_form(form)

            form_soup = BeautifulSoup(form_html, 'html.parser')
            form_soup.append(table_div)

            form_div.append(form_soup)

            response = HttpResponse(soup)

            return response

        post_card = forms.blank_alert(**attrs)
        message_div.append(post_card)
        return HttpResponse(soup)
    return HttpResponse("Hi")


def import_plankton(request, **kwargs):

    mission_id = kwargs['mission_id']

    if request.method == 'GET':
        # you can only get the file though a POST request
        url = reverse_lazy('core:mission_plankton_import_plankton', args=(mission_id,))
        component_id = "div_id_message"
        attrs = {
            'component_id': component_id,
            'message': _("Loading"),
            'alert_type': 'info',
            'hx-trigger': "load",
            'hx-swap-oob': 'true',
            'hx-post': url,
            'hx-ext': "ws",
            'ws-connect': f"/ws/biochem/notifications/{component_id}/"
        }
        load_card = forms.save_load_component(**attrs)

        return HttpResponse(load_card)
    elif request.method == 'POST':

        soup = BeautifulSoup('', 'html.parser')

        message_div = soup.new_tag('div')
        message_div.attrs['class'] = "mt-2"
        message_div.attrs['id'] = "div_id_message"
        message_div.attrs['hx-swap-oob'] = "true"
        soup.append(message_div)

        form_div = soup.new_tag('div')
        form_div.attrs['class'] = "row"
        form_div.attrs['id'] = "div_id_plankton_form"
        form_div.attrs['hx-swap-oob'] = "true"
        soup.append(form_div)

        attrs = {
            'component_id': 'div_id_message',
            'message': _("Success"),
            'alert_type': 'success',
            'hx-swap-oob': 'true',
        }

        if 'plankton_file' not in request.FILES:
            attrs['message'] = 'No file chosen'
            attrs['alert_type'] = 'warning'
            message_div.append(forms.blank_alert(**attrs))
            return HttpResponse(soup)

        file = request.FILES['plankton_file']

        # the file can only be read once per request
        data = file.read()
        file_type: str = file.name.split('.')[-1].lower()

        # because this is an excel format, we now need to know what tab and line the header
        # appears on to figure out if this is zoo or phyto plankton
        tab = int(request.POST['tab'])
        header = int(request.POST['header'])

        try:
            dataframe = get_excel_dataframe(stream=data, sheet_number=(tab - 1), header_row=(header - 1))
            dataframe.columns = map(str.upper, dataframe.columns)

            if 'WHAT_WAS_IT' in dataframe.columns:
                parse_zooplankton(mission_id, file.name, dataframe)
            else:
                parse_phytoplankton(mission_id, file.name, dataframe)

            if (errs := models.FileError.objects.filter(mission_id=mission_id,
                                                             file_name__iexact=file.name)).exists():
                # might as well add the list of issues while loading the file to the response so the
                # user knows what went wrong.
                attrs['message'] = _("Completed with issues")
                attrs['alert_type'] = 'warning'
                alert = forms.blank_alert(**attrs)
                ul = soup.new_tag('ul')
                ul.attrs['class'] = 'vertical-scrollbar-sm'
                for err in errs:
                    li = soup.new_tag('li')
                    li.string = err.message
                    ul.append(li)
                alert.find('div').find('div').append(ul)
            else:
                alert = forms.blank_alert(**attrs)

            message_div.append(alert)
            # clear the file input upon success
            input = soup.new_tag('input')
            input.attrs['id'] = "id_input_sample_file"
            input.attrs['class'] = "form-control form-control-sm"
            input.attrs['hx-swap-oob'] = "true"
            input.attrs['type'] = "file"
            input.attrs['name'] = "plankton_file"
            input.attrs['accept'] = ".xls,.xlsx,.xlsm"
            input.attrs['hx-trigger'] = "change"
            input.attrs['hx-get'] = reverse_lazy('core:mission_plankton_load_plankton', args=(mission_id,))
            input.attrs['hx-swap'] = "none"

            soup.append(input)
        except ValueError as e:
            logger.exception(e)
            attrs = {
                'component_id': "div_id_plankton_table",
                'alert_type': "danger",
                'message': e.args[0]
            }
            message_div.append(forms.blank_alert(**attrs))
        except Exception as e:
            logger.exception(e)
            attrs = {
                'component_id': "div_id_plankton_table",
                'alert_type': "danger",
                'message': _("An unknown issue occurred (see ./logs/error.log).")
            }
            message_div.append(forms.blank_alert(**attrs))

        response = HttpResponse(soup)
        response['HX-Trigger'] = 'update_samples'
        return response


def list_plankton(request, **kwargs):

    mission_id = kwargs['mission_id']

    soup = BeautifulSoup('', "html.parser")
    div = soup.new_tag('div')
    div.attrs['id'] = "div_id_plankton_data_table"
    div.attrs['hx-trigger'] = 'update_samples from:body'
    div.attrs['hx-get'] = reverse_lazy('core:mission_plankton_list_plankton', args=(mission_id,))
    soup.append(div)

    page = int(request.GET['page'] if 'page' in request.GET else 0)
    page_limit = 50
    page_start = page_limit * page

    samples = models.PlanktonSample.objects.filter(bottle__event__trip__mission_id=mission_id).order_by(
        'bottle__event__instrument__type', 'bottle__bottle_id'
    )
    if samples.exists():
        data_columns = ["Sample", "Pressure", "Station", "Type", "Name", "Sex", "Stage", "Split", "Count", "Wet", "Dry",
                        "Volume", "Percent", "Comments"]

        samples = samples.values("bottle__bottle_id", "bottle__pressure", 'bottle__event__station__name',
                                 "bottle__event__instrument__type", "taxa__taxonomic_name", "sex__name", "stage__name",
                                 "split_fraction", "count", "raw_wet_weight", "raw_dry_weight", "volume", "percent",
                                 "comments")
        samples = samples[page_start:(page_start + page_limit)]

        dataframe = read_frame(samples)
        dataframe.columns = data_columns
        dataframe.fillna('---', inplace=True)
        dataframe['Type'] = dataframe['Type'].map({1: "phyto", 2: "zoo"}, na_action='ignore')

        style = dataframe.style.hide(axis="index")

        table_html = style.to_html()
        table_soup = BeautifulSoup(table_html, 'html.parser')

        table = table_soup.find('table')

        table.attrs['class'] = 'dataframe table table-striped table-sm tscroll horizontal-scrollbar'

        last_tr = table.find('tbody').find_all('tr')[-1]
        last_tr.attrs['hx-trigger'] = 'intersect once'
        last_tr.attrs['hx-get'] = reverse_lazy('core:mission_plankton_list_plankton', args=(mission_id,)) + f"?page={page + 1}"
        last_tr.attrs['hx-swap'] = "afterend"

        div.append(table)
        if page > 0:
            return HttpResponse(table.find('tbody').find_all('tr'))

        return HttpResponse(soup)

    alert_attrs = {
        'component_id': 'div_id_plankton_data_table_alert',
        'alert_type': 'info',
        'message': _("No Plankton samples loaded")
    }
    alert_soup = forms.blank_alert(**alert_attrs)
    div.append(alert_soup)

    return HttpResponse(soup)


def get_plankton_db_card(request, **kwargs):
    mission_id = kwargs['mission_id']
    upload_url = reverse_lazy("core:mission_plankton_biochem_upload_plankton", args=(mission_id,))
    download_url = reverse_lazy("core:mission_plankton_download_plankton", args=(mission_id,))

    form_soup = form_biochem_database.get_database_connection_form(request, mission_id, upload_url, download_url)

    return HttpResponse(form_soup)


def upload_plankton(request, **kwargs):

    def upload_samples(mission: models.Mission, uploader: str):
        form_biochem_database.upload_bcs_p_data(mission, uploader)
        form_biochem_database.upload_bcd_p_data(mission, uploader)

    return form_biochem_database.upload_bio_chem(request, upload_samples, **kwargs)


def download_plankton(request, **kwargs):
    mission_id = kwargs['mission_id']

    soup = BeautifulSoup('', 'html.parser')
    div = soup.new_tag('div')
    div.attrs = {
        'id': "div_id_biochem_alert_biochem_db_details",
        'hx-swap-oob': 'true'
    }
    soup.append(div)

    def get_progress_alert():
        url = reverse_lazy("core:mission_plankton_download_plankton", args=(mission_id, ))
        message_component_id = 'div_id_upload_biochem'
        attrs = {
            'component_id': message_component_id,
            'alert_type': 'info',
            'message': _("Saving to file"),
            'hx-post': url,
            'hx-swap': 'none',
            'hx-trigger': 'load',
            'hx-target': "#div_id_biochem_alert_biochem_db_details",
            'hx-ext': "ws",
            'ws-connect': f"/ws/biochem/notifications/{message_component_id}/"
        }

        alert_soup = forms.save_load_component(**attrs)

        # add a message area for websockets
        msg_div = alert_soup.find(id="div_id_upload_biochem_message")
        msg_div.string = ""

        msg_div_status = soup.new_tag('div')
        msg_div_status['id'] = 'status'
        msg_div_status.string = _("Loading")
        msg_div.append(msg_div_status)

        return alert_soup

    if request.method == "GET":

        alert_soup = get_progress_alert()

        div.append(alert_soup)

        return HttpResponse(soup)

    has_uploader = 'uploader' in request.POST and request.POST['uploader']
    if 'uploader2' not in request.POST and not has_uploader:
        url = reverse_lazy("core:mission_plankton_download_plankton", args=(mission_id, ))
        message_component_id = 'div_id_upload_biochem'
        attrs = {
            'component_id': message_component_id,
            'alert_type': 'warning',
            'message': _("Require Uploader")
        }
        alert_soup = forms.blank_alert(**attrs)

        input_div = soup.new_tag('div')
        input_div['class'] = 'form-control input-group'

        input = soup.new_tag('input')
        input.attrs['id'] = 'input_id_uploader'
        input.attrs['type'] = "text"
        input.attrs['name'] = "uploader2"
        input.attrs['class'] = 'textinput form-control'
        input.attrs['maxlength'] = '20'
        input.attrs['placeholder'] = _("Uploader")

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

        input_div.append(input)
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

    mission = models.Mission.objects.get(pk=mission_id)
    plankton_samples = models.PlanktonSample.objects.filter(
        bottle__event__trip__mission=mission).values_list('pk', flat=True).distinct()
    bottles = models.Bottle.objects.filter(plankton_data__id__in=plankton_samples).distinct()

    # because we're not passing in a link to a database for the bcs_d_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create, update, fields = biochem.upload.get_bcs_p_rows(uploader=uploader, bottles=bottles)

    headers = [field.name for field in biochem_models.BcsPReportModel._meta.fields]

    file_name = f'{mission.name}_BCS_P.csv'
    path = os.path.join(settings.BASE_DIR, "reports")
    Path(path).mkdir(parents=True, exist_ok=True)

    try:
        with open(os.path.join(path, file_name), 'w', newline='', encoding="UTF8") as f:

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

    plankton_samples = models.PlanktonSample.objects.filter(bottle__event__trip__mission=mission)

    # because we're not passing in a link to a database for the bcd_p_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create, update, fields = biochem.upload.get_bcd_p_rows(uploader=uploader, samples=plankton_samples)

    headers = [field.name for field in biochem_models.BcdPReportModel._meta.fields]

    file_name = f'{mission.name}_BCD_P.csv'
    path = os.path.join(settings.BASE_DIR, "reports")
    Path(path).mkdir(parents=True, exist_ok=True)

    try:
        with open(os.path.join(path, file_name), 'w', newline='', encoding="UTF8") as f:

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


def clear_plankton(request, **kwargs):
    mission_id = kwargs['mission_id']

    if request.htmx:
        samples = models.PlanktonSample.objects.filter(bottle__event__trip__mission_id=mission_id)
        files = samples.values_list('file', flat=True).distinct()
        errors = models.FileError.objects.filter(mission_id=mission_id, file_name__in=files)
        errors.delete()
        samples.delete()

    response = HttpResponse()
    response['HX-Trigger'] = 'update_samples'

    return response


# ###### Plankton loading ###### #
url_prefix = "<str:database>/plankton"
plankton_urls = [
    path(f'{url_prefix}/<int:pk>/', PlanktonDetails.as_view(), name="mission_plankton_plankton_details"),
    path(f'plankton/load/<int:mission_id>/', load_plankton, name="mission_plankton_load_plankton"),
    path(f'plankton/import/<int:mission_id>/', import_plankton, name="mission_plankton_import_plankton"),
    path(f'plankton/list/<int:mission_id>/', list_plankton, name="mission_plankton_list_plankton"),
    path(f'plankton/db/<int:mission_id>/', get_plankton_db_card, name="mission_plankton_get_plankton_db_card"),
    path(f'plankton/biochem/upload/<int:mission_id>/', upload_plankton, name="mission_plankton_biochem_upload_plankton"),
    path(f'plankton/biochem/download/<int:mission_id>/', download_plankton, name="mission_plankton_download_plankton"),
    path(f'plankton/clear/<int:mission_id>/', clear_plankton, name="mission_plankton_clear"),
]
