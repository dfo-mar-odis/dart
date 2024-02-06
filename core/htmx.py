from bs4 import BeautifulSoup

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from crispy_forms.utils import render_crispy_form
from django.contrib import messages
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django.http import HttpResponseRedirect, HttpResponse

from render_block import render_block_to_string

from biochem import models
from core import models, forms


from core import validation
from dart.utils import load_svg

import logging
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
    errors = models.ValidationError.objects.filter(event__trip__mission=mission).order_by('event')

    error_dict = {}
    events = [error.event for error in errors]
    for event in events:
        error_dict[event.event_id] = []
        for error in event.validation_errors.all():
            error_dict[event.event_id].append(error)

    return error_dict


def get_file_errors(request, mission_id):
    mission = models.Mission.objects.get(pk=mission_id)
    file_errors = get_mission_elog_errors(mission)
    validation_errors = get_mission_validation_errors(mission)
    error_count = len(file_errors) + len(validation_errors)
    context = {
        'mission': mission,
        'errors': file_errors,
        'validation_errors': validation_errors,
        'error_count': error_count
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


htmx_urls = [
    path('mission/list/', list_missions, name="hx_list_missions"),
    path('hx/mission/delete/<int:mission_id>/', hx_mission_delete, name="hx_mission_delete"),
    path('geographic_region/add/', add_geo_region, name="hx_geo_region_add"),
    path('update_regions/', update_geographic_regions, name="hx_update_regions"),
    path('mission/errors/<int:mission_id>/', get_file_errors, name="hx_get_file_errors"),
    path('event/action/blank/<int:event_id>/', event_action, name="hx_get_blank_action"),
    path('event/action/list/<int:event_id>/', event_list_action, name="hx_list_actions"),

]