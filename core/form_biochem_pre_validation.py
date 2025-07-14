import copy
import re

from bs4 import BeautifulSoup
from enum import Enum
from django.urls import reverse_lazy, path
from django.http import HttpResponse
from django.utils.translation import gettext as _
from django.db.models import Q, QuerySet

from config.utils import load_svg
from core import models as core_models
from core import forms

from biochem import models as biochem_models

import logging

logger_notifications = logging.getLogger('dart.user.biochem_validation')


class BIOCHEM_CODES(Enum):
    # 1 - 1000 Date codes
    FAILED_WRITING_DATA = -1
    DATE_MISSING = 1  # use for when a date is missing
    DATE_BAD_VALUES = 2  # use when a date is improperly formatted or outside an expected range
    POSITION_MISSING = 50  # use when an event/bottle is missing a position (lat/lon)
    DESCRIPTOR_MISSING = 2000  # use for when the mission descriptor is missing
    DATA = 2001  # use for general data errors
    DATA_BAD_RANGE = 2002  # use for bad data outside of expected BCRetrivals min/max

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
    bottles = core_models.Bottle.objects.filter(event__mission=mission)

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

def _validate_sample_ranges(mission) -> [core_models.Error]:
    logger_notifications.info(_("Validating Data Ranges"))
    errors: [core_models.Error] = []

    sample_types: QuerySet[core_models.MissionSampleType] = mission.mission_sample_types.filter(Q(uploads__status=core_models.BioChemUploadStatus.uploaded) | Q(uploads__status=core_models.BioChemUploadStatus.upload))
    for mst in sample_types:
        range = mst.datatype.data_retrieval
        values = core_models.DiscreteSampleValue.objects.filter(sample__type=mst).filter(Q(value__lt=range.minimum_value) | Q(value__gt=range.maximum_value))
        if values.exists():
            err = core_models.Error(mission=mission, type=core_models.ErrorType.biochem,
                                    code=BIOCHEM_CODES.DATA_BAD_RANGE.value,
                                    message=_("Samples exist outside of the expected range, count [") + str(values.count()) + "] : MST_ID [" + str(mst.pk) + "] :" + str(mst)
                                    )
            errors.append(err)

    return errors

def validate_mission(mission: core_models.Mission) -> [core_models.Error]:
    errors = []
    errors += _validation_mission_descriptor(mission)
    errors += _validate_mission_dates(mission)
    errors += _validate_bottles(mission)
    errors += _validate_sample_ranges(mission)

    return errors


def run_biochem_validation(request, mission_id):

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
    core_models.Error.objects.filter(type=core_models.ErrorType.biochem).delete()

    # 2. Re-run validation
    mission = core_models.Mission.objects.get(id=mission_id)
    errors = validate_mission(mission)
    core_models.Error.objects.bulk_create(errors)

    response = HttpResponse()
    response['HX-Trigger'] = 'biochem_validation_update'
    return response


def get_validation_errors(request, mission_id):

    soup = BeautifulSoup('', 'html.parser')
    soup.append(badge_error_count := soup.new_tag("div"))
    badge_error_count.attrs["id"] = "div_id_biochem_validation_count"
    badge_error_count.attrs['hx-swap-oob'] = "true"

    errors = core_models.Error.objects.filter(type=core_models.ErrorType.biochem)
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

    # If an element matches these codes the user should have an option to delete the flagged data
    remove_data_codes = [BIOCHEM_CODES.DATA_BAD_RANGE.value]

    mission = core_models.Mission.objects.get(pk=mission_id)
    database = mission._state.db
    minus_icon = BeautifulSoup(load_svg("dash-square"), 'html.parser').svg
    for error in errors:
        ul.append(li := soup.new_tag('li'))
        li.attrs = {'class': 'list-group-item'}
        li.string = error.message

        if error.code in settings_codes:
            link = reverse_lazy('core:mission_edit', args=(database, mission_id))
            li.append(div_row:=soup.new_tag('div', attrs={'class': 'row'}))
            div_row.append(div_col:=soup.new_tag('div', attrs={'class': 'col'}))
            div_col.append(a := soup.new_tag('a', href=link))
            a.attrs['class'] = 'btn btn-primary btn-sm'
            a.string = _("Mission Details")
        elif error.code in remove_data_codes:
            match = re.search(r'MST_ID \[(\d+)\]', error.message)
            if match:
                mst_id = int(match.group(1))

                url = reverse_lazy('core:form_biochem_pre_validation_bad_data', args=(mission_id, error.pk,))
                li.append(div_row:=soup.new_tag('div', attrs={'class': 'row'}))
                div_row.append(div_col:=soup.new_tag('div', attrs={'class': 'col'}))
                div_col.append(btn := soup.new_tag('button'))
                btn.attrs['class'] = 'btn btn-danger btn-sm'
                btn.attrs['hx-confirm'] = _("Are you sure?")
                btn.attrs['hx-swap'] = "none"
                btn.attrs['hx-post'] = url
                btn.attrs['title'] = _("Remove Bad Data")
                btn.append(copy.copy(minus_icon))

    response = HttpResponse(soup)
    return response


def remove_data(request, mission_id, error_id):
    error = core_models.Error.objects.get(mission__id=mission_id, pk=error_id)
    match = re.search(r'MST_ID \[(\d+)\]', error.message)
    if match:
        mst_id = int(match.group(1))

        mission = error.mission
        mst = mission.mission_sample_types.get(pk=mst_id)
        range = mst.datatype.data_retrieval

        values = core_models.DiscreteSampleValue.objects.filter(sample__type=mst).filter(
            Q(value__lt=range.minimum_value) | Q(value__gt=range.maximum_value))
        values.delete()
        error.delete()

    response = HttpResponse()
    response['HX-Trigger'] = "biochem_validation_update"
    return response


url_prefix = "<str:mission_id>"
database_urls = [
    path(f'{url_prefix}/biochem/validation/run/', run_biochem_validation, name="form_biochem_pre_validation_run"),
    path(f'{url_prefix}/biochem/validation/', get_validation_errors, name="form_biochem_pre_validation_get_validation_errors"),
    path(f'{url_prefix}/biochem/bad_data/<int:error_id>/', remove_data, name="form_biochem_pre_validation_bad_data"),
]
