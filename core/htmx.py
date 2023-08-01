import io
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import messages
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.http import HttpResponseRedirect, HttpResponse

from render_block import render_block_to_string

from biochem import models
from core import models

import logging

from core.parsers import elog

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


def update_geographic_regions(request):
    regions = models.GeographicRegion.objects.all().order_by("pk")
    selected = regions.last()
    regions.order_by('name')
    context = {'geographic_regions': regions, 'selected': selected.pk}

    html = render(request, 'core/partials/geographic_region.html', context)
    return HttpResponse(html)


def add_geo_region(request):
    region_name = request.POST.get('new_region')

    if region_name is None or region_name.strip() == "":
        message = _("could not create geographic region, no name provided")
        logger.error(message)

        html = render_block_to_string('core/mission_settings.html', 'geographic_region_block')
        # TODO: This should be replaced with a notification using Django Channels
        return HttpResponse(html)

    regs = models.GeographicRegion.objects.filter(name=region_name)

    if not regs.exists():
        region = models.GeographicRegion(name=region_name)
        region.save()

        regs = models.GeographicRegion.objects.filter(name=region_name)

    html = render_block_to_string('core/mission_settings.html', 'geographic_region_form')
    response = HttpResponse(html)
    response['HX-Trigger'] = "region_added"

    return response


def send_user_notification(group_name, mission, message):
    channel_layer = get_channel_layer()
    event = {
        'type': 'processing_message',
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


def upload_elog(request, mission_id):
    mission = models.Mission.objects.get(pk=mission_id)
    elog_configuration = models.ElogConfig.get_default_config(mission)

    files = request.FILES.getlist('event')
    group_name = 'mission_events'

    for index, file in enumerate(files):
        file_name = file.name
        process_message = f'{index}/{len(files)}: {file_name}'
        # let the user know that we're about to start processing a file
        send_user_notification(group_name, mission, f'Processing file {process_message}')

        # remove any existing errors for a log file of this name and update the interface
        models.FileError.objects.filter(mission=mission, file_name=file_name).delete()
        send_update_errors(group_name, mission)

        try:
            data = file.read()
            message_objects = elog.parse(io.StringIO(data.decode('utf-8')), elog_configuration)

            errors = []
            # make note of missing required field errors in this file
            for mid in message_objects[elog.ParserType.MID].keys():
                # Report errors to the user if there are any, otherwise process the message objects you can

                if mid in message_objects[elog.ParserType.ERRORS]:
                    for error in message_objects[elog.ParserType.ERRORS][mid]:
                        err = models.FileError(mission=mission, file_name=file_name, line=int(mid),
                                               type=models.ErrorType.missing_field,
                                               message=f'Elog message object ($@MID@$: {mid}) missing required '
                                                       f'field [{error.args[0]["expected"]}]')
                        errors.append(err)
                        message_objects[elog.ParserType.MID].pop(mid)
                        continue

            send_user_notification(group_name, mission, f"Process Stations {process_message}")
            elog.process_stations(message_objects[elog.ParserType.STATIONS])

            send_user_notification(group_name, mission, f"Process Instruments {process_message}")
            elog.process_instruments(message_objects[elog.ParserType.INSTRUMENTS])

            send_user_notification(group_name, mission, f"Process Events {process_message}")
            elog.process_events(message_objects[elog.ParserType.MID], mission)

            send_user_notification(group_name, mission, f"Process Actions and Attachments {process_message}")
            elog.process_attachments_actions(message_objects[elog.ParserType.MID], mission, file_name)

            send_user_notification(group_name, mission, f"Process Other Variables {process_message}")
            elog.process_variables(message_objects[elog.ParserType.MID], mission)

            if errors:
                models.FileError.objects.bulk_create(errors)

        except Exception as ex:
            if type(ex) is LookupError:
                logger.error(ex)
                err = models.FileError(mission=mission, type=models.ErrorType.missing_id, file_name=file_name,
                                       message=ex.args[0]['message'] + ", " + _("see error.log for details"))
            else:
                # Something is really wrong with this file
                logger.exception(ex)
                err = models.FileError(mission=mission, type=models.ErrorType.unknown, file_name=file_name,
                                       message=_("Unknown error :") + f"{str(ex)}, " +
                                               _("see error.log for details"))
            err.save()
            send_update_errors(group_name, mission)

            continue

    # clear the processing message
    send_user_notification(group_name, mission, '')

    context = {'object': mission}
    response = HttpResponse(render_block_to_string('core/mission_events.html', 'event_list', context))

    return response


def select_event(request, mission_id, event_id):
    mission = models.Mission.objects.get(pk=mission_id)
    event = models.Event.objects.get(pk=event_id)

    context = {'object': mission, 'selected_event': event}
    response = HttpResponse(render_block_to_string('core/mission_events.html', 'selected_event_details', context))
    return response


def get_mission_elog_errors(mission):
    errors = mission.file_errors.filter(file_name__iendswith='.log').order_by('file_name')
    files = errors.values_list('file_name').distinct()

    error_dict = {}
    for file in files:
        error_dict[file[0]] = []
        for error in errors.filter(file_name=file[0]):
            error_dict[file[0]].append(error)

    return error_dict


def get_file_errors(request, mission_id):
    mission = models.Mission.objects.get(pk=mission_id)
    context = {'errors': get_mission_elog_errors(mission)}
    response = HttpResponse(render_block_to_string('core/mission_events.html', 'error_block', context))

    return response
