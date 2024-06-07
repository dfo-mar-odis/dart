from bs4 import BeautifulSoup
from django.urls import reverse_lazy, path
from django.http import HttpResponse
from django.utils.translation import gettext as _

from core import models as core_models
from core import forms

import logging

logger_notifications = logging.getLogger('dart.user.biochem_validation')


def _validate_mission_dates(mission: core_models.Mission) -> [core_models.Error]:
    logger_notifications.info(_("Validating Mission Dates"))

    date_errors = []
    if not mission.start_date:
        err = core_models.Error(mission=mission, type=core_models.ErrorType.biochem, message=_("Missing start date"))
        date_errors.append(err)

    if not mission.end_date:
        err = core_models.Error(mission=mission, type=core_models.ErrorType.biochem, message=_("Missing end date"))
        date_errors.append(err)

    if mission.start_date and mission.end_date and mission.end_date < mission.start_date:
        err = core_models.Error(mission=mission, type=core_models.ErrorType.biochem,
                                message=_("End date comes before Start date"))
        date_errors.append(err)

    return date_errors


def validate_mission(mission: core_models.Mission) -> [core_models.Error]:
    errors = []
    errors += _validate_mission_dates(mission)

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
    validate_mission(mission)

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

    for error in errors:
        ul.append(li := soup.new_tag('li'))
        li.attrs = {'class': 'list-group-item'}
        li.string = error.message

    response = HttpResponse(soup)
    return response


url_prefix = "<str:database>/<str:mission_id>"
database_urls = [
    path(f'{url_prefix}/biochem/validation/run/', run_biochem_validation, name="form_biochem_validation_run"),
    path(f'{url_prefix}/biochem/validation/', get_validation_errors, name="form_validation_get_validation_errors"),
]