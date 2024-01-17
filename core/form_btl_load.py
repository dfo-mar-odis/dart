import os
import queue
import threading
import time

import easygui

import concurrent.futures

from bs4 import BeautifulSoup

from threading import Thread

from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Column, Row, Div, Field
from crispy_forms.utils import render_crispy_form

from django import forms
from django.conf import settings
from django.http import HttpResponse
from django.template.context_processors import csrf
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core import htmx
from core import models
from core.parsers import ctd
from core.forms import CollapsableCardForm, CardForm, save_load_component
from dart2.utils import load_svg

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
        # url = reverse_lazy('core:mission_samples_upload_bio_chem', args=(self.mission_id,))
        button_icon = load_svg('folder-symlink')
        button_id = f'btn_id_load_{self.card_name}'
        button_attrs = {
            'id': button_id,
            'name': 'upload',
            'title': _("Select BTL directory"),
            'hx-get': self.get_open_folder_url(),
            'hx-swap': 'none'
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

    def get_refresh_url(self, hide_loaded: bool=False):
        url = reverse_lazy("core:form_btl_reload_files", args=(self.mission_id,))
        if hide_loaded:
            url += '?hide_loaded=true'

        return url

    def get_card_header(self):
        header = super().get_card_header()

        button_icon = load_svg('arrow-clockwise')
        button_attrs = {
            'id': f"{self.card_name}_refresh_files",
            'name': 'reload',
            'title': _("Refresh files in directory"),
            'hx-get': self.get_refresh_url('hide_loaded' in self.initial),
            'hx-swap': 'none',
            'value': "true"
        }
        refresh_button = StrictButton(
            button_icon, **button_attrs, css_class="btn btn-secondary btn-sm"
        )

        input = Column(
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
        header.fields[0].append(input)

        header.fields.append(self.get_alert_area())
        return header

    def get_card_body(self):
        body = super().get_card_body()

        load_icon = load_svg("arrow-down-square")
        url = reverse_lazy("core:form_btl_upload_bottles", args=(self.mission_id,))
        load_attrs = {
            'id': f"{self.card_name}_load_bottles",
            'hx-get': url,
            'hx-swap': 'none'
        }
        load_btn = StrictButton(load_icon, css_class="btn btn-primary btn-sm mb-2", **load_attrs)

        view_attrs = {
            'id': f"{self.card_name}_hide_loaded",
            'hx-get': self.get_refresh_url('hide_loaded' not in self.initial),
            'hx-swap': 'none'
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

    def __init__(self, mission_id, *args, **kwargs):
        if not mission_id:
            raise KeyError("missing mission_id for database connection card")

        self.mission_id = mission_id

        self.open_folder_url = reverse_lazy('core:form_btl_choose_bottle_dir', args=(self.mission_id,))
        super().__init__(card_name="bottle_load", card_title=_("Load Bottles"), *args, **kwargs)

        mission = models.Mission.objects.get(pk=mission_id)

        self.fields['dir_field'].label = False
        self.initial['dir_field'] = mission.bottle_directory

        self.fields['files'].label = False
        if mission.bottle_directory:
            files = [f for f in os.listdir(mission.bottle_directory) if f.upper().endswith('.BTL')]
            if 'hide_loaded' in self.initial:
                loaded_files = [f.upper() for f in models.Sample.objects.filter(
                    type__is_sensor=True,
                    bottle__event__trip__mission_id=mission_id).values_list('file', flat=True).distinct()]
                files = [f for f in files if f.upper() not in loaded_files]

            files.sort(key=lambda fn: os.path.getmtime(os.path.join(mission.bottle_directory, fn)))

            self.fields['files'].choices = [(file, file) for file in files]
            self.initial['files'] = [file for file in files]


def bottle_load_card(request, **kwargs):
    mission_id = kwargs['mission_id']

    context = {}
    context.update(csrf(request))

    initial = {'hide_loaded': "true"}
    if 'hide_loaded' in request.GET:
        initial['hide_loaded'] = request.GET['hide_loaded']

    bottle_load_form = BottleLoadForm(mission_id=mission_id, initial={'hide_loaded': "true"})
    bottle_load_html = render_crispy_form(bottle_load_form, context=context)
    bottle_load_soup = BeautifulSoup(bottle_load_html, 'html.parser')

    form_soup = BeautifulSoup(f'<form id="form_id_{bottle_load_form.get_card_name()}"></form>', 'html.parser')
    form = form_soup.find('form')
    form.append(bottle_load_soup)

    return HttpResponse(form_soup)


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

        logger.debug(f"Loading file {ctd_file}")

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

        htmx.send_user_notification_queue(group_name, f"Loaded {len(completed)}/{total_jobs}", processed)

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

    # time.sleep(2)
    # The mission_samples.html page has a websocket notifications element on it. We can send messages
    # to the notifications element to display progress to the user, but we can also use it to
    # send an update request to the page when loading is complete.
    url = reverse_lazy("core:form_btl_reload_files", args=(mission.pk,)) + "?hide_loaded=true"
    hx = {
        'hx-get': url,
        'hx-trigger': 'load',
        'hx-target': '#div_id_upload_ctd_load',
        'hx-swap': 'outerHTML'
    }

    htmx.send_user_notification_close(group_name, **hx)


def choose_bottle_dir(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = models.Mission.objects.get(pk=mission_id)
    result = easygui.diropenbox(title="Choose BTL directory")
    logger.info(result)

    if result:
        mission.bottle_directory = result
        mission.save()

    return reload_files(request, **kwargs)


def reload_files(request, **kwargs):
    mission_id = kwargs['mission_id']

    initial = {}
    if "hide_loaded" in request.GET or "hide_loaded" in request.POST:
        initial['hide_loaded'] = "true"

    form = BottleLoadForm(mission_id=mission_id, initial=initial)
    html = render_crispy_form(form)
    bottle_soup = BeautifulSoup(html, "html.parser")
    soup = BeautifulSoup("", "html.parser")

    dir_input = bottle_soup.find(id=form.get_card_header_id())
    dir_input.attrs['hx-swap-oob'] = "true"

    file_list = bottle_soup.find(id="div_id_files")
    file_list.attrs['hx-swap-oob'] = "true"

    if (errors := models.FileError.objects.filter(mission_id=mission_id, file_name__icontains='BTL')).exists():
        dir_input.attrs['class'].append("text-bg-warning")

        btl_error_form = CollapsableCardForm(card_name="bottle_file_errors", card_title=_("Bottle File Errors"))
        btl_errors_html = render_crispy_form(btl_error_form)
        btl_errors_soup = BeautifulSoup(btl_errors_html, 'html.parser')
        btl_errors_soup.find("div").attrs['class'].append("mt-2")

        body = btl_errors_soup.find(id=btl_error_form.get_card_body_id())

        files = errors.values_list('file_name', flat=True).distinct()
        error_list = soup.new_tag('ul')
        for file in files:
            file_item = soup.new_tag('li')
            file_item.string = str(file)
            ul_file = soup.new_tag('ul')
            for error in errors.filter(file_name__iexact=file):
                li_error = soup.new_tag('li')
                li_error.string = error.message
                ul_file.append(li_error)
            file_item.append(ul_file)
            error_list.append(file_item)

        body.append(error_list)

        file_list.append(btl_errors_soup)

    hide_loaded_btn = bottle_soup.find(id="bottle_load_hide_loaded")
    hide_loaded_btn.attrs['hx-swap-oob'] = "true"

    soup.append(dir_input)
    soup.append(file_list)
    soup.append(hide_loaded_btn)

    response = HttpResponse(soup)
    response['HX-Trigger'] = 'update_samples, file_errors_updated'
    return response


def upload_btl_files(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = models.Mission.objects.get(pk=mission_id)

    thread_name = "load_ctd_files"

    soup = BeautifulSoup('<div id="div_id_alert_bottle_load" hx-swap-oob="true"></div>', "html.parser")
    if request.method == "GET":
        attrs = {
            'component_id': "load_ctd_bottle",
            'message': _("Loading Bottles"),
            'hx-post': reverse_lazy("core:form_btl_upload_bottles", args=(mission_id,)),
            'hx-trigger': 'load'
        }
        alert = save_load_component(**attrs)
        soup.find(id="div_id_alert_bottle_load").append(alert)
        response = HttpResponse(soup)
    else:
        files = request.POST.getlist('files')
        logger.info(sample_file_queue.empty())
        for file in files:
            sample_file_queue.put((mission, file,))

        start = True
        for thread in threading.enumerate():
            if thread.name == thread_name:
                start = False

        if start:
            Thread(target=load_ctd_files, name=thread_name, daemon=True, args=(mission,)).start()

        attrs = {
            'component_id': "div_id_upload_ctd_load",
            'alert_type': 'info',
            'message': _("Loading"),
            'hx-target': "#form_id_ctd_bottle_upload",
            'hx-ext': "ws",
            'ws-connect': "/ws/notifications/"
        }
        alert_soup = save_load_component(**attrs)
        # add a message area for websockets
        msg_div = alert_soup.find(id="div_id_upload_ctd_load_message")
        msg_div.string = ""

        # The core.consumer.processing_elog_message() function is going to write output to a div
        # with the 'status' id, we'll stick that in the loading alerts message area and bam! Instant notifications!
        msg_div_status = alert_soup.new_tag('div')
        msg_div_status['id'] = 'status'
        msg_div_status.string = _("Loading")
        msg_div.append(msg_div_status)

        soup.find(id="div_id_alert_bottle_load").append(alert_soup)
        response = HttpResponse(soup)

    return response


# ###### Mission Sample ###### #
bottle_load_urls = [
    path('bottleload/card/<int:mission_id>/', bottle_load_card, name="form_btl_card"),

    path('bottleload/<int:mission_id>/', reload_files, name="form_btl_reload_files"),
    path('bottleload/dir/<int:mission_id>/', choose_bottle_dir, name="form_btl_choose_bottle_dir"),
    path('bottleload/load/<int:mission_id>/', upload_btl_files, name="form_btl_upload_bottles"),
]