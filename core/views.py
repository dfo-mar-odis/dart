import concurrent.futures
import os
import queue
import time

from bs4 import BeautifulSoup
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.urls import reverse_lazy

import core.htmx
import dart2.utils
from biochem import models
from dart2.views import GenericFlilterMixin, GenericCreateView, GenericUpdateView, GenericDetailView
from dart2 import utils

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
    url = reverse_lazy("core:hx_sample_upload_ctd", args=(mission.pk,))
    hx = {
        'hx-get': url,
        'hx-trigger': 'load',
        'hx-target': '#div_id_upload_ctd_load',
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


class ElogDetails(GenericDetailView):
    template_name = 'core/mission_elog.html'
    page_title = _('Mission Elog Configuration')
    model = models.Mission

    def get_context_data(self, **kwargs):
        if not hasattr(self.object, 'elogconfig'):
            models.ElogConfig.get_default_config(self.object)

        context = super().get_context_data(**kwargs)
        return context


def hx_update_elog_config(request, **kwargs):
    if request.method == "POST":
        dict_vals = request.POST.copy()
        mission = models.Mission.objects.get(pk=kwargs['mission_id'])

        config = models.ElogConfig.get_default_config(mission)
        update_models = {'fields': set(), 'models': []}
        for field_name, map_value in dict_vals.items():
            mapping = config.mappings.filter(field=field_name)
            if mapping.exists():
                mapping = mapping[0]
                updated = utils.updated_value(mapping, 'mapped_to', map_value)
                if updated:
                    update_models['models'].append(mapping)

        if len(update_models['models']) > 0:
            models.FileConfigurationMapping.objects.bulk_update(update_models['models'], ['mapped_to'])

        config.save()
        context = {'object': mission}
        html = render_to_string(template_name='core/mission_elog.html', context=context)
        soup = BeautifulSoup(html, 'html.parser')
        for mapping in update_models['models']:
            input = soup.find(id=f'mapping_{mapping.id}')
            input.attrs['class'].append("bg-success-subtle")

        return HttpResponse(soup)