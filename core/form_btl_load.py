import os
import queue
import time
import ctypes
import easygui

import concurrent.futures

from bs4 import BeautifulSoup

from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Column, Row, Div, Field
from crispy_forms.utils import render_crispy_form

from django import forms
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

import core.forms
from core import models
from core.parsers import ctd
from core.forms import CollapsableCardForm
from config.utils import load_svg

import logging

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')

# This queue is used for processing sample files in the sample_upload_ctd function
sample_file_queue = queue.Queue()


class BottleLoadForm(CollapsableCardForm):
    dir_field = forms.CharField(required=True)
    files = forms.MultipleChoiceField(choices=[], required=False)
    hide_loaded = forms.BooleanField(required=False)

    open_folder_url = None

    # I had to override the default Bootstrap template for fields, because someone thought putting 'mb-3'
    # as a default for field wrappers was a good idea and it creates a massive gap under the inputs when
    # used in a card title
    field_template = os.path.join(settings.TEMPLATE_DIR, "field.html")

    def get_open_folder_url(self):
        return self.open_folder_url

    def get_open_folder_btn(self):
        # url = reverse_lazy('core:mission_samples_upload_biochem', args=(self.mission_id,))
        button_icon = load_svg('folder-symlink')
        button_id = f'btn_id_load_{self.card_name}'
        button_attrs = {
            'id': button_id,
            'name': 'change_dir',
            'title': _("Select BTL directory"),
            'hx-get': self.get_open_folder_url(),
            'hx-swap': 'outerHTML',
            'hx-target': f"#{self.get_card_id()}",
        }
        upload_button = StrictButton(button_icon, css_class='btn btn-sm btn-secondary', **button_attrs)

        upload_field = Column(
            upload_button,
            css_class="col-auto"
        )

        return upload_field

    def get_alert_area(self):
        msg_row = Row(id=f"div_id_alert_{self.card_name}")
        return msg_row

    def get_refresh_url(self, hide_loaded: bool = False):
        url = reverse_lazy("core:form_btl_reload_files", args=(self.mission.pk,))
        if hide_loaded:
            url += '?hide_loaded=true'

        return url

    def get_card_header(self):
        header = super().get_card_header()

        url = reverse_lazy("core:form_btl_choose_bottle_dir", args=(self.mission.pk,))
        button_icon = load_svg('arrow-clockwise')
        button_attrs = {
            'id': f"{self.card_name}_refresh_files",
            'name': 'reload',
            'title': _("Refresh files in directory"),
            'hx-post': url,
            'hx-swap': 'outerHTML',
            'hx-target': f"#{self.get_card_id()}",
            'value': "true"
        }
        refresh_button = StrictButton(
            button_icon, **button_attrs, css_class="btn btn-secondary btn-sm"
        )

        dir_input = Column(
            Div(
                Field("dir_field", template=self.field_template,
                      css_class="input-group-sm form-control form-control-sm",
                      wrapper_class="d-flex flex-fill"
                      ),
                refresh_button,
                css_class="input-group",
                id=f"{self.card_name}_dir_field"
            ),
            css_class="col"
        )

        header.fields[0].append(self.get_open_folder_btn())
        header.fields[0].append(dir_input)

        header.fields.append(self.get_alert_area())
        return header

    def get_card_body(self):
        body = super().get_card_body()

        load_icon = load_svg("arrow-down-square")
        url = reverse_lazy("core:form_btl_upload_bottles", args=(self.mission.pk,))
        load_attrs = {
            'id': f"{self.card_name}_load_bottles",
            'hx-get': url,
            'hx-swap': 'none'
        }
        load_btn = StrictButton(load_icon, css_class="btn btn-primary btn-sm mb-2", **load_attrs)

        view_attrs = {
            'id': f"{self.card_name}_hide_loaded",
            'hx-get': self.get_refresh_url('hide_loaded' not in self.initial),
            'hx-swap': 'outerHTML',
            'hx-target': f"#{self.get_card_id()}",
        }
        if 'hide_loaded' in self.initial:
            view_icon = load_svg("eye-slash")
        else:
            view_icon = load_svg("eye")

        view_btn = StrictButton(view_icon, css_class="btn btn-primary btn-sm mb-2", **view_attrs)

        button_row = Row(
            Column(load_btn, css_class="col-auto"),
            Column(view_btn, css_class="col-auto"),
            css_class="justify-content-between"
        )

        body.fields.append(button_row)
        body.fields.append(Field("files"))
        body.fields.append(Field('hide_loaded', type="hidden"))
        return body

    def __init__(self, mission, *args, **kwargs):

        self.mission = mission

        self.open_folder_url = reverse_lazy('core:form_btl_choose_bottle_dir', args=(self.mission.pk,))
        super().__init__(card_name="bottle_load", card_title=_("Load Bottles"), *args, **kwargs)

        self.fields['dir_field'].label = False
        self.fields['files'].label = False
        self.initial['dir_field'] = mission.bottle_directory

        if mission.bottle_directory:
            try:
                files = [f for f in os.listdir(mission.bottle_directory) if f.upper().endswith('.BTL')]
                if 'hide_loaded' in self.initial:
                    loaded_files = [f.upper() for f in models.Sample.objects.filter(
                        type__is_sensor=True,
                        bottle__event__mission=self.mission).values_list('file', flat=True).distinct()]
                    files = [f for f in files if f.upper() not in loaded_files]

                files.sort(key=lambda fn: os.path.getmtime(os.path.join(mission.bottle_directory, fn)))

                self.fields['files'].choices = [(file, file) for file in files]
                self.initial['files'] = [file for file in files]
            except FileNotFoundError:
                logger.warning("directory does not exist")
                mission.bottle_directory = None
                mission.save()
                self.initial['dir_field'] = mission.bottle_directory


def get_bottle_load_card(request, mission_id, **kwargs):
    context = {}

    initial = {}
    if 'hide_loaded' in request.GET:
        initial = {'hide_loaded': "true"}

    collapsed = False if 'collapsed' in kwargs else True
    mission = models.Mission.objects.get(pk=mission_id)
    bottle_load_form = BottleLoadForm(mission=mission, collapsed=collapsed, initial=initial)
    bottle_load_html = render_crispy_form(bottle_load_form, context=context)
    bottle_load_soup = BeautifulSoup(bottle_load_html, 'html.parser')

    if (errors := mission.file_errors.filter(file_name__icontains='BTL')).exists():
        dir_input = bottle_load_soup.find(id=bottle_load_form.get_card_header_id())
        dir_input.attrs['class'].append("text-bg-warning")

        form_body = bottle_load_soup.find(id=bottle_load_form.get_card_body_id())

        btl_error_form = CollapsableCardForm(card_name="bottle_file_errors", card_title=_("Bottle File Errors"))
        btl_errors_html = render_crispy_form(btl_error_form)
        btl_errors_soup = BeautifulSoup(btl_errors_html, 'html.parser')
        btl_errors_soup.find("div").attrs['class'].append("mt-2")

        body = btl_errors_soup.find(id=btl_error_form.get_card_body_id())

        files = errors.values_list('file_name', flat=True).distinct()
        for index, file in enumerate(files):
            body.append(card := bottle_load_soup.new_tag('div', attrs={'class': 'card',
                                                                       'id': f'div_id_card_file_validation_{index}'}))
            card.append(card_header := bottle_load_soup.new_tag('div', attrs={'class': 'card-header'}))
            card_header.append(card_title := bottle_load_soup.new_tag('div', attrs={'class': 'card-title'}))
            card_title.append(title := bottle_load_soup.new_tag('h6'))
            title.string = str(file)

            card.append(card_body := bottle_load_soup.new_tag('div', attrs={'class': 'card-body'}))
            card_body.append(ul_file := bottle_load_soup.new_tag('ul', attrs={'class': 'list-group'}))
            for error in errors.filter(file_name=file):
                li_error_id = f'li_id_btl_error_{error.pk}'
                ul_file.append(li_error := bottle_load_soup.new_tag('li', attrs={'class': 'list-group-item',
                                                                                 'id': li_error_id}))
                li_error.append(div_row := bottle_load_soup.new_tag('div', attrs={'class': "row"}))
                div_row.append(div := bottle_load_soup.new_tag('div', attrs={'class': "col"}))
                div.string = error.message

                button_attrs = {
                    'class': "btn btn-danger btn-sm col-auto",
                    'hx-delete': reverse_lazy('core:mission_event_delete_log_file_error', args=(error.pk, index,)),
                    'hx-target': f"#{li_error_id}",
                    'hx-confirm': _("Are you Sure?"),
                    'hx-swap': 'delete'
                }
                div_row.append(button := bottle_load_soup.new_tag('button', attrs=button_attrs))
                button.append(BeautifulSoup(load_svg('x-square'), "html.parser").svg)

        form_body.append(btl_errors_soup)

    return bottle_load_soup


def bottle_load_card(request, mission_id, **kwargs):
    bottle_load_soup = get_bottle_load_card(request, mission_id, **kwargs)
    first_elm = bottle_load_soup.find(recursive=False)
    form_id = first_elm.attrs['id']
    form_soup = BeautifulSoup(f'<form id="form_id_{form_id}"></form>', 'html.parser')
    form = form_soup.find('form')
    form.append(bottle_load_soup)

    return HttpResponse(form_soup)


def load_ctd_file(ctd_mission: models.Mission, ctd_file):
    bottle_dir = ctd_mission.bottle_directory
    status = 'Success'
    # group_name = 'mission_events'

    ctd.logger_notifications.info(f"Loading file {ctd_file}")

    ctd_file_path = os.path.join(bottle_dir, ctd_file)
    try:
        ctd.read_btl(ctd_mission, ctd_file_path)
    except Exception as ctd_ex:
        logger.exception(ctd_ex)
        status = "Fail"

    # update the user on our progress
    return status


def load_ctd_files(mission):
    time.sleep(2)  # brief pause and wait for the websocket to initialize

    logger.level = logging.DEBUG
    group_name = 'mission_events'

    jobs = {}
    completed = []
    total_jobs = 0
    max_jobs = 2

    def load_ctd_file(ctd_mission: models.Mission, ctd_file):
        bottle_dir = ctd_mission.bottle_directory
        status = 'Success'
        # group_name = 'mission_events'

        ctd.logger_notifications.info(f"Loading file {ctd_file}")

        ctd_file_path = os.path.join(bottle_dir, ctd_file)
        try:
            ctd.read_btl(ctd_mission, ctd_file_path)
        except Exception as ctd_ex:
            logger.exception(ctd_ex)
            status = "Fail"

        completed.append(ctd_file)

        processed = 0
        if total_jobs > 0:
            processed = (len(completed) / total_jobs) * 100.0
            processed = str(round(processed, 2))

        ctd.logger_notifications.info(f"Loaded %d/%d", len(completed), total_jobs)

        # update the user on our progress
        return status

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_jobs) as executor:
        while True:
            while not sample_file_queue.empty():
                args = sample_file_queue.get()
                jobs[executor.submit(load_ctd_file, *args)] = args[1]  # args[1] is the file name to be processed
                total_jobs += 1

            done, not_done = concurrent.futures.wait(jobs, timeout=1)

            # remove jobs from the job queue if they've been completed
            for future in done:

                file = jobs[future]
                try:
                    results = future.result()
                except Exception as ex:
                    logger.exception(ex)

                del jobs[future]

            if len(jobs) <= 0 and sample_file_queue.empty() and len(not_done) <= 0:
                break

    ctd.logger_notifications.info(f"Complete")


def force_foreground_window():
    # Give system time to create the dialog
    time.sleep(0.25)
    # Get the foreground window handle
    dialog_title = _("Choose BTL directory")
    hwnd = ctypes.windll.user32.FindWindowW(None, dialog_title)

    if hwnd:
        # Try more aggressive techniques to force to front
        # This combination works better for dialog windows
        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
        ctypes.windll.user32.BringWindowToTop(hwnd)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.FlashWindow(hwnd, True)
    else:
        # Fall back to the original method if we can't find by title
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.FlashWindow(hwnd, True)


def diropenbox_on_top(*args, **kwargs):
    import platform

    # For Windows, use the dialog-forcing approach
    if platform.system() == 'Windows':
        # Start the dialog in a way that allows us to force it to the top
        result = None
        import threading
        threading.Timer(0.2, force_foreground_window).start()
        result = easygui.diropenbox(*args, **kwargs)
        return result
    else:
        # For non-Windows platforms, just use the standard dialog
        return easygui.diropenbox(*args, **kwargs)


def choose_bottle_dir(request, mission_id, **kwargs):
    mission = models.Mission.objects.get(pk=mission_id)
    if request.method == "POST" and 'dir_field' in request.POST:
        result = request.POST['dir_field']
    else:
        result = diropenbox_on_top(title=_("Choose BTL directory"))

    if result:
        mission.bottle_directory = result
        mission.save()

    return reload_files(request, mission_id, **kwargs)


def reload_files(request, mission_id, **kwargs):
    soup = get_bottle_load_card(request, mission_id, collapsed=False, **kwargs)
    response = HttpResponse(soup)
    response['HX-Trigger'] = 'update_samples, file_errors_updated'
    return response


def upload_btl_files(request, mission_id, **kwargs):
    mission = models.Mission.objects.get(pk=mission_id)

    thread_name = "load_ctd_files"

    if request.method == "GET":
        attrs = {
            'alert_area_id': "div_id_alert_bottle_load",
            'message': _("Loading Bottles"),
            'logger': ctd.logger_notifications.name,
            'hx-post': reverse_lazy("core:form_btl_upload_bottles", args=(mission_id,)),
            'hx-trigger': 'load'
        }
        alert = core.forms.websocket_post_request_alert(**attrs)
        response = HttpResponse(alert)
        return response
    else:
        files = request.POST.getlist('files')
        counts = len(files)
        for item, file in enumerate(files):
            ctd.logger_notifications.info("Processing file %d/%d", item, counts)
            load_ctd_file(mission, file)

        soup = get_bottle_load_card(request, mission_id, collapsed=False, **kwargs)

        reload_url = reverse_lazy('core:form_btl_reload_files', args=(mission_id,)) + "?hide_loaded=true"
        alert = core.forms.blank_alert(component_id="div_id_alert_bottle_load", message="Done", alert_type="success")
        div = soup.new_tag("div", id="div_id_alert_bottle_load", attrs={'hx-swap-oob': 'true'})
        div.attrs['hx-target'] = "#div_id_card_bottle_load"
        div.attrs['hx-trigger'] = 'load'
        div.attrs['hx-get'] = reload_url
        div.append(alert)

        soup.insert(0, div)

        response = HttpResponse(soup)
        response['HX-Trigger'] = 'update_samples'

    return response


def delete_log_file_errors(request, file_name):
    models.FileError.objects.filter(file_name__iexact=file_name).delete()

    return HttpResponse()


# ###### Bottle Load ###### #
url_prefix = "bottleload"
bottle_load_urls = [
    path(f'{url_prefix}/card/<int:mission_id>/', bottle_load_card, name="form_btl_card"),

    path(f'{url_prefix}/reload/<int:mission_id>/', reload_files, name="form_btl_reload_files"),
    path(f'{url_prefix}/dir/<int:mission_id>/', choose_bottle_dir, name="form_btl_choose_bottle_dir"),
    path(f'{url_prefix}/load/<int:mission_id>/', upload_btl_files, name="form_btl_upload_bottles"),
]
