import datetime
import io
import os

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Row, Column, Field, Div, Hidden
from crispy_forms.utils import render_crispy_form

from django import forms
from django.conf import settings
from django.http import HttpResponse
from django.core.cache import caches
from django.template.loader import render_to_string
from django.urls import path, reverse_lazy
from django.utils.translation import gettext as _
from render_block import render_block_to_string

from core import forms as core_forms, validation
from core import models
from core.htmx import send_user_notification_elog, send_update_errors
from core.parsers import elog
from dart2.utils import load_svg

import logging
logger = logging.getLogger("dart")


class TripForm(core_forms.CollapsableCardForm, forms.ModelForm):

    select_trip = forms.ChoiceField(required=False)

    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'value': datetime.datetime.now().strftime("%Y-%m-%d")}))
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'value': datetime.datetime.now().strftime("%Y-%m-%d")}))

    # I had to override the default Bootstrap template for fields, because someone thought putting 'mb-3'
    # as a default for field wrappers was a good idea and it creates a massive gap under the inputs when
    # used in a card title
    field_template = os.path.join(settings.TEMPLATE_DIR, "field.html")

    class Meta:
        model = models.Trip
        fields = ['select_trip', 'mission', 'start_date', 'end_date', 'protocol', 'platform',
                  'collector_comments', 'more_comments', 'data_manager_comments']

    def get_trip_select(self):
        url = reverse_lazy('core:form_trip_select', args=(self.mission_id,))

        title_id = f"control_id_trip_select_{self.card_name}"

        db_select_attributes = {
            'id': title_id,
            'class': 'form-select form-select-sm mt-1',
            'name': 'select_trip',
            'hx-get': url,
            'hx-swap': 'none'
        }
        db_select = Column(
            Field('select_trip', template=self.field_template, **db_select_attributes,
                  wrapper_class="col-auto"),
            id=f"div_id_trip_select_{self.card_name}",
            css_class="col-auto"
        )

        return db_select

    def get_card_header(self):
        header = super().get_card_header()

        spacer = Column(Row())
        button_row = Row(css_class="align-self-end")

        button_column = Column()
        if 'select_trip' in self.initial:
            url = reverse_lazy('core:form_trip_save', args=(self.mission_id,))
            add_attrs = {
                'id': 'btn_id_db_details_update',
                'title': _('Update'),
                'name': 'update_trip',
                'hx_get': url,
                'hx_swap': 'none'
            }
            icon = load_svg('arrow-clockwise')
            add_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **add_attrs)
            spacer.append(add_button)

            url = reverse_lazy('core:form_trip_delete', args=(self.mission_id, self.initial['select_trip']))
            remove_attrs = {
                'id': 'btn_id_db_details_delete',
                'title': _('Remove'),
                'name': 'delete_trip',
                'hx_get': url,
                'hx_swap': 'none',
                'hx_confirm': _("Are you sure?")
            }
            icon = load_svg('dash-square')
            delete_button = StrictButton(icon, css_class="btn btn-danger btn-sm", **remove_attrs)
            button_column.append(delete_button)
        else:
            url = reverse_lazy('core:form_trip_save', args=(self.mission_id,))
            add_attrs = {
                'id': 'btn_id_db_details_add',
                'title': _('Add'),
                'name': 'add_trip',
                'hx_get': url,
                'hx_swap': 'none'
            }
            icon = load_svg('plus-square')
            add_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **add_attrs)
            spacer.append(add_button)

        button_row.fields.append(button_column)
        input_column = Column(button_row, css_class="col-auto")

        header.fields[0].fields.append(self.get_trip_select())
        header.fields[0].fields.append(spacer)
        header.fields[0].fields.append(input_column)

        header.fields.append(self.get_alert_area())

        return header

    def get_card_body(self) -> Div:
        div = super().get_card_body()

        div.append(Hidden('mission', self.mission_id))
        div.append(Row(Column(Field('start_date')), Column(Field('end_date'))))

        div.append(Row(Column(Field('platform')), Column(Field('protocol'))))
        div.append(Row(Column(Field('collector_comments'))))
        div.append(Row(Column(Field('data_manager_comments'))))
        div.append(Row(Column(Field('more_comments'))))

        return div

    def __init__(self, mission_id, *args, **kwargs):
        self.mission_id = mission_id

        super().__init__(card_title=_("Trip"), card_name="mission_trips", *args, **kwargs)

        if self.instance:
            start_date = self.instance.start_date.strftime("%Y-%m-%d")
            self.fields['start_date'].widget = forms.DateInput({'type': 'date', 'value': start_date})

            end_date = self.instance.end_date.strftime("%Y-%m-%d")
            self.fields['end_date'].widget = forms.DateInput({'type': 'date', 'value': end_date})

        self.fields['select_trip'].label = False

        trips = models.Mission.objects.get(pk=mission_id).trips.all()
        self.fields['select_trip'].choices = [(trip.id, trip) for trip in trips]
        self.fields['select_trip'].choices.insert(0, (None, '--- New ---'))


def mission_trip_card(request, **kwargs):
    mission_id = kwargs['mission_id']

    soup = BeautifulSoup('', 'html.parser')
    mission = models.Mission.objects.get(pk=mission_id)
    trip = None
    if 'trip_id' in kwargs and kwargs['trip_id'] == '':
        trip_form = TripForm(mission_id=mission_id, collapsed=False)
    else:
        if 'trip_id' in kwargs and mission.trips.filter(pk=kwargs['trip_id']).exists():
            trip = mission.trips.get(pk=kwargs['trip_id'])
        else:
            trip = mission.trips.last()

        if trip:
            initial = {"select_trip": trip.pk}
            trip_form = TripForm(mission_id=mission_id, collapsed=True, instance=trip, initial=initial)
        else:
            trip_form = TripForm(mission_id=mission_id, collapsed=False)

    trip_html = render_crispy_form(trip_form)
    trip_soup = BeautifulSoup(trip_html, 'html.parser')

    form_soup = BeautifulSoup(f'<form id="form_id_{trip_form.get_card_name()}"></form>', 'html.parser')
    form = form_soup.find('form')
    form.append(trip_soup)

    soup.append(form_soup)

    div = soup.new_tag('div')
    div.attrs['id'] = 'div_id_trip_events'
    div.attrs['hx-swap-oob'] = 'true'
    soup.append(div)

    args = (mission_id,)
    if trip:
        event_html = render_to_string('core/partials/card_event_row.html', context={
            'trip': trip
        })
        event_table_soup = BeautifulSoup(event_html, 'html.parser')

        div.append(event_table_soup)

        args = (mission_id, trip.pk)

    response = HttpResponse(soup)
    response['HX-Push-Url'] = reverse_lazy("core:mission_events_details", args=args)
    return response


def save_trip(request, **kwargs):

    mission_id = kwargs['mission_id']

    soup = BeautifulSoup('', 'html.parser')

    if request.method == "GET":
        form = TripForm(mission_id)

        div = soup.new_tag("div")
        div.attrs['id'] = form.get_alert_area_id()
        div.attrs['hx-swap-oob'] = "true"
        soup.append(div)

        url = reverse_lazy('core:form_trip_save', args=(mission_id,))
        attrs = {
            'component_id': 'div_id_trip_alert',
            'message': _("Saving"),
            'hx-post': url,
            'hx-trigger': 'load'
        }
        alert_soup = core_forms.save_load_component(**attrs)
        div.append(alert_soup)
    else:
        if 'select_trip' in request.POST and request.POST['select_trip']:
            trip = models.Trip.objects.get(pk=request.POST['select_trip'])
            form = TripForm(mission_id, instance=trip, data=request.POST)
        else:
            form = TripForm(mission_id, data=request.POST)

        if form.is_valid():
            trip = form.save()
            validation.validate_trip(trip)
            return select_trip(request, select_trip=trip.pk, **kwargs)
        else:
            form_html = render_crispy_form(form)
            form_soup = BeautifulSoup(form_html, 'html.parser')
            form_body = form_soup.find(id="div_id_card_body_mission_trips")
            form_body.attrs['hx-swap-oob'] = 'true'
            soup.append(form_body)

    return HttpResponse(soup)


def select_trip(request, **kwargs):

    trip_id = None
    if 'select_trip' in request.GET:
        trip_id = request.GET['select_trip']
    elif 'select_trip' in kwargs:
        trip_id = kwargs['select_trip']
    else:
        html = mission_trip_card(request, **kwargs)
        soup = BeautifulSoup(html.content, 'html.parser')
        soup.find('form').attrs['hx-swap-oob'] = "true"
        return HttpResponse(soup)

    html = mission_trip_card(request, trip_id=trip_id, **kwargs)

    # if the selected trip changes update the form to show the selection
    soup = BeautifulSoup(html.content, 'html.parser')
    soup.find('form').attrs['hx-swap-oob'] = "true"

    response = HttpResponse(soup)
    if trip_id:
        trip = models.Trip.objects.get(pk=trip_id)
        response['HX-Push-Url'] = reverse_lazy("core:mission_events_details", args=(trip.mission_id, trip_id,))

    return response


def delete_trip(request, **kwargs):
    trip_id = kwargs['trip_id']
    trip = models.Trip.objects.get(pk=trip_id)
    mission = trip.mission

    trip.delete()

    last_trip = mission.trips.last()
    if last_trip:
        args = (trip.mission_id, last_trip.pk,)
    else:
        args = (trip.mission_id,)

    response = HttpResponse()
    response['HX-Redirect'] = reverse_lazy("core:mission_events_details", args=args)
    return response


def import_elog_events(request, **kwargs):
    trip_id = kwargs['trip_id']
    trip = models.Trip.objects.get(pk=trip_id)
    mission = trip.mission

    if request.method == 'GET':
        attrs = {
            'component_id': 'div_id_load_elog_alert',
            'message': _("Loading"),
            'hx-post': reverse_lazy("core:form_trip_import_events_elog", args=(trip_id,)),
            'hx-trigger': 'load',
            'hx-swap': 'outerHTML',
            'hx-ext': "ws",
            'ws-connect': "/ws/notifications/"
        }
        alert = core_forms.save_load_component(**attrs)

        soup = BeautifulSoup('', 'html.parser')

        div = soup.new_tag('div')
        div.attrs['id'] = "div_id_event_alert"
        div.attrs['hx-swap-oob'] = 'true'
        div.append(alert.find('div'))

        # add a message area for websockets
        msg_div = div.find(id="div_id_load_elog_alert_message")
        msg_div.string = ""

        # The core.consumer.processing_elog_message() function is going to write output to a div
        # with the 'status' id, we'll stick that in the loading alerts message area and bam! Instant notifications!
        msg_div_status = soup.new_tag('div')
        msg_div_status['id'] = 'status'
        msg_div_status.string = _("Loading")
        msg_div.append(msg_div_status)

        soup.append(div)

        return HttpResponse(soup)

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
            elog_configuration = models.ElogConfig.get_default_config(mission)
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
            elog.process_stations(trip, message_objects[elog.ParserType.STATIONS])

            send_user_notification_elog(group_name, mission, f"Process Instruments {process_message}")
            elog.process_instruments(trip, message_objects[elog.ParserType.INSTRUMENTS])

            send_user_notification_elog(group_name, mission, f"Process Events {process_message}")
            errors += elog.process_events(trip, message_objects[elog.ParserType.MID])

            send_user_notification_elog(group_name, mission, f"Process Actions and Attachments {process_message}")
            errors += elog.process_attachments_actions(trip, message_objects[elog.ParserType.MID], file_name)

            send_user_notification_elog(group_name, mission, f"Process Other Variables {process_message}")
            errors += elog.process_variables(trip, message_objects[elog.ParserType.MID])

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

        validation.validate_trip(trip)

    response = HttpResponse(render_block_to_string('core/partials/card_event_row.html', 'event_import_form', context={
            'mission_id': trip.mission.pk,
            'trip_id': trip.pk
        }))
    response['HX-Trigger'] = 'event_updated'
    return response


def list_events(request, **kwargs):
    trip_id = kwargs['trip_id']
    trip = models.Trip.objects.get(pk=trip_id)

    tr_html = render_to_string('core/partials/table_event.html', context={'trip': trip})

    return HttpResponse(tr_html)


trip_load_urls = [
    path('trip/card/<int:mission_id>/', mission_trip_card, name="form_trip_card"),
    path('trip/card/<int:mission_id>/<int:trip_id>/', mission_trip_card, name="form_trip_card"),
    path('trip/save/<int:mission_id>/', save_trip, name="form_trip_save"),
    path('trip/delete/<int:mission_id>/<int:trip_id>/', delete_trip, name="form_trip_delete"),
    path('trip/select/<int:mission_id>/', select_trip, name="form_trip_select"),

    path('trip/event/import/<int:trip_id>/', import_elog_events, name="form_trip_import_events_elog"),
    path('trip/event/list/<int:trip_id>/', list_events, name="form_trip_get_events"),
]
