import io
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from crispy_forms.utils import render_crispy_form
from django.contrib import messages
from django.shortcuts import render
from django.template.context_processors import csrf
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.http import HttpResponseRedirect, HttpResponse

from render_block import render_block_to_string

from biochem import models
from core import models, forms

import logging

from core.parsers import elog
from core import validation

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


def htmx_validate_events(request, mission_id, file_name):
    mission = models.Mission.objects.get(pk=mission_id)

    group_name = 'mission_events'

    try:
        validation_errors = []

        send_user_notification(group_name, mission, "Validating Events")
        file_events = mission.events.filter(actions__file=file_name).exclude(
            actions__type=models.ActionType.aborted).distinct()

        models.ValidationError.objects.filter(event__in=file_events).delete()

        for event in file_events:
            validation_errors += validation.validate_event(event)

        models.ValidationError.objects.bulk_create(validation_errors)
        # clear the processing message
        send_update_errors(group_name, mission)
        send_user_notification(group_name, mission, '')
    except Exception as ex:
        # Something is really wrong with this file
        logger.exception(ex)
        err = models.Error(mission=mission, type=models.ErrorType.unknown,
                           message=_("Unknown error during validation :") + f"{str(ex)}, " +
                                   _("see error.log for details"))
        err.save()
        send_update_errors(group_name, mission)

        # clear the processing message
        send_user_notification(group_name, mission, _('An unknown error occurred, see error.log'))


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
        mission.file_errors.filter(file_name=file_name).delete()
        send_update_errors(group_name, mission)

        try:
            data = file.read()
            message_objects = elog.parse(io.StringIO(data.decode('utf-8')), elog_configuration)

            file_errors: [models.FileError] = []
            errors: [tuple] = []
            # make note of missing required field errors in this file
            for mid, error_buffer in message_objects[elog.ParserType.ERRORS].items():
                # Report errors to the user if there are any, otherwise process the message objects you can
                for error in error_buffer:
                    err = models.FileError(mission=mission, file_name=file_name, line=int(mid),
                                           type=models.ErrorType.missing_value,
                                           message=f'Elog message object ($@MID@$: {mid}) missing required '
                                                   f'field [{error.args[0]["expected"]}]')
                    file_errors.append(err)

                    if mid in message_objects[elog.ParserType.MID]:
                        message_objects[elog.ParserType.MID].pop(mid)

            send_user_notification(group_name, mission, f"Process Stations {process_message}")
            elog.process_stations(message_objects[elog.ParserType.STATIONS])

            send_user_notification(group_name, mission, f"Process Instruments {process_message}")
            elog.process_instruments(message_objects[elog.ParserType.INSTRUMENTS])

            send_user_notification(group_name, mission, f"Process Events {process_message}")
            errors += elog.process_events(message_objects[elog.ParserType.MID], mission)

            send_user_notification(group_name, mission, f"Process Actions and Attachments {process_message}")
            errors += elog.process_attachments_actions(message_objects[elog.ParserType.MID], mission, file_name)

            send_user_notification(group_name, mission, f"Process Other Variables {process_message}")
            errors += elog.process_variables(message_objects[elog.ParserType.MID], mission)

            for error in errors:
                file_error = models.FileError(mission=mission, file_name=file_name, line=error[0], message=error[1])
                if error[2] is KeyError:
                    file_error.type = models.ErrorType.missing_id
                elif error[2] is ValueError:
                    file_error.type = models.ErrorType.missing_value
                else:
                    file_error.type = models.ErrorType.unknown
                file_errors.append(file_error)

            models.FileError.objects.bulk_create(file_errors)

        except Exception as ex:
            if type(ex) is LookupError:
                logger.error(ex)
                err = models.FileError(mission=mission, type=models.ErrorType.missing_id, file_name=file_name,
                                       message=ex.args[0]['message'] + ", " + _("see error.log for details"))
            else:
                # Something is really wrong with this file
                logger.exception(ex)
                err = models.FileError(mission=mission, type=models.ErrorType.unknown, file_name=file_name,
                                       message=_("Unknown error :") + f"{str(ex)}, " + _("see error.log for details"))
            err.save()
            send_update_errors(group_name, mission)
            send_user_notification(group_name, mission, "File Error")

            continue

        htmx_validate_events(request, mission.pk, file_name)

    context = {'object': mission}
    response = HttpResponse(render_block_to_string('core/mission_events.html', 'event_import_form', context))
    response['HX-Trigger'] = 'event_updated'
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
    context = {'errors': get_mission_elog_errors(mission),
               'validation_errors': get_mission_validation_errors(mission)}
    response = HttpResponse(render_block_to_string('core/mission_events.html', 'error_block', context))

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