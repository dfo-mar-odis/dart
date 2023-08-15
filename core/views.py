import concurrent.futures
import os
import io
import queue
import threading
import time

import pandas as pd
import csv

from bs4 import BeautifulSoup
from django.template.loader import render_to_string

from django_pandas.io import read_frame

from django.http import HttpResponse
from django.template.context_processors import csrf
from django.utils.translation import gettext as _
from django.urls import reverse_lazy
from render_block import render_block_to_string

import core.htmx
import dart2.utils
from biochem import models
from dart2.views import GenericFlilterMixin, GenericCreateView, GenericUpdateView, GenericDetailView

from core import forms, filters, models, validation
from core.parsers import ctd

from threading import Thread

import logging

logger = logging.getLogger('dart')

# This queue is used for processing sample files in the hx_sample_upload_ctd function
sample_file_queue = queue.Queue()


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


class EventDetails(MissionMixin, GenericDetailView):
    page_title = _("Missions Events")
    template_name = "core/mission_events.html"

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk, ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['search_form'] = forms.MissionSearchForm(initial={'mission': self.object.pk})
        context['events'] = self.object.events.all()
        return context


def hx_event_select(request, event_id):
    event = models.Event.objects.get(pk=event_id)

    context = {}
    context['object'] = event.mission
    context['selected_event'] = event
    if not event.files:
        context['form'] = forms.EventForm(instance=event)
        context['actionform'] = forms.ActionForm(initial={'event': event.pk})
        context['attachmentform'] = forms.AttachmentForm(initial={'event': event.pk})

    response = HttpResponse(render_block_to_string('core/mission_events.html', 'selected_event_details', context))
    response['HX-Trigger'] = 'selected_event_updated'
    return response


def hx_event_new_delete(request, mission_id, event_id):

    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        # called with no event id to create a blank instance of the event_edit_form
        context['form'] = forms.EventForm(initial={'mission': mission_id})
        response = HttpResponse(
            render_block_to_string('core/partials/event_edit_form.html', 'event_content', context=context))
        return response
    elif request.method == "POST":
        if event_id:
            event = models.Event.objects.get(pk=event_id)
            context['object'] = event.mission
            event.delete()
            response = HttpResponse(render_block_to_string('core/mission_events.html', 'content_details_block',
                                                           context=context))
            response['HX-Trigger-After-Swap'] = 'event_updated'
            return response


def hx_event_update(request, event_id):
    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        event = models.Event.objects.get(pk=event_id)
        context['event'] = event
        context['form'] = forms.EventForm(instance=event)
        context['actionform'] = forms.ActionForm(initial={'event': event.pk})
        context['attachmentform'] = forms.AttachmentForm(initial={'event': event.pk})
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'event_content', context=context))
        return response
    if request.method == "POST":
        mission_id = request.POST['mission']
        event_id = request.POST['event_id']
        context.update(csrf(request))
        update = models.Event.objects.filter(mission_id=mission_id, event_id=event_id).exists()

        if update:
            event = models.Event.objects.get(mission_id=mission_id, event_id=event_id)
            form = forms.EventForm(request.POST, instance=event)
        else:
            form = forms.EventForm(request.POST, initial={'mission': mission_id})

        if form.is_valid():
            event = form.save()
            form = forms.EventForm(instance=event)
            context['form'] = form
            context['event'] = event
            context['actionform'] = forms.ActionForm(initial={'event': event.pk})
            context['attachmentform'] = forms.AttachmentForm(initial={'event': event.pk})
            context['page_title'] = _("Event : ") + str(event.event_id)
            if update:
                # if updating an event, everything is already on the page, just update the event form area
                response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'event_form', context=context))
                response['HX-Trigger'] = 'update_actions, update_attachments'
            else:
                # if creating a new event, update the entire event block to add other blocks to the page
                response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'event_content', context=context))
                response['HX-Trigger-After-Swap'] = "event_updated"
                # response['HX-Push-Url'] = reverse_lazy('core:event_edit', args=(event.pk,))
            return response

        context['form'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'event_form', context=context))
        return response


def hx_update_action(request, action_id):
    context = {}
    context.update(csrf(request))

    if 'reset' in request.GET:
        # I'm passing the event id to initialize the form through the 'action_id' variable
        # it's not stright forward, but the action form needs to maintain an event or the
        # next action won't know what event it should be attached to.
        form = forms.ActionForm(initial={'event': action_id})
        context['actionform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'action_form', context=context))
        return response
    else:
        action = models.Action.objects.get(pk=action_id)
        event = action.event
    context['event'] = event

    if request.method == "GET":
        form = forms.ActionForm(instance=action, initial={'event': event.pk})
        context['actionform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'action_form', context=context))
        return response
    elif request.method == "POST":
        action.delete()
        response = HttpResponse(render_block_to_string('core/partials/table_action.html', 'action_table',
                                                       context=context))
        return response


def hx_new_action(request, event_id):
    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        # if the get method is used with this function the form will be cleared.
        event_id = request.GET['event']
        context['event'] = models.Event.objects.get(pk=event_id)
        context['actionform'] = forms.ActionForm(initial={'event': event_id})
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'action_form', context=context))
        return response
    elif request.method == "POST":
        action = None
        if 'id' in request.POST:
            action = models.Action.objects.get(pk=request.POST['id'])
            event_id = action.event.pk
            form = forms.ActionForm(request.POST, instance=action)
            event = action.event
        else:
            event_id = request.POST['event']
            event = models.Event.objects.get(pk=event_id)
            form = forms.ActionForm(request.POST, initial={'event': event_id})

        context['event'] = event

        if form.is_valid():
            action = form.save()
            # context['actionforms'] = [forms.ActionForm(instance=action) for action in event.actions.all()]
            context['actionform'] = forms.ActionForm(initial={'event': event_id})
            response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'action_form', context=context))
            response['HX-Trigger'] = 'update_actions'
            return response

        context['actionform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'action_form', context=context))
        return response


def hx_update_attachment(request, action_id):
    context = {}
    context.update(csrf(request))

    if 'reset' in request.GET:
        # I'm passing the event id to initialize the form through the 'action_id' variable
        # it's not stright forward, but the action form needs to maintain an event or the
        # next action won't know what event it should be attached to.
        form = forms.AttachmentForm(initial={'event': action_id})
        context['attachmentform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'attachments_form', context=context))
        return response
    else:
        attachment = models.InstrumentSensor.objects.get(pk=action_id)
        event = attachment.event
    context['event'] = event

    if request.method == "GET":
        form = forms.AttachmentForm(instance=attachment, initial={'event': event.pk})
        context['attachmentform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'attachments_form', context=context))
        return response
    elif request.method == "POST":
        attachment.delete()
        response = HttpResponse(render_block_to_string('core/partials/table_attachment.html', 'attachments_table',
                                                       context=context))
        return response


def hx_new_attachment(request):
    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        # if the get method is used with this function the form will be cleared.
        event_id = request.GET['event']
        context['event'] = models.Event.objects.get(pk=event_id)
        context['attachmentform'] = forms.AttachmentForm(initial={'event': event_id})
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'attachments_form', context=context))
        return response
    elif request.method == "POST":
        attachment = None
        if 'id' in request.POST:
            attachment = models.InstrumentSensor.objects.get(pk=request.POST['id'])
            event_id = attachment.event.pk
            form = forms.AttachmentForm(request.POST, instance=attachment)
            event = attachment.event
        else:
            event_id = request.POST['event']
            event = models.Event.objects.get(pk=event_id)
            form = forms.AttachmentForm(request.POST, initial={'event': event_id})

        context['event'] = event

        if form.is_valid():
            attachment = form.save()
            # context['actionforms'] = [forms.ActionForm(instance=action) for action in event.actions.all()]
            context['attachmentform'] = forms.AttachmentForm(initial={'event': event_id})
            response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'attachments_form', context=context))
            response['HX-Trigger'] = 'update_attachments'
            return response

        context['attachmentform'] = form
        response = HttpResponse(render_block_to_string('core/partials/event_edit_form.html', 'attachments_form', context=context))
        return response


def hx_list_action(request, event_id, editable=False):
    event = models.Event.objects.get(pk=event_id)
    context = {'event': event, 'editable': editable}
    response = HttpResponse(render_block_to_string('core/partials/table_action.html', 'action_table', context=context))
    return response


def hx_list_attachment(request, event_id, editable=False):
    event = models.Event.objects.get(pk=event_id)
    context = {'event': event, 'editable': editable}
    response = HttpResponse(render_block_to_string('core/partials/table_attachment.html', 'attachments_table',
                                                   context=context))
    return response


def hx_list_event(request, mission_id):
    mission = models.Mission.objects.get(pk=mission_id)
    events = mission.events.all()
    if request.method == 'GET':
        if 'station' in request.GET and request.GET['station']:
            events = events.filter(station=request.GET['station'])

        if 'instrument' in request.GET and request.GET['instrument']:
            events = events.filter(instrument=request.GET['instrument'])

        if 'action_type' in request.GET and request.GET['action_type']:
            events = events.filter(actions__type=request.GET['action_type'])

        if 'event_start' in request.GET and request.GET['event_start']:
            start_id = request.GET['event_start']

            if 'event_end' in request.GET and request.GET['event_end']:
                end_id = request.GET['event_end']
                events = events.filter(event_id__lte=end_id, event_id__gte=start_id)
            else:
                events = events.filter(event_id=start_id)
        elif 'event_end' in request.GET and request.GET['event_end']:
            end_id = request.GET['event_end']
            events = events.filter(event_id=end_id)

        if 'sample_start' in request.GET and request.GET['sample_start']:
            start_id = request.GET['sample_start']
            if 'sample_end' in request.GET and request.GET['sample_end']:
                end_id = request.GET['sample_end']
                events = events.filter(sample_id__lte=end_id, end_sample_id__gte=start_id)
            else:
                events = events.filter(sample_id__lte=start_id, end_sample_id__gte=start_id)
        elif 'sample_end' in request.GET and request.GET['sample_end']:
            end_id = request.GET['sample_end']
            events = events.filter(sample_id__lte=end_id, end_sample_id__gte=end_id)

    context = {'mission': mission, 'events': events}
    response = HttpResponse(render_block_to_string('core/partials/table_event.html', 'event_table',
                                                   context=context))
    return response


class SampleDetails(MissionMixin, GenericDetailView):
    page_title = _("Mission Samples")
    template_name = "core/mission_samples.html"

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk, ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        return context


def hx_sample_form(request, mission_id):
    context = {}
    context.update(csrf(request))

    mission = models.Mission.objects.get(pk=mission_id)
    if request.method == "GET":

        datatype_filter = request.GET['datatype_filter'] if 'datatype_filter' in request.GET else None
        initial = {"mission": mission_id, 'datatype_filter': datatype_filter}
        if request.FILES:
            initial['file'] = request.FILES['file']

        # context['sample_form'] = forms.NewSampleForm(initial=initial)
        context['object'] = mission
        html = render_block_to_string('core/mission_samples.html', 'new_sample_form_block', context)
        response = HttpResponse(html)

        return response

    elif request.method == "POST":
        datatype_filter = request.GET['datatype_filter'] if 'datatype_filter' in request.GET else None
        initial = {"mission": mission_id, 'datatype_filter': datatype_filter}

        file_data = None
        if request.FILES:
            file = request.FILES['file']
            initial['file_name'] = file.name
            file_data = file.read().decode('utf-8')
            initial['file_data'] = file_data

        # A POST action is required to upload a file even to just read a couple lines of it, but if the POST
        # request comes form a 'choose file' changed event then the 'submit' button won't be in the POST request
        # so we can update the form the user sees here when they select a file and ask them to choose tabs and columns
        # that we'll need to know when processing the file.
        if 'submit' not in request.POST:
            context['sample_form'] = forms.NewSampleForm(initial=initial)
            html = render_block_to_string('core/mission_samples.html', 'new_sample_form_block', context)
            response = HttpResponse(html)

            return response

        form = forms.NewSampleForm(request.POST, initial=initial)
        if form.is_valid():
            tab = int(request.POST['tab']) if 'tab' in request.POST else -1
            skip_lines = int(request.POST['skip_lines']) if 'skip_lines' in request.POST else -1
            sample_column = int(request.POST['sample_id_col']) if 'sample_id_col' in request.POST else -1
            value_column = int(request.POST['sample_value_col']) if 'sample_value_col' in request.POST else -1

            stream = io.StringIO(file_data)
            df = pd.read_csv(filepath_or_buffer=stream, header=skip_lines)
            dart2.utils.parse_csv_sample_file(df, sample_column, value_column)

            logger.info(f"Processing file {file.name}")
            context['sample_form'] = forms.NewSampleForm(initial={"mission": mission_id})
            html = render_block_to_string('core/mission_samples.html', 'new_sample_form_block', context)
            response = HttpResponse(html)

            return response

        context['sample_form'] = form
        html = render_block_to_string('core/mission_samples.html', 'new_sample_form_block', context)
        response = HttpResponse(html)
        return response


def hx_sample_upload_ctd(request, mission_id):
    context = {}
    context.update(csrf(request))

    thread_name = "load_ctd_files"

    if request.method == "GET":
        bottle_dir = request.GET['bottle_dir']
        files = [f for f in os.listdir(bottle_dir) if f.lower().endswith('.btl')]
        files.sort(key=lambda fn: os.path.getmtime(os.path.join(bottle_dir, fn)))
        context['file_form'] = forms.BottleSelection(initial={'mission': mission_id,
                                                              'bottle_dir': bottle_dir,
                                                              'file_name': files})
        html = render_block_to_string('core/mission_samples.html', 'ctd_list', context=context)
        response = HttpResponse(html)

        mission = models.Mission.objects.get(pk=mission_id)
        mission.bottle_directory = bottle_dir
        mission.save()

        return response
    elif request.method == "POST":
        bottle_dir = request.POST['bottle_dir']
        files = request.POST.getlist('file_name')
        mission = models.Mission.objects.get(pk=mission_id)

        logger.info(sample_file_queue.empty())
        for file in files:
            sample_file_queue.put({"mission": mission, "file": file, "bottle_dir": bottle_dir})

        start = True
        for thread in threading.enumerate():
            if thread.name == thread_name:
                start = False

        if start:
            Thread(target=load_ctd_files, name=thread_name, daemon=True, args=(mission,)).start()

        context['object'] = mission
        html = render_block_to_string('core/mission_samples.html', 'ctd_list', context=context)
        response = HttpResponse(html)
        return response
    response = HttpResponse("Hi!")
    return response


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

            core.htmx.send_render_block(group_name, template='core/partials/notifications_samples.html',
                                        block='notifications',
                                        context={'msg': f"Loading {kw['file']}", 'queue': processed})

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
    hx = {
        'get': reverse_lazy("core:hx_sample_list", args=(mission.pk,)),
        'trigger': 'load',
        'target': '#sample_table',
        'swap': 'outerHTML'
    }
    core.htmx.send_render_block(group_name, template='core/partials/notifications_samples.html',
                                block='notifications', context={'hx': hx})


def load_ctd_file(mission, file, bottle_dir):
    status = 'Success'
    group_name = 'mission_events'

    message = f"Loading file {file}"
    logger.info(message)

    # core.htmx.send_render_block(group_name, template='core/partials/notifications_samples.html',
    #                             block='notifications', context={'msg': message})

    ctd_file = os.path.join(bottle_dir, file)
    try:
        ctd.read_btl(mission, ctd_file)
    except Exception as ex:
        logger.exception(ex)
        status = "Fail"

    return status


def hx_list_samples(request, **kwargs):
    context = {}

    page = int(request.GET['page'] if 'page' in request.GET else 0)
    page_limit = 50
    page_start = page_limit * page

    mission_id = kwargs['mission_id']
    sensor_id = kwargs['sensor_id'] if 'sensor_id' in kwargs else None

    mission = models.Mission.objects.get(pk=mission_id)
    bottle_limit = models.Bottle.objects.filter(event__mission=mission).order_by('bottle_id')[page_start:(page_start+page_limit)]
    headings = []
    if sensor_id:
        queryset = models.Sample.objects.filter(type_id=sensor_id, bottle__in=bottle_limit)
        queryset = queryset.order_by('bottle__bottle_id')
        queryset = queryset.values(
            'type__short_name', 'bottle__bottle_id', 'bottle__pressure', 'discrete_value__value',
            'discrete_value__flag', 'discrete_value__sample_datatype'
        )
        headings = ['Flag', 'Datatype']
        df = read_frame(queryset)
        df.columns = ["Sensor", "Sample", "Pressure", "Value"] + headings

    else:
        queryset = models.Sample.objects.filter(bottle__in=bottle_limit)
        queryset = queryset.order_by('bottle__bottle_id')
        queryset = queryset.values(
            'type__short_name', 'bottle__bottle_id', 'bottle__pressure', 'discrete_value__value'
        )
        df = read_frame(queryset)
        df.columns = ["Sensor", "Sample", "Pressure", "Value"]

    if not queryset.exists():
        soup = BeautifulSoup('<table id="sample_table"></table>', 'html.parser')
        response = HttpResponse(soup)
        return response

    df = df.pivot(index=['Sample', 'Pressure'], columns='Sensor')
    # df = df.groupby(["Sample", 'Sensor']).count().reset_index()
    html = df.to_html(classes=['table', 'table-striped', 'tscroll'])

    # Using BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup(html, 'html.parser')
    soup.find('table').attrs['id'] = "sample_table"


    # remove the first table row pandas adds for the "Value" column header
    soup.find("thead").find("tr").decompose()

    # This row contains the headers we action want... Except for the 'Sensor' header
    # fix the headers, then remove the 'index' table row
    sensor_headers = soup.find("thead").find("tr")
    index_headers = soup.find("thead").find("tr").find_next("tr")

    column = sensor_headers.find('th')
    index = index_headers.find('th')

    column.string = index.string

    column = column.find_next_sibling('th')
    index = index.find_next_sibling('th')

    column.string = index.string

    index_headers.decompose()

    column = column.find_next_sibling('th')
    if sensor_id:
        # if the sensor_id is present then we want to show the specific details for this sensor/sample
        short_name = column.string
        sensor = models.SampleType.objects.get(short_name=short_name)
        sensor_row = soup.new_tag("tr")

        td_back = soup.new_tag("td")
        back_button = soup.new_tag('button')
        svg = dart2.utils.load_svg('arrow-left-square')
        icon = BeautifulSoup(svg, 'html.parser').svg

        # create a button so the user can go back to viewing all loaded sensors/samples
        back_button.attrs['class'] = 'btn btn-primary'
        back_button.attrs['hx-trigger'] = 'click'
        back_button.attrs['hx-get'] = reverse_lazy('core:hx_sample_list', args=(mission_id,))
        back_button.attrs['hx-target'] = "#sample_table"
        back_button.attrs['hx-swap'] = 'outerHTML'
        back_button.append(icon)

        td_back.append(back_button)
        sensor_row.append(td_back)

        th_data_type = soup.new_tag("th")
        th_data_type.string = _("Sensor Datatype")
        td_back.insert_after(th_data_type)

        td_data_type_value = soup.new_tag("td")
        td_data_type_value.string = str(sensor.datatype.pk) if sensor.datatype else _("None")
        th_data_type.insert_after(td_data_type_value)

        th_data_type_des = soup.new_tag("th")
        th_data_type_des.string = _("Datatype Description")
        td_data_type_value.insert_after(th_data_type_des)

        td_data_type_des_value = soup.new_tag("td")
        td_data_type_des_value.string = sensor.datatype.description if sensor.datatype else _("None")
        th_data_type_des.insert_after(td_data_type_des_value)

        sensor_headers.insert_before(sensor_row)

        col_span = -1
        # if we're looking at a sensor then keep the first column label, but change the next two
        column = column.find_next_sibling('th')
        for heading in headings:
            column.string = _(heading)
            column = column.find_next_sibling('th')
            col_span += 1

        td_data_type_des_value.attrs['colspan'] = col_span
    else:
        # now add htmx tags to the rest of the TH elements in the row so the user
        # can click that row for details on the sensor
        while column:
            short_name = column.string
            sampletype = models.SampleType.objects.get(short_name=short_name)
            button = soup.new_tag("button")
            button.string = short_name
            column.string = ''
            button.attrs['class'] = 'btn btn-primary'
            button.attrs['hx-trigger'] = 'click'
            button.attrs['hx-get'] = reverse_lazy('core:hx_sample_list', args=(mission_id, sampletype.pk,))
            button.attrs['hx-target'] = "#sample_table"
            button.attrs['hx-swap'] = 'outerHTML'
            button.attrs['title'] = sampletype.long_name

            column.append(button)

            column = column.find_next_sibling('th')

    # now we'll attach an HTMX call to the last queried table row so when the user scrolls to it the next batch
    # of samples will be loaded into the table.
    args = (mission_id, sensor_id,) if sensor_id else (mission_id,)
    last_tr = soup.find('tbody').find_all('tr')[-1]
    last_tr.attrs['hx-target'] = 'this'
    last_tr.attrs['hx-trigger'] = 'intersect once'
    last_tr.attrs['hx-get'] = reverse_lazy('core:hx_sample_list', args=args) + f"?page={page+1}"
    last_tr.attrs['hx-swap'] = "afterend"

    if page > 0:
        response = HttpResponse(soup.find('tbody').findAll('tr', recursive=False))
    else:
        response = HttpResponse(soup)
    return response


def get_csv_header(file_string: str) -> {}:
    csv_reader = csv.reader(file_string, delimiter=',')
    skip = 0
    header_fields = next(csv_reader)
    while '' in header_fields:
        skip += 1
        header_fields = next(csv_reader)

    return skip, header_fields


def load_sample_type(request, **kwargs):

    context = {}
    context.update(csrf(request))

    # the mission id is used to determine if we're actually going to save anything or if we're just process
    # and sending back updated forms
    mission_id = kwargs['mission'] if 'mission' in kwargs else None

    if request.method == "POST":

        if 'sample_file' in request.FILES:
            file = request.FILES['sample_file']
            file_name = file.name
            file_type = file_name.split('.')[-1].lower()

            if not mission_id:
                field_choices = []
                skip = 0
                if file_type == 'csv':
                    data = file.read()
                    csv_header = get_csv_header(data.decode('utf-8').split("\r\n"))
                    skip = csv_header[0]
                    field_choices = [(field.lower, field) for field in csv_header[1]]

                sample_type_form = forms.SampleTypeForm(post_url=request.path)
                file_config_form = forms.SampleFileConfigurationForm(
                    initial={"file_type": file_type, "header": skip},
                    field_choices=field_choices,
                )
                context['sample_type_form'] = sample_type_form
                context['file_form'] = file_config_form
                html = render_block_to_string("core/partials/form_sample_type.html", "file_input_form_block",
                                              context=context)
                return HttpResponse(html)

            sample_type_form = forms.SampleTypeForm(request.POST)
            if sample_type_form.is_valid():
                sample_type: models.SampleType = sample_type_form.save()
                config_args = request.POST.dict()
                config_args['sample_type'] = sample_type
                file_config_form = forms.SampleFileConfigurationForm(config_args)
                if file_config_form.is_valid():
                    file_settings: models.SampleFileSettings = file_config_form.save()

                    context['mission_id'] = mission_id
                    html = render_block_to_string("core/partials/form_sample_type.html", "file_input_form_block",
                                                  context=context)
                    return HttpResponse(html)
                else:
                    # if the file config isn't valid then remove the sample type too
                    sample_type.delete()
            context['sample_type_form'] = sample_type_form
            context['file_form'] = file_config_form
            context['mission_id'] = mission_id
            # context['sample_file'] = request.FILES['sample_file']
            html = render_block_to_string("core/partials/form_sample_type.html", "file_input_form_block", context=context)
            return HttpResponse(html)

    elif request.method == "GET":
        if mission_id:
            context['mission_id'] = mission_id
            html = render_to_string("core/mission_samples_2.html", request=request, context=context)
            return HttpResponse(html)

        if request.htmx:
            # if this is an htmx request it's to grab an updated element from the form, like the BioChem Datatype
            # field after the Datatype_filter has been triggered.
            sample_type_form = forms.SampleTypeForm(initial=request.GET, post_url=request.path)
            context['sample_type_form'] = sample_type_form
        html = render_block_to_string("core/partials/form_sample_type.html", "file_input_form_block", context=context)
        return HttpResponse(html)
