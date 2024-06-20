from bs4 import BeautifulSoup
from enum import Enum
from django.urls import reverse_lazy, path
from django.http import HttpResponse
from django.utils.translation import gettext as _

from core import models as core_models
from core import forms

import logging

logger_notifications = logging.getLogger('dart.user.biochem_validation')


class BIOCHEM_CODES(Enum):
    # 1 - 1000 Date codes
    FAILED_WRITING_DATA = -1
    DATE_MISSING = 1  # use for when a date is missing
    DATE_BAD_VALUES = 2  # use when a date is improperly formatted or outside an expected range
    POSITION_MISSING = 50  # use when an event/bottle is missing a position
    DESCRIPTOR_MISSING = 1001  # use for when the mission descriptor is missing


def _validation_mission_descriptor(mission: core_models.Mission) -> [core_models.Error]:
    logger_notifications.info(_("Validating Mission descriptor"))
    descriptor_errors = []

    if not mission.mission_descriptor:
        err = core_models.Error(mission=mission, type=core_models.ErrorType.biochem,
                                message=_("Mission descriptor doesn't exist"),
                                code=BIOCHEM_CODES.DESCRIPTOR_MISSING.value)
        descriptor_errors.append(err)

    return descriptor_errors


def _validate_mission_dates(mission: core_models.Mission) -> [core_models.Error]:
    logger_notifications.info(_("Validating Mission Dates"))

    date_errors = []
    if not mission.start_date:
        err = core_models.Error(mission=mission, type=core_models.ErrorType.biochem, message=_("Missing start date"),
                                code=BIOCHEM_CODES.DATE_MISSING.value)
        date_errors.append(err)

    if not mission.end_date:
        err = core_models.Error(mission=mission, type=core_models.ErrorType.biochem, message=_("Missing end date"),
                                code=BIOCHEM_CODES.DATE_MISSING.value)
        date_errors.append(err)

    if mission.start_date and mission.end_date and mission.end_date < mission.start_date:
        err = core_models.Error(mission=mission, type=core_models.ErrorType.biochem,
                                message=_("End date comes before Start date"),
                                code=BIOCHEM_CODES.DATE_BAD_VALUES.value)
        date_errors.append(err)

    return date_errors


def _validate_bottles(mission) -> [core_models.Error]:
    logger_notifications.info(_("Validating Bottle Dates"))

    errors: [core_models.Error] = []
    database = mission._state.db
    bottles = core_models.Bottle.objects.using(database).filter(event__mission=mission)

    bottle_count = len(bottles)
    for index, bottle in enumerate(bottles):
        logger_notifications.info(_("Validating Bottles") + " : %d/%d", (index+1), bottle_count)

        if not bottle.latitude:
            # the biochem validation script only checks start dates, times, and positions
            if not bottle.event.start_location:
                err = core_models.Error(mission=mission, type=core_models.ErrorType.biochem,
                                        code=BIOCHEM_CODES.POSITION_MISSING.value,
                                        message=_("Event is missing a position. Event ID : ")+str(bottle.event.event_id)
                                        )
                errors.append(err)
    return errors


def validate_mission(mission: core_models.Mission) -> [core_models.Error]:
    errors = []
    errors += _validation_mission_descriptor(mission)
    errors += _validate_mission_dates(mission)
    errors += _validate_bottles(mission)

    return errors


def run_biochem_validation(request, database, mission_id):

    if request.method == 'GET':
        attrs = {
            'alert_area_id': "div_id_biochem_validation_details_alert",
            'message': _("Validating"),
            'logger': logger_notifications.name,
            'hx-post': request.path,
            'hx-trigger': 'load'
        }
        return HttpResponse(forms.websocket_post_request_alert(**attrs))

    # 1. Delete old validation errors
    core_models.Error.objects.using(database).filter(type=core_models.ErrorType.biochem).delete()

    # 2. Re-run validation
    mission = core_models.Mission.objects.using(database).get(id=mission_id)
    errors = validate_mission(mission)
    core_models.Error.objects.using(database).bulk_create(errors)

    response = HttpResponse()
    response['HX-Trigger'] = 'biochem_validation_update'
    return response


def get_validation_errors(request, database, mission_id):

    soup = BeautifulSoup('', 'html.parser')
    soup.append(badge_error_count := soup.new_tag("div"))
    badge_error_count.attrs["id"] = "div_id_biochem_validation_count"
    badge_error_count.attrs['hx-swap-oob'] = "true"

    errors = core_models.Error.objects.using(database).filter(type=core_models.ErrorType.biochem)
    if not errors:
        badge_error_count.attrs['class'] = 'badge bg-success'
        badge_error_count.string = "0"
        return HttpResponse(soup)

    badge_error_count.attrs['class'] = 'badge bg-danger'
    badge_error_count.string = str(errors.count())

    soup.append(ul := soup.new_tag('ul'))
    ul.attrs = {'class': 'list-group'}

    # codes that should link the user back to the mission settings page to fix the issues.
    settings_codes = [BIOCHEM_CODES.DESCRIPTOR_MISSING.value, BIOCHEM_CODES.DATE_MISSING.value,
                      BIOCHEM_CODES.DATE_BAD_VALUES.value]
    for error in errors:
        ul.append(li := soup.new_tag('li'))
        li.attrs = {'class': 'list-group-item'}
        li.string = error.message

        match error.code:
            case code if code in settings_codes:
                link = reverse_lazy('core:mission_edit', args=(database, mission_id))
                li.string += " : "
                li.append(a := soup.new_tag('a', href=link))
                a.string = _("Mission Details")


    response = HttpResponse(soup)
    return response


url_prefix = "<str:database>/<str:mission_id>"
database_urls = [
    path(f'{url_prefix}/biochem/validation/run/', run_biochem_validation, name="form_biochem_validation_run"),
    path(f'{url_prefix}/biochem/validation/', get_validation_errors, name="form_validation_get_validation_errors"),
]