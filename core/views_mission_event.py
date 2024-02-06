import os
import time

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Div, HTML, Row, Column
from crispy_forms.utils import render_crispy_form
from django.core.cache import caches
from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from settingsdb import utils
from core import models, forms, validation, form_event_details, form_mission_trip
from core.views import MissionMixin, reports
from dart.utils import load_svg
from dart.views import GenericDetailView


class EventDetails(MissionMixin, GenericDetailView):
    page_title = _("Missions Events")
    template_name = "core/mission_events.html"

    def get_page_title(self):
        return _("Mission Events") + " : " + self.object.name

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if caches['default'].touch('selected_event'):
            caches['default'].delete('selected_event')

        context['search_form'] = forms.MissionSearchForm(initial={'mission': self.object.pk})

        if 'trip_id' in self.kwargs:
            context['trip_id'] = self.kwargs['trip_id']
        elif self.object.trips.last():
            context['trip_id'] = self.object.trips.last().pk

        context['reports'] = {key: reverse_lazy(reports[key], args=(self.object.pk,)) for key in reports.keys()}

        return context


class ValidationEventCard(forms.CardForm):

    event = None

    def get_card_body(self) -> Div:
        body = super().get_card_body()
        validation_errors = models.ValidationError.objects.using(self.database).filter(event=self.event)

        html = ""
        for error in validation_errors:
            html += f"<li>{error.message}</li>"

        html = f"<ul>{html}</ul>"
        body.fields.append(HTML(html))
        return body

    def __init__(self, event, database=None, *args, **kwargs):
        self.event = event
        self.database = database if database else event._state.db
        title = _("Event") + f" {event.event_id} : {event.trip.start_date} - {event.trip.end_date}"
        super().__init__(card_name=f"event_validation_{event.pk}", card_title=title, *args, **kwargs)


class ValidateEventsCard(forms.CollapsableCardForm):

    mission = None

    def get_card_header(self):
        header = super().get_card_header()

        spacer_col = Column(css_class="col")
        header.fields[0].fields.append(spacer_col)

        buttons = Column(css_class="col-auto align-self-end")
        header.fields[0].fields.append(buttons)

        btn_attrs = {
            'hx-get': reverse_lazy("core:mission_events_revalidate", args=(self.database, self.mission.pk,)),
            'hx-swap': 'none',
        }
        icon = load_svg('arrow-clockwise')
        revalidate = StrictButton(icon, css_class="btn btn-primary btn-sm", **btn_attrs)
        spacer_col.fields.append(revalidate)

        issue_count = models.ValidationError.objects.using(self.database).filter(event__trip__mission=self.mission).count()
        issue_count_col = Div(HTML(issue_count), css_class="badge bg-danger")
        buttons.fields.append(issue_count_col)

        header.fields.append(super().get_alert_area())

        return header
    
    def get_card_body(self) -> Div:
        body = super().get_card_body()
        body.css_class += " vertical-scrollbar"

        events_ids = models.ValidationError.objects.using(self.database).filter(
            event__trip__mission=self.mission
        ).values_list('event', flat=True)
        events = models.Event.objects.using(self.database).filter(pk__in=events_ids)
        for event in events:
            event_card = ValidationEventCard(event=event)
            div = Div(event_card.helper.layout, css_class="mb-2")
            body.fields.append(div)

        return body

    def __init__(self, mission, database=None, *args, **kwargs):
        self.mission = mission
        self.database = database if database else mission._state.db

        super().__init__(card_name="event_validation", card_title=_("Event Validation"), *args, **kwargs)


class ValidationFileCard(forms.CardForm):

    mission = None
    file_name = None

    def get_card_body(self) -> Div:
        body = super().get_card_body()

        errors = self.mission.file_errors.filter(file_name=self.file_name)
        html = ""
        for error in errors:
            html += f"<li>MID: {error.line} - {error.message}</li>"

        html = f"<ul>{html}</ul>"
        body.fields.append(HTML(html))
        return body

    def __init__(self, mission, file_name, uuid, *args, **kwargs):
        self.mission = mission
        self.file_name = file_name
        title = _("File") + f" : {file_name}"
        super().__init__(card_name=f"file_validation_{uuid}", card_title=title, *args, **kwargs)


class ValidateFileCard(forms.CollapsableCardForm):
    mission = None

    def get_card_header(self):
        header = super().get_card_header()

        spacer_col = Column(css_class="col")
        header.fields[0].fields.append(spacer_col)

        buttons = Column(css_class="col-auto align-self-end")
        header.fields[0].fields.append(buttons)

        issue_count = self.mission.file_errors.count()
        if issue_count > 0:
            issue_count_col = Div(HTML(issue_count), css_class="badge bg-danger")
            buttons.fields.append(issue_count_col)

        return header

    def get_card_body(self) -> Div:
        body = super().get_card_body()
        body.css_class += " vertical-scrollbar"

        files = self.mission.file_errors.all().values_list('file_name', flat=True).distinct()
        for index, file in enumerate(files):
            event_card = ValidationFileCard(self.mission, file, index)
            div = Div(event_card.helper.layout, css_class="mb-2")
            body.fields.append(div)

        return body

    def __init__(self, mission, *args, **kwargs):
        self.mission = mission
        super().__init__(card_name="file_validation", card_title=_("File Issues"), *args, **kwargs)


def get_validation_card(request, database, mission_id, **kwargs):
    mission = models.Mission.objects.using(database).get(pk=mission_id)
    validation_card = ValidateEventsCard(mission=mission, collapsed=('collapsed' not in kwargs))
    validation_card_html = render_crispy_form(validation_card)
    validation_card_soup = BeautifulSoup(validation_card_html, 'html.parser')

    if 'swap' in kwargs:
        validation_card_soup.find(id=validation_card.get_card_id()).attrs['hx-swap-oob'] = 'true'

    return HttpResponse(validation_card_soup)


def get_file_validation_card(request, database, mission_id, **kwargs):
    mission = models.Mission.objects.using(database).get(pk=mission_id)
    validation_card = ValidateFileCard(mission=mission, collapsed=('collapsed' not in kwargs))
    validation_card_html = render_crispy_form(validation_card)
    validation_card_soup = BeautifulSoup(validation_card_html, 'html.parser')

    if 'swap' in kwargs:
        validation_card_soup.find(id=validation_card.get_card_id()).attrs['hx-swap-oob'] = 'true'

    return HttpResponse(validation_card_soup)


def revalidate_events(request, database, mission_id):
    mission = models.Mission.objects.using(database).get(pk=mission_id)

    if request.method == "GET":

        attrs = {
            'alert_area_id': "div_id_card_alert_event_validation",
            'logger': validation.logger_notifications.name,
            'message': _("Revalidating"),
            'hx-trigger': 'load',
            'hx-post': reverse_lazy("core:mission_events_revalidate", args=(database, mission_id,)),
        }
        return HttpResponse(forms.websocket_post_request_alert(**attrs))

    validation.validate_mission(mission)
    response = get_validation_card(request, database, mission_id, swap=True, collapsed=False)
    response['HX-Trigger'] = 'event_updated'
    return response


path_prefix = '<str:database>/mission'
mission_event_urls = [
    path(f'{path_prefix}/event/<int:pk>/', EventDetails.as_view(), name="mission_events_details"),
    path(f'{path_prefix}/event/<int:pk>/<int:trip_id>/', EventDetails.as_view(), name="mission_events_details"),
    path(f'{path_prefix}/event/validation/<int:mission_id>/', get_validation_card, name="mission_events_validation"),
    path(f'{path_prefix}/file/validation/<int:mission_id>/', get_file_validation_card, name="mission_file_validation"),
    path(f'{path_prefix}/event/revalidate/<int:mission_id>/', revalidate_events, name="mission_events_revalidate"),
]

mission_event_urls += form_mission_trip.trip_load_urls + form_event_details.event_detail_urls
