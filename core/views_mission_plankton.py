import logging

from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

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

        attrs = {
            'component_id': 'div_id_message',
            'message': _("Success"),
            'alert_type': 'success',
            'hx-swap-oob': 'true',
        }
        if 'plankton_file' not in request.FILES:
            attrs['message'] = 'No file chosen'
            attrs['alert_type'] = 'warning'
            post_card = forms.blank_alert(**attrs)
            return HttpResponse(post_card)

        file = request.FILES['plankton_file']

        #determine the file type
        debug_logger.debug(file)

        # the file can only be read once per request
        data = file.read()
        file_type: str = file.name.split('.')[-1].lower()

        if file_type.startswith('xls'):
            debug_logger.debug("Excel format detected")
            soup = BeautifulSoup('<div class="mt-2" id="div_id_message" hx-swap-oob="true"></div>')

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

            soup.find(id="div_id_message").append(form_soup)

            return HttpResponse(soup)

        post_card = forms.blank_alert(**attrs)

        return HttpResponse(post_card)
    return HttpResponse("Hi")