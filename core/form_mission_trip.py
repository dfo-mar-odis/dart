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
from django.template.loader import render_to_string
from django.urls import path, reverse_lazy
from django.utils.translation import gettext as _
from render_block import render_block_to_string

from core import forms as core_forms, validation, form_event_details
from core import models
from core.htmx import send_user_notification_elog
from core.parsers import elog
from dart.utils import load_svg

from settingsdb import models as settings_models

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
        url = reverse_lazy('core:form_trip_select', args=(self.mission.name, self.mission.pk,))

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
            url = reverse_lazy('core:form_trip_save', args=(self.mission.name, self.mission.pk))
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

            url = reverse_lazy('core:form_trip_delete', args=(self.mission.name, self.mission.pk,
                                                              self.initial['select_trip']))
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
            url = reverse_lazy('core:form_trip_save', args=(self.mission.name, self.mission.pk,))
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

        div.append(Hidden('mission', self.mission.pk))
        div.append(Row(Column(Field('start_date')), Column(Field('end_date'))))

        div.append(Row(Column(Field('platform')), Column(Field('protocol'))))
        div.append(Row(Column(Field('collector_comments'))))
        div.append(Row(Column(Field('data_manager_comments'))))
        div.append(Row(Column(Field('more_comments'))))

        return div

    def __init__(self, mission, database=None, *args, **kwargs):
        self.mission = mission
        self.database = database if database else mission.name

        super().__init__(card_title=_("Trip"), card_name="mission_trips", *args, **kwargs)

        self.fields['mission'].queryset = models.Mission.objects.using(self.database).all()

        if self.instance:
            start_date = self.instance.start_date.strftime("%Y-%m-%d")
            self.fields['start_date'].widget = forms.DateInput({'type': 'date', 'value': start_date})

            end_date = self.instance.end_date.strftime("%Y-%m-%d")
            self.fields['end_date'].widget = forms.DateInput({'type': 'date', 'value': end_date})

        self.fields['select_trip'].label = False

        trips = mission.trips.all()
        self.fields['select_trip'].choices = [(trip.id, trip) for trip in trips]
        self.fields['select_trip'].choices.insert(0, (None, '--- New ---'))

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.save(using=self.database)

        return instance


def get_mision_trip_form(mission, trip=None):
    if trip:
        initial = {"select_trip": trip.pk}
        trip_form = TripForm(mission, collapsed=True, instance=trip, initial=initial)
    else:
        trip_form = TripForm(mission, collapsed=False)

    trip_html = render_crispy_form(trip_form)
    trip_soup = BeautifulSoup(trip_html, 'html.parser')

    form_soup = BeautifulSoup(f'<form id="form_id_{trip_form.get_card_name()}"></form>', 'html.parser')
    form = form_soup.find('form')
    form.append(trip_soup)

    return form


def mission_trip_card(request, database, mission_id, **kwargs):

    soup = BeautifulSoup('', 'html.parser')
    mission = models.Mission.objects.using(database).get(pk=mission_id)

    trip = None
    if 'trip_id' in kwargs and kwargs['trip_id'] != '':
        if mission.trips.filter(pk=int(kwargs['trip_id'])).exists():
            trip = mission.trips.get(pk=int(kwargs['trip_id']))
        else:
            trip = mission.trips.last()

    soup.append(get_mision_trip_form(mission, trip))

    div = soup.new_tag('div')
    div.attrs['id'] = 'div_id_trip_events'
    div.attrs['hx-swap-oob'] = 'true'
    div.attrs['class'] = "mb-2"
    soup.append(div)

    args = (database, mission_id,)
    if trip:
        # if a trip id is provided return a cleared Event Detail form
        details_form = form_event_details.EventDetails(trip=trip, database=database)
        event_html = render_to_string('core/partials/card_event_row.html',
                                      context={'database': database, 'trip': trip, 'details_form': details_form})
        event_table_soup = BeautifulSoup(event_html, 'html.parser')

        div.append(event_table_soup)

        args = (database, mission_id, trip.pk)

    response = HttpResponse(soup)
    response['HX-Push-Url'] = reverse_lazy("core:mission_events_details", args=args)
    return response


def save_trip(request, database, mission_id, **kwargs):
    mission = models.Mission.objects.using(database).get(pk=mission_id)
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "GET":
        form = TripForm(mission, database=database)

        div = soup.new_tag("div")
        div.attrs['id'] = form.get_alert_area_id()
        div.attrs['hx-swap-oob'] = "true"
        soup.append(div)

        url = reverse_lazy('core:form_trip_save', args=(database, mission_id,))
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
            trip = models.Trip.objects.using(database).get(pk=request.POST['select_trip'])
            form = TripForm(mission, database=database, instance=trip, data=request.POST)
        else:
            form = TripForm(mission, database=database, data=request.POST)

        if form.is_valid():
            trip = form.save()
            http_response: HttpResponse = select_trip(request, database, select_trip=trip.pk, **kwargs)
            soup = BeautifulSoup(http_response.content, 'html.parser')

            url = reverse_lazy("core:mission_events_revalidate", args=(database, trip.mission.pk,))
            soup.append(alert_div := soup.new_tag("div", id="div_id_card_alert_mission_trips"))
            alert_div.attrs['hx-get'] = url
            alert_div.attrs['hx-trigger'] = 'load'
            alert_div.attrs['hx-swap-oob'] = 'true'

            return HttpResponse(soup)
        else:
            form_html = render_crispy_form(form)
            form_soup = BeautifulSoup(form_html, 'html.parser')
            form_body = form_soup.find(id="div_id_card_body_mission_trips")
            form_body.attrs['hx-swap-oob'] = 'true'
            soup.append(form_body)

    return HttpResponse(soup)


def select_trip(request, database, **kwargs):

    trip_id = None
    if 'select_trip' in request.GET:
        trip_id = request.GET['select_trip']
    elif 'select_trip' in kwargs:
        trip_id = kwargs['select_trip']
    else:
        html = mission_trip_card(request, database, **kwargs)
        soup = BeautifulSoup(html.content, 'html.parser')
        soup.find('form').attrs['hx-swap-oob'] = "true"
        return HttpResponse(soup)

    if 'mission_id' not in kwargs:
        mission = models.Mission.objects.using(database).first()
        html = mission_trip_card(request, database, mission.pk, trip_id=trip_id, **kwargs)
    else:
        html = mission_trip_card(request, database, trip_id=trip_id, **kwargs)

    # if the selected trip changes update the form to show the selection
    soup = BeautifulSoup(html.content, 'html.parser')
    soup.find('form').attrs['hx-swap-oob'] = "true"

    response = HttpResponse(soup)
    if trip_id:
        trip = models.Trip.objects.using(database).get(pk=trip_id)
        response['HX-Push-Url'] = reverse_lazy("core:mission_events_details", args=(database, trip.mission_id, trip_id,))

    return response


def delete_trip(request, database, trip_id, **kwargs):
    trip = models.Trip.objects.using(database).get(pk=trip_id)
    mission = trip.mission

    trip.delete()

    last_trip = mission.trips.last()
    if last_trip:
        args = (database, trip.mission_id, last_trip.pk,)
    else:
        args = (database, trip.mission_id,)

    response = HttpResponse()
    response['HX-Redirect'] = reverse_lazy("core:mission_events_details", args=args)
    return response


def import_elog_events(request, database, **kwargs):
    trip_id = kwargs['trip_id']
    trip = models.Trip.objects.using(database).get(pk=trip_id)
    mission = trip.mission

    if request.method == 'GET':
        attrs = {
            'alert_area_id': "div_id_event_alert",
            'message': _("Processing Elog"),
            'logger': elog.logger_notifications.name,
            'hx-post': reverse_lazy("core:form_trip_import_events_elog", args=(database, trip_id,)),
            'hx-trigger': 'load'
        }
        return HttpResponse(core_forms.websocket_post_request_alert(**attrs))

    files = request.FILES.getlist('event')
    group_name = 'mission_events'

    file_count = len(files)
    for index, file in enumerate(files):
        file_name = file.name
        # let the user know that we're about to start processing a file
        # send_user_notification_elog(group_name, mission, f'Processing file {process_message}')
        elog.logger_notifications.info(_("Processing File") + " : %d/%d", (index+1), file_count)

        # remove any existing errors for a log file of this name and update the interface
        mission.file_errors.filter(file_name=file_name).delete()

        try:
            data = file.read()
            message_objects = elog.parse(io.StringIO(data.decode('utf-8')))

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

            # send_user_notification_elog(group_name, mission, f"Process Stations {process_message}")
            elog.process_stations(trip, message_objects[elog.ParserType.STATIONS])

            # send_user_notification_elog(group_name, mission, f"Process Instruments {process_message}")
            elog.process_instruments(trip, message_objects[elog.ParserType.INSTRUMENTS])

            # send_user_notification_elog(group_name, mission, f"Process Events {process_message}")
            errors += elog.process_events(trip, message_objects[elog.ParserType.MID])

            # send_user_notification_elog(group_name, mission, f"Process Actions and Attachments {process_message}")
            errors += elog.process_attachments_actions(trip, message_objects[elog.ParserType.MID], file_name)

            # send_user_notification_elog(group_name, mission, f"Process Other Variables {process_message}")
            errors += elog.process_variables(trip, message_objects[elog.ParserType.MID])

            error_count = len(errors)
            for err, error in enumerate(errors):
                elog.logger_notifications.info(_("Recording Errors") + f" {file_name} : %d/%d", (err+1), error_count)
                file_error = models.FileError(mission=mission, file_name=file_name, line=error[0], message=error[1])
                if isinstance(error[2], KeyError):
                    file_error.type = models.ErrorType.missing_id
                elif isinstance(error[2], ValueError):
                    file_error.type = models.ErrorType.missing_value
                else:
                    file_error.type = models.ErrorType.unknown
                file_errors.append(file_error)

            models.FileError.objects.using(database).bulk_create(file_errors)

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
            send_user_notification_elog(group_name, mission, "File Error")

            continue

        validation.validate_trip(trip)

    # When a file is first loaded it triggers a 'selection changed' event for the forms "input" element.
    # If we don't clear the input element here and the user tries to reload the same file, nothing will happen
    # and the user will be left clicking the button endlessly wondering why it won't load the file
    event_form = render_block_to_string('core/partials/card_event_row.html', 'event_import_form',
                                        context={'database': database, 'trip': trip})

    soup = BeautifulSoup()
    trip_form = get_mision_trip_form(mission, trip)
    trip_form.attrs['hx-swap-oob'] = 'true'

    soup.append(trip_form)
    event_form_soup = BeautifulSoup(event_form, 'html.parser')

    # Now that events are reloaded we should trigger a validation of the events
    msg_div = event_form_soup.find(id="div_id_event_message_area")
    alert_area = msg_div.find(id="div_id_event_alert")
    alert_area.attrs['hx-get'] = reverse_lazy("core:mission_events_revalidate", args=(database, mission.pk,))
    alert_area.attrs['hx-trigger'] = 'load'
    msg_div.attrs['hx-swap-oob'] = 'true'

    soup.append(event_form_soup)

    response = HttpResponse(soup)
    response['HX-Trigger'] = 'event_updated'
    return response


def list_events(request, database, trip_id, **kwargs):
    trip = models.Trip.objects.using(database).get(pk=trip_id)

    tr_html = render_to_string('core/partials/table_event.html', context={'database': database, 'trip': trip})

    return HttpResponse(tr_html)


url_prefix = "<str:database>/trip"
trip_load_urls = [
    path(f'{url_prefix}/card/<int:mission_id>/', mission_trip_card, name="form_trip_card"),
    path(f'{url_prefix}/card/<int:mission_id>/<int:trip_id>/', mission_trip_card, name="form_trip_card"),
    path(f'{url_prefix}/save/<int:mission_id>/', save_trip, name="form_trip_save"),
    path(f'{url_prefix}/delete/<int:mission_id>/<int:trip_id>/', delete_trip, name="form_trip_delete"),
    path(f'{url_prefix}/select/<int:mission_id>/', select_trip, name="form_trip_select"),

    path(f'{url_prefix}/event/import/<int:trip_id>/', import_elog_events, name="form_trip_import_events_elog"),
    path(f'{url_prefix}/event/list/<int:trip_id>/', list_events, name="form_trip_get_events"),
]
