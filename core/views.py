import concurrent.futures
import os
import queue
import time

from django.utils.translation import gettext as _
from django.urls import reverse_lazy

import core.htmx
from biochem import models
from dart2.views import GenericFlilterMixin, GenericCreateView, GenericUpdateView, GenericDetailView

from core import forms, filters, models, validation
from core.parsers import ctd

import logging

logger = logging.getLogger('dart')

# This queue is used for processing sample files in the hx_sample_upload_ctd function
sample_file_queue = queue.Queue()

reports = {
    "Chlorophyll Summary": "core:hx_report_chl",
    "Oxygen Summary": "core:hx_report_oxygen",
    "Salinity Summary": "core:hx_report_salt",
    "Profile Summary": "core:hx_report_profile",
    "Elog Report": "core:hx_report_elog",
    "Error Report": "core:hx_report_error",
}


class MissionMixin:
    model = models.Mission
    page_title = _("Missions")


class EventMixin:
    model = models.Event
    page_title = _("Event Details")


class MissionFilterView(MissionMixin, GenericFlilterMixin):
    filterset_class = filters.MissionFilter
    new_url = reverse_lazy("core:mission_new")
    home_url = ""
    fields = ["id", "name", "start_date", "end_date", "biochem_table"]


class MissionCreateView(MissionMixin, GenericCreateView):
    form_class = forms.MissionSettingsForm
    template_name = "core/mission_settings.html"

    def get_success_url(self):
        success = reverse_lazy("core:event_details", args=(self.object.pk, ))
        return success


class MissionUpdateView(MissionCreateView, GenericUpdateView):

    def form_valid(self, form):
        events = self.object.events.all()
        errors = []
        for event in events:
            event.validation_errors.all().delete()
            errors += validation.validate_event(event)

        models.ValidationError.objects.bulk_create(errors)
        return super().form_valid(form)


class SampleDetails(MissionMixin, GenericDetailView):
    page_title = _("Mission Samples")
    template_name = "core/mission_samples.html"

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk, ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reports'] = {key: reverse_lazy(reports[key], args=(self.object.pk,)) for key in reports.keys()}

        return context


def load_ctd_files(mission):

    group_name = 'mission_events'

    jobs = {}
    completed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        while not sample_file_queue.empty():
            processed = (len(completed) / (sample_file_queue.qsize() + len(completed))) * 100.0
            processed = str(round(processed, 2))

            kw = sample_file_queue.get()
            jobs[executor.submit(load_ctd_file, **kw)] = kw['file']

            logger.info(f"Processed {processed}")

            # update the user on our progress
            core.htmx.send_user_notification_queue(group_name, f"Loading {kw['file']}", processed)

            done, not_done = concurrent.futures.wait(jobs)

            # remove jobs from the job queue if they've been completed
            for future in done:

                file = jobs[future]
                try:
                    results = future.result()
                except Exception as ex:
                    logger.exception(ex)

                completed.append(file)
                del jobs[future]


    time.sleep(2)
    # The mission_samples.html page has a websocket notifications element on it. We can send messages
    # to the notifications element to display progress to the user, but we can also use it to
    # send an update request to the page when loading is complete.
    url = reverse_lazy("core:hx_sample_list", args=(mission.pk,))
    hx = {
        'hx-get': url,
        'hx-trigger': 'load',
        'hx-target': '#form_id_ctd_bottle_upload',
        'hx-swap': 'outerHTML'
    }
    core.htmx.send_user_notification_close(group_name, **hx)


def load_ctd_file(mission, file, bottle_dir):
    status = 'Success'
    group_name = 'mission_events'

    message = f"Loading file {file}"
    logger.info(message)

    ctd_file = os.path.join(bottle_dir, file)
    try:
        ctd.read_btl(mission, ctd_file)
    except Exception as ex:
        logger.exception(ex)
        status = "Fail"

    return status


