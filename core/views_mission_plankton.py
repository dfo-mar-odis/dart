import logging

from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.core.cache import caches
from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django_pandas.io import read_frame

import core.models
from core.parsers.PlanktonParser import parse_phytoplankton, parse_zooplankton
from core.parsers.SampleParser import get_excel_dataframe
from core.views import MissionMixin
from core import forms, form_biochem_database
from core.form_biochem_database import BiochemUploadForm

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

            if (errs := core.models.FileError.objects.filter(mission_id=mission_id,
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

    samples = core.models.PlanktonSample.objects.filter(bottle__event__mission_id=mission_id).order_by(
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
    url = reverse_lazy("core:mission_plankton_biochem_upload_plankton", args=(mission_id,))

    form_soup = form_biochem_database.get_database_connection_form(request, mission_id, url)

    return HttpResponse(form_soup)


def upload_plankton(request, **kwargs):

    def upload_samples(mission, database):
        uploader = database.uploader if database.uploader else database.account_name

        form_biochem_database.upload_bcs_p_data(mission, uploader)

    return form_biochem_database.upload_bio_chem(request, upload_samples, **kwargs)


def clear_plankton(request, **kwargs):
    mission_id = kwargs['mission_id']

    if request.htmx:
        samples = core.models.PlanktonSample.objects.filter(bottle__event__mission_id=mission_id)
        files = samples.values_list('file', flat=True).distinct()
        errors = core.models.FileError.objects.filter(mission_id=mission_id, file_name__in=files)
        errors.delete()
        samples.delete()

    response = HttpResponse()
    response['HX-Trigger'] = 'update_samples'

    return response


# ###### Plankton loading ###### #
plankton_urls = [
    path('plankton/<int:pk>/', PlanktonDetails.as_view(), name="mission_plankton_plankton_details"),
    path('plankton/load/<int:mission_id>/', load_plankton, name="mission_plankton_load_plankton"),
    path('plankton/import/<int:mission_id>/', import_plankton, name="mission_plankton_import_plankton"),
    path('plankton/list/<int:mission_id>/', list_plankton, name="mission_plankton_list_plankton"),
    path('plankton/db/<int:mission_id>/', get_plankton_db_card, name="mission_plankton_get_plankton_db_card"),
    path('plankton/biochem/<int:mission_id>/', upload_plankton, name="mission_plankton_biochem_upload_plankton"),
    path('plankton/clear/<int:mission_id>/', clear_plankton, name="mission_plankton_clear"),
]
