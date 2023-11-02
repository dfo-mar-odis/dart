import io

from django.http import HttpResponse
from django.template.context_processors import csrf
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from render_block import render_block_to_string

from core import forms, models
from core.htmx import send_user_notification_elog, send_update_errors, logger, htmx_validate_events
from core.parsers import elog
from core.views import MissionMixin, reports
from dart2.views import GenericDetailView


class EventDetails(MissionMixin, GenericDetailView):
    page_title = _("Missions Events")
    template_name = "core/mission_events.html"

    def get_page_title(self):
        return _("Mission Events") + " : " + self.object.name

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk, ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['search_form'] = forms.MissionSearchForm(initial={'mission': self.object.pk})
        context['events'] = self.object.events.all()

        context['reports'] = {key: reverse_lazy(reports[key], args=(self.object.pk,)) for key in reports.keys()}

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


def upload_elog(request, mission_id):

    mission = models.Mission.objects.get(pk=mission_id)
    elog_configuration = models.ElogConfig.get_default_config(mission)

    if request.method == "GET":
        url = reverse_lazy('core:hx_upload_elog', args=(mission_id,))
        attrs = {
            'component_id': "div_id_upload_elog_load",
            'message': '',
            'alert_type': "info",
            'hx-post': url,
            'hx-trigger': "load",
            'hx-target': "#elog_upload_file_form_id",
            'hx-swap': 'outerHTML',
            'hx-ext': "ws",
            'ws-connect': "/ws/notifications/"
        }
        soup = forms.save_load_component(**attrs)
        # add a message area for websockets
        msg_div = soup.find(id="div_id_upload_elog_load_message")
        msg_div.string = ""

        # The core.consumer.processing_elog_message() function is going to write output to a div
        # with the 'status' id, we'll stick that in the loading alerts message area and bam! Instant notifications!
        msg_div_status = soup.new_tag('div')
        msg_div_status['id'] = 'status'
        msg_div_status.string = _("Loading")
        msg_div.append(msg_div_status)

        response = HttpResponse(soup)
        return response

    files = request.FILES.getlist('event')
    group_name = 'mission_events'

    for index, file in enumerate(files):
        file_name = file.name
        process_message = f'{index}/{len(files)}: {file_name}'
        # let the user know that we're about to start processing a file
        send_user_notification_elog(group_name, mission, f'Processing file {process_message}')

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

            send_user_notification_elog(group_name, mission, f"Process Stations {process_message}")
            elog.process_stations(message_objects[elog.ParserType.STATIONS])

            send_user_notification_elog(group_name, mission, f"Process Instruments {process_message}")
            elog.process_instruments(message_objects[elog.ParserType.INSTRUMENTS])

            send_user_notification_elog(group_name, mission, f"Process Events {process_message}")
            errors += elog.process_events(message_objects[elog.ParserType.MID], mission)

            send_user_notification_elog(group_name, mission, f"Process Actions and Attachments {process_message}")
            errors += elog.process_attachments_actions(message_objects[elog.ParserType.MID], mission, file_name)

            send_user_notification_elog(group_name, mission, f"Process Other Variables {process_message}")
            errors += elog.process_variables(message_objects[elog.ParserType.MID], mission)

            for error in errors:
                file_error = models.FileError(mission=mission, file_name=file_name, line=error[0], message=error[1])
                if isinstance(error[2], KeyError):
                    file_error.type = models.ErrorType.missing_id
                elif isinstance(error[2], ValueError):
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
            send_user_notification_elog(group_name, mission, "File Error")

            continue

        htmx_validate_events(request, mission.pk, file_name)

    context = {'object': mission}
    response = HttpResponse(render_block_to_string('core/mission_events.html', 'event_import_form', context))
    response['HX-Trigger'] = 'event_updated'
    return response
