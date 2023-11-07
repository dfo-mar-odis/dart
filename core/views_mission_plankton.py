import logging

from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

from core.parsers.PlanktonParser import parse_phytoplankton
from core.parsers.SampleParser import get_excel_dataframe
from core.views import MissionMixin
from core import forms

from dart2.views import GenericDetailView

debug_logger = logging.getLogger('dart.debug')
logger = logging.getLogger('dart')


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
    mission_id = kwargs['mission_id']

    if request.method == 'GET':
        # you can only get the file though a POST request
        url = reverse_lazy('core:load_plankton', args=(mission_id,))
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

            return HttpResponse(soup)

        post_card = forms.blank_alert(**attrs)
        message_div.append(post_card)
        return HttpResponse(soup)
    return HttpResponse("Hi")


def import_plankton(request, **kwargs):
    mission_id = kwargs['mission_id']

    if request.method == 'GET':
        # you can only get the file though a POST request
        url = reverse_lazy('core:import_plankton', args=(mission_id,))
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

            parse_phytoplankton(mission_id, file.name, dataframe)

            message_div.append(forms.blank_alert(**attrs))
            # clear the file input upon success
            input = soup.new_tag('input')
            input.attrs['id'] = "id_input_sample_file"
            input.attrs['class'] = "form-control form-control-sm"
            input.attrs['hx-swap-oob'] = "true"
            input.attrs['type'] = "file"
            input.attrs['name'] = "plankton_file"
            input.attrs['accept'] = ".xls,.xlsx,.xlsm"
            input.attrs['hx-trigger'] = "change"
            input.attrs['hx-get'] = reverse_lazy('core:load_plankton', args=(mission_id,))
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

        return HttpResponse(soup)
