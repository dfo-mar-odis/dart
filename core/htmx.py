from bs4 import BeautifulSoup

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from crispy_forms.utils import render_crispy_form
from django.contrib import messages
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.http import HttpResponseRedirect, HttpResponse

from render_block import render_block_to_string

from biochem import models
from core import models, forms

import logging

from core import validation
from dart2.utils import load_svg

logger = logging.getLogger("dart")


def mission_delete(request, mission_id):
    m = models.Mission.objects.get(pk=mission_id)
    m.delete()

    messages.success(request=request, message=_("Mission Deleted"))
    return HttpResponseRedirect(reverse_lazy("core:mission_filter"))


def hx_mission_delete(request, mission_id):
    m = models.Mission.objects.get(pk=mission_id)
    m.delete()

    return list_missions(request)


def list_missions(request):
    missions = None
    if request.GET:
        if 'name' in request.GET:
            missions = models.Mission.objects.filter(name__icontains=request.GET['name'])

    # if use the filtered list of missions if there was a git request otherwise return all missions
    missions = missions if missions else models.Mission.objects.all()

    context = {'missions': missions}
    response = HttpResponse(render_block_to_string('core/mission_filter.html', 'mission_table_block', context))

    return response


def update_geographic_regions(request, **kwargs):

    if request.method == "GET":
        if 'geographic_region' in request.GET and request.GET['geographic_region'] == '-1':
            soup = BeautifulSoup('', 'html.parser')

            row = soup.new_tag('div')
            row.attrs['class'] = 'container-fluid row'

            geo_region_input = soup.new_tag('input')
            geo_region_input.attrs['name'] = 'geographic_region'
            geo_region_input.attrs['id'] = 'id_geographic_region'
            geo_region_input.attrs['type'] = 'text'
            geo_region_input.attrs['class'] = 'textinput form-control col'

            submit = soup.new_tag('button')
            submit.attrs['class'] = 'btn btn-primary btn-sm ms-2 col-auto'
            submit.attrs['hx-post'] = reverse_lazy('core:hx_update_regions')
            submit.attrs['hx-target'] = '#div_id_geographic_region'
            submit.attrs['hx-select'] = '#div_id_geographic_region'
            submit.attrs['hx-swap'] = 'outerHTML'
            submit.append(BeautifulSoup(load_svg('plus-square'), 'html.parser').svg)

            row.append(geo_region_input)
            row.append(submit)

            soup.append(row)

            return HttpResponse(soup)

        mission_form = forms.MissionSettingsForm(request.GET)
        html = render_crispy_form(mission_form)
        soup = BeautifulSoup(html, "html.parser")
        geo_region = soup.find(id="id_geographic_region")

        return HttpResponse(geo_region.prettify())

    elif request.method == "POST":
        mission_dict = request.POST.copy()
        if 'geographic_region' in request.POST and (region_name := request.POST['geographic_region'].strip()):
            if (region := models.GeographicRegion.objects.filter(name=region_name)).exists():
                mission_dict['geographic_region'] = region[0].id
            else:
                region = models.GeographicRegion(name=region_name)
                region.save()
                mission_dict['geographic_region'] = models.GeographicRegion.objects.get(name=region_name)

        mission_form = forms.MissionSettingsForm(mission_dict)
        html = render_crispy_form(mission_form)
        return HttpResponse(html)


def add_geo_region(request):
    region_name = request.POST.get('new_region')

    if region_name is None or region_name.strip() == "":
        # if the region name is blank the user is just closing the dialog and nothing will happen.

        html = render_block_to_string('core/mission_settings.html', 'geographic_region_form')
        return HttpResponse(html)

    regs = models.GeographicRegion.objects.filter(name=region_name)

    if not regs.exists():
        region = models.GeographicRegion(name=region_name)
        region.save()

        regs = models.GeographicRegion.objects.filter(name=region_name)

    context = {}
    context.update(csrf(request))
    context['form'] = forms.MissionSettingsForm(initial={'geographic_region': regs[0].pk})
    html = render_to_string('core/mission_settings.html', context=context)

    response = HttpResponse(html)
    # response['HX-Trigger'] = "region_added"

    return response


def send_user_notification_close(group_name, **kwargs):
    channel_layer = get_channel_layer()
    event = {
        'type': 'close_render_queue',
    }
    if 'message' in kwargs:
        event['message'] = kwargs.pop('message')
    for key, value in kwargs.items():
        if key.startswith('hx'):
            event[key] = value

    async_to_sync(channel_layer.group_send)(group_name, event)


def send_user_notification_queue(group_name, message, queue=None):
    channel_layer = get_channel_layer()
    event = {
        'type': 'process_render_queue',
        'message': message,
        'queue': queue
    }

    async_to_sync(channel_layer.group_send)(group_name, event)


def send_user_notification_html_update(group_name, soup_element):
    channel_layer = get_channel_layer()
    event = {
        'type': 'send_html_update',
        'html_element': soup_element
    }

    async_to_sync(channel_layer.group_send)(group_name, event)


def send_user_notification_elog(group_name, mission, message):
    channel_layer = get_channel_layer()
    event = {
        'type': 'processing_elog_message',
        'mission': mission,
        'message': message
    }
    async_to_sync(channel_layer.group_send)(group_name, event)


def send_update_errors(group_name, mission):
    channel_layer = get_channel_layer()
    event = {
        'type': 'update_errors',
        'mission': mission,
    }
    async_to_sync(channel_layer.group_send)(group_name, event)


def htmx_validate_events(request, mission_id, file_name):
    mission = models.Mission.objects.get(pk=mission_id)

    group_name = 'mission_events'

    try:
        validation_errors = []

        send_user_notification_elog(group_name, mission, "Validating Events")
        file_events = mission.events.filter(actions__file=file_name).exclude(
            actions__type=models.ActionType.aborted).distinct()

        models.ValidationError.objects.filter(event__in=file_events).delete()

        for event in file_events:
            validation_errors += validation.validate_event(event)

        models.ValidationError.objects.bulk_create(validation_errors)
        # clear the processing message
        send_update_errors(group_name, mission)
        send_user_notification_elog(group_name, mission, '')
    except Exception as ex:
        # Something is really wrong with this file
        logger.exception(ex)
        err = models.Error(mission=mission, type=models.ErrorType.unknown,
                           message=_("Unknown error during validation :") + f"{str(ex)}, " +
                                   _("see error.log for details"))
        err.save()
        send_update_errors(group_name, mission)

        # clear the processing message
        send_user_notification_elog(group_name, mission, _('An unknown error occurred, see error.log'))


def get_mission_elog_errors(mission):
    errors = mission.file_errors.all().order_by('file_name')
    files = errors.values_list('file_name').distinct()

    error_dict = {}
    for file in files:
        error_dict[file[0]] = []
        for error in errors.filter(file_name=file[0]):
            error_dict[file[0]].append(error)

    return error_dict


def get_mission_validation_errors(mission):
    errors = models.ValidationError.objects.filter(event__mission=mission).order_by('event')

    error_dict = {}
    events = [error.event for error in errors]
    for event in events:
        error_dict[event.event_id] = []
        for error in event.validation_errors.all():
            error_dict[event.event_id].append(error)

    return error_dict


def get_file_errors(request, mission_id):
    mission = models.Mission.objects.get(pk=mission_id)
    context = {
        'mission': mission,
        'errors': get_mission_elog_errors(mission),
        'validation_errors': get_mission_validation_errors(mission)
    }
    html = render_to_string('core/partials/card_event_validation.html', context=context)
    response = HttpResponse(html)

    return response


def event_action(request, event_id):
    event = models.Event.objects.get(pk=event_id)
    if request.method == 'GET':
        context = {'actionform': forms.ActionForm(instance=event), "event": event}
        response = HttpResponse(render_block_to_string('core/event_settings.html', 'action_block', context))
        response['HX-Trigger'] = "update_actions"
        return response
    elif request.method == 'POST':
        form = forms.ActionForm(request.POST)
        if form.is_valid():
            form.save()
            context = {'actionform': forms.ActionForm(instance=event), "event": event}
            response = HttpResponse(render_block_to_string('core/event_settings.html', 'action_block', context))
            response['HX-Trigger'] = "update_actions"

            return HttpResponse(response)

        ctx = {'event': event}
        ctx.update(csrf(request))
        form_html = render_crispy_form(form, context=ctx)
        response = HttpResponse(form_html)
        return response


def event_list_action(request, event_id):
    event = models.Event.objects.get(pk=event_id)
    context = {'event': event}
    response = HttpResponse(render_block_to_string('core/event_settings.html', 'action_table_block', context))

    return response