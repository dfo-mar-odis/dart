import copy
import re

from bs4 import BeautifulSoup
from enum import Enum

from django.conf import settings
from django.urls import reverse_lazy, path
from django.http import HttpResponse
from django.utils.translation import gettext as _
from django.db.models import Q, QuerySet

from config.utils import load_svg
from core import models as core_models
from core import forms

import logging

logger_notifications = logging.getLogger('dart.user.biochem_validation')
logger = logging.getLogger('dart')


class BIOCHEM_CODES(Enum):
    # 1 - 1000 Date codes
    FAILED_WRITING_DATA = -1
    DATE_MISSING = 1  # use for when a date is missing
    DATE_BAD_VALUES = 2  # use when a date is improperly formatted or outside an expected range
    POSITION_MISSING = 50  # use when an event/bottle is missing a position (lat/lon)
    DESCRIPTOR_MISSING = 2000  # use for when the mission descriptor is missing
    DATA = 2001  # use for general data errors
    DATA_BAD_RANGE = 2002  # use for bad data outside of expected BCRetrivals min/max

def _validation_mission_descriptor(mission: core_models.Mission) -> [core_models.MissionError]:
    logger_notifications.info(_("Validating Mission descriptor"))
    descriptor_errors = []

    if not mission.mission_descriptor:
        err = core_models.MissionError(mission=mission, type=core_models.ErrorType.biochem,
                                       message=_("Mission descriptor doesn't exist"),
                                       code=BIOCHEM_CODES.DESCRIPTOR_MISSING.value)
        descriptor_errors.append(err)

    return descriptor_errors


def _validate_mission_dates(mission: core_models.Mission) -> [core_models.MissionError]:
    logger_notifications.info(_("Validating Mission Dates"))

    date_errors = []
    if not mission.start_date:
        err = core_models.MissionError(mission=mission, type=core_models.ErrorType.biochem, message=_("Missing start date"),
                                       code=BIOCHEM_CODES.DATE_MISSING.value)
        date_errors.append(err)

    if not mission.end_date:
        err = core_models.MissionError(mission=mission, type=core_models.ErrorType.biochem, message=_("Missing end date"),
                                       code=BIOCHEM_CODES.DATE_MISSING.value)
        date_errors.append(err)

    if mission.start_date and mission.end_date and mission.end_date < mission.start_date:
        err = core_models.MissionError(mission=mission, type=core_models.ErrorType.biochem,
                                       message=_("End date comes before Start date"),
                                       code=BIOCHEM_CODES.DATE_BAD_VALUES.value)
        date_errors.append(err)

    return date_errors


def _validate_bottles(mission) -> [core_models.MissionError]:
    logger_notifications.info(_("Validating Bottle Dates"))

    errors: [core_models.MissionError] = []
    bottles = core_models.Bottle.objects.filter(event__mission=mission)

    bottle_count = len(bottles)
    for index, bottle in enumerate(bottles):
        logger_notifications.info(_("Validating Bottles") + " : %d/%d", (index+1), bottle_count)

        if not bottle.latitude:
            # the biochem validation script only checks start dates, times, and positions
            if not bottle.event.start_location:
                err = core_models.MissionError(mission=mission, type=core_models.ErrorType.biochem,
                                               code=BIOCHEM_CODES.POSITION_MISSING.value,
                                               message=_("Event is missing a position. Event ID : ")+str(bottle.event.event_id)
                                               )
                errors.append(err)
    return errors

def _validate_sample_ranges(mission) -> [core_models.MissionError]:
    logger_notifications.info(_("Validating Data Ranges"))
    errors: [core_models.MissionError] = []

    sample_types: QuerySet[core_models.MissionSampleType] = mission.mission_sample_types.filter(Q(uploads__status=core_models.BioChemUploadStatus.uploaded) | Q(uploads__status=core_models.BioChemUploadStatus.upload))
    for mst in sample_types:
        range = mst.datatype.data_retrieval
        values = core_models.DiscreteSampleValue.objects.filter(sample__type=mst).exclude(flag__exact=4).filter(Q(value__lt=range.minimum_value) | Q(value__gt=range.maximum_value))
        if values.exists():
            # mst_id allows us to find the mission sample type later when removing or flagging data
            message = "MST_ID [" + str(mst.pk) + "]"
            message += " : " + str(values.count()) + " " + _("Samples exist outside of the expected range")
            message += f" [{range.minimum_value}, {range.maximum_value}]"
            err = core_models.MissionError(mission=mission, type=core_models.ErrorType.biochem,
                                           code=BIOCHEM_CODES.DATA_BAD_RANGE.value,
                                           message=message
                                           )
            errors.append(err)

    return errors

def validate_mission(mission: core_models.Mission) -> [core_models.MissionError]:
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
    core_models.MissionError.objects.filter(type=core_models.ErrorType.biochem).delete()

    # 2. Re-run validation
    mission = core_models.Mission.objects.get(id=mission_id)
    errors = validate_mission(mission)
    core_models.MissionError.objects.bulk_create(errors)

    response = HttpResponse()
    response['HX-Trigger'] = 'biochem_validation_update'
    return response


def get_validation_errors(request, mission_id):

    mission = core_models.Mission.objects.get(pk=mission_id)
    try:
        database = settings.DATABASES[mission._state.db]['LOADED']
    except KeyError as ex:
        logger.exception(ex)
        database = 'mission_db'

    soup = BeautifulSoup('', 'html.parser')
    soup.append(badge_error_count := soup.new_tag("div"))
    badge_error_count.attrs["id"] = "div_id_biochem_validation_count"
    badge_error_count.attrs['hx-swap-oob'] = "true"

    errors = core_models.MissionError.objects.filter(type=core_models.ErrorType.biochem)
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

    minus_icon = BeautifulSoup(load_svg("dash-square"), 'html.parser').svg
    flag_icon = BeautifulSoup(load_svg("flag"), 'html.parser').svg
    for error in errors:
        if error.code in settings_codes:
            ul.append(li := soup.new_tag('li'))
            li.attrs = {'class': 'list-group-item'}
            li.string = error.message

            link = reverse_lazy('core:mission_edit', args=(database, mission_id))
            li.append(btn_row:=soup.new_tag('div', attrs={'class': 'row'}))
            btn_row.append(div_col:=soup.new_tag('div', attrs={'class': 'col'}))
            div_col.append(a := soup.new_tag('a', href=link))
            a.attrs['class'] = 'btn btn-primary btn-sm'
            a.string = _("Mission Details")
        elif error.code in remove_data_codes:
            ul.append(li := soup.new_tag('li'))
            li.attrs = {'class': 'list-group-item'}
            li.append(title_row:=soup.new_tag("div"))

            title_row.attrs = {'class': 'd-flex w-100 justify-content-between'}
            title_row.append(header:=soup.new_tag("h5"))
            header.string = _("Unknown issue")

            title_row.append(count_badge:=soup.new_tag("span"))
            count_badge.attrs = {'class': 'd-flex align-items-center badge text-bg-primary'}
            count_badge.string = "0"

            li.append(message_row:=soup.new_tag("p"))
            message_row.attrs = {'class': 'mb-1'}

            match = re.search(r'MST_ID \[(\d+)\]', error.message)
            message = re.sub(r'MST_ID \[\d+\] : ', '', error.message)
            count_match = re.search(r'^(\d+)', message)
            if count_match:
                count_badge.string = count_match.group(1)
                message = re.sub(r'^\d+ ', '', message)

            message_row.string = message

            if match:
                mst_id = int(match.group(1))
                mst = core_models.MissionSampleType.objects.get(pk=mst_id)
                header.string = str(mst)

                li.append(btn_row:=soup.new_tag('div', attrs={'class': 'row'}))
                btn_row.append(div_col:=soup.new_tag('div', attrs={'class': 'col'}))

                url = reverse_lazy('core:form_biochem_pre_validation_flag_data', args=(mission_id, error.pk,))
                div_col.append(btn_flag := soup.new_tag('button'))
                btn_flag.attrs['class'] = 'btn btn-danger btn-sm me-2'
                btn_flag.attrs['hx-confirm'] = _("Are you sure?")
                btn_flag.attrs['hx-swap'] = "none"
                btn_flag.attrs['hx-post'] = url
                btn_flag.attrs['title'] = _("Flag Bad Data")
                btn_flag.append(copy.copy(flag_icon))

                url = reverse_lazy('core:form_biochem_pre_validation_bad_data', args=(mission_id, error.pk,))
                div_col.append(btn_remove := soup.new_tag('button'))
                btn_remove.attrs['class'] = 'btn btn-danger btn-sm me-2'
                btn_remove.attrs['hx-confirm'] = _("Are you sure?")
                btn_remove.attrs['hx-swap'] = "none"
                btn_remove.attrs['hx-post'] = url
                btn_remove.attrs['title'] = _("Remove Bad Data")
                btn_remove.append(copy.copy(minus_icon))

    response = HttpResponse(soup)
    return response


def flag_data(request, mission_id, error_id):
    error = core_models.MissionError.objects.get(mission__id=mission_id, pk=error_id)
    match = re.search(r'MST_ID \[(\d+)\]', error.message)
    if match:
        mst_id = int(match.group(1))

        mission = error.mission
        mst = mission.mission_sample_types.get(pk=mst_id)
        range = mst.datatype.data_retrieval

        values = core_models.DiscreteSampleValue.objects.filter(sample__type=mst).filter(
            Q(value__lt=range.minimum_value) | Q(value__gt=range.maximum_value))
        for v in values:
            v.flag = 4

        core_models.DiscreteSampleValue.objects.bulk_update(values, ['flag'])

        error.delete()

    response = HttpResponse()
    response['HX-Trigger'] = "biochem_validation_update"
    return response

def remove_data(request, mission_id, error_id):
    error = core_models.MissionError.objects.get(mission__id=mission_id, pk=error_id)
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
    path(f'{url_prefix}/biochem/flag_data/<int:error_id>/', flag_data, name="form_biochem_pre_validation_flag_data"),
]
