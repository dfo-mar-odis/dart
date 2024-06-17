import time
from datetime import datetime

import core.models
from core import models as core_models
from django.utils.translation import gettext as _
from django.db.models import Q

import logging

logger_notifications = logging.getLogger('dart.user.validation')


def validate_mission(mission: core_models.Mission):
    database = mission._state.db
    events = core_models.Event.objects.using(database).filter(mission=mission)

    core_models.ValidationError.objects.using(database).filter(event__mission=mission,
                                                               type=core_models.ErrorType.validation).delete()
    errors = []
    events_count = len(events)
    for index, event in enumerate(events):
        logger_notifications.info(_("Validating Event") + " : %d/%d", (index+1), events_count)
        errors += validate_event(event)

    core_models.ValidationError.objects.using(database).bulk_create(errors)


def validate_event(event: core_models.Event) -> [core_models.ValidationError]:

    database = event._state.db

    # I return the errors rather than just saving them so events can be validated and saved in bulk
    # it's up to the calling function to delete ValidationError objects on an event before validating it
    validation_errors = []

    actions = event.actions.all()

    # Don't validate aborted events
    if actions.filter(type=core_models.ActionType.aborted).exists():
        return validation_errors

    # Don't validate duplicates of the 'other' action_type
    distinct_actions = actions.exclude(type=core_models.ActionType.other).values_list('type', flat=True)

    for action_type in distinct_actions:
        if len(actions.filter(type=action_type)) > 1:
            message = _("Event contains duplicate actions")
            err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
            validation_errors.append(err)
            break

    for action in actions:
        if not action.sounding:
            message = _("Event is missing a depth for action") + f' {action.get_type_display()}'
            err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
            validation_errors.append(err)

    if event.start_location == [None, None]:
        message = _("Event is missing an action with a valid location") + f' {event.event_id}'
        err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
        validation_errors.append(err)

    # Validate event does not have duplicate action types
    mission = event.mission
    if event.start_date is None or event.end_date is None:
        message = _("Event is missing start and/or end date")

        err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
        validation_errors.append(err)
    elif event.start_date.date() < mission.start_date or event.start_date.date() > mission.end_date or \
            event.end_date.date() < mission.start_date or event.end_date.date() > mission.end_date:
        message = _("Action occurred outside of mission dates")
        message += " " + mission.start_date.strftime("%Y-%m-%d") + " - " + mission.end_date.strftime("%Y-%m-%d")

        err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
        validation_errors.append(err)

    dup_events = core_models.Event.objects.using(database).filter(
        event_id=event.event_id,
        station=event.station,
        instrument=event.instrument
    ).exclude(pk=event.pk)

    if dup_events.exists():
        message = _("Event with the same ID, Station and Instrument already exists for this mission")

        err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
        validation_errors.append(err)

    if event.instrument.type == core_models.InstrumentType.ctd:
        validation_errors += validate_ctd_event(event)
    elif event.instrument.type == core_models.InstrumentType.net:
        if 'multinet' not in event.instrument.name.lower():
            validation_errors += validate_net_event(event)

    return validation_errors


# returns a dictionary with keys 'errors' for events not associated with files
# and 'file_errors' for events that are associated with files
def validate_ctd_event(event: core_models.Event) -> [core_models.ValidationError]:

    validation_errors = []

    # Don't validate aborted events
    if event.actions.filter(type=core_models.ActionType.aborted).exists():
        return validation_errors

    # all CTD events should have a starting and ending ID
    if not event.sample_id:
        message = _("Missing a starting sample ID")
        err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
        validation_errors.append(err)

    if not event.end_sample_id:
        message = _("Missing an ending sample ID")
        err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
        validation_errors.append(err)

    if event.sample_id and event.end_sample_id:
        if event.end_sample_id < event.sample_id:
            message = _("End bottle id is less than the starting sample id")
            err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
            validation_errors.append(err)
        elif (event.end_sample_id-event.sample_id)+1 > 24:
            message = _("There are more than 24 bottles in this event")
            err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
            validation_errors.append(err)

    # CTD events should not have overlapping IDs
    ctd_events = event.mission.events.filter(instrument__type=core_models.InstrumentType.ctd).exclude(
        pk=event.id).exclude(actions__type=core_models.ActionType.aborted)
    if (evt := ctd_events.filter(
            sample_id__range=(event.sample_id, event.end_sample_id))).exists():
        message = _("Multiple overlapping samples for sample ids ") + f"[{event.sample_id} - {event.end_sample_id}] "
        message += _("Events") + "(" + ",".join([str(e) for e in evt]) + ")"
        err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
        validation_errors.append(err)

    return validation_errors


def validate_net_event(event: core_models.Event) -> [core_models.ValidationError]:
    database = event._state.db
    validation_errors = []

    # Don't validate aborted events
    if event.actions.filter(type=core_models.ActionType.aborted).exists():
        return validation_errors

    if not event.attachments.filter(Q(name__iexact='202um') | Q(name__iexact='76um')).exists():
        message = _("Nets must have a '202um' or '76um' attachment")
        err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
        validation_errors.append(err)
    elif not event.sample_id:
        message = _("Missing a starting sample ID")
        err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
        validation_errors.append(err)
    elif event.mission.start_date < datetime.strptime("2024-01-01", '%Y-%m-%d').date():
        if event.attachments.filter(name__iexact='76um').exists():
            ctd_events = core_models.Event.objects.using(database).filter(instrument__type=core_models.InstrumentType.ctd)
            if not ctd_events.filter(end_sample_id=event.sample_id).exists():
                message = _("No CTD event with matching surface bottle. "
                            "Check the deck sheet to confirm this is a surface bottle")
                message += f" : {event.sample_id}"
                possible_match =ctd_events.filter(sample_id__lte=event.sample_id, end_sample_id__gte=event.sample_id)
                if possible_match.exists():
                    message += _(", Likely matches event : ") + str(possible_match.first().event_id)

                err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
                validation_errors.append(err)
        elif event.attachments.filter(name__iexact='202um').exists():
            ctd_events = core_models.Event.objects.using(database).filter(instrument__type=core_models.InstrumentType.ctd)
            if not ctd_events.filter(sample_id=event.sample_id).exists():
                message = _("No CTD event with matching bottom bottle. "
                            "Check the deck sheet to confirm this is a bottom bottle")
                message += f" : {event.sample_id}"
                possible_match =ctd_events.filter(sample_id__lte=event.sample_id, end_sample_id__gte=event.sample_id)
                if possible_match.exists():
                    message += _(", Likely matches event : ") + str(possible_match.first().event_id)

                err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.validation)
                validation_errors.append(err)

    return validation_errors


def validate_bottle_sample_range(event: core_models.Event, bottle_id: int) -> \
        list[core_models.ValidationError]:
    errors = []
    if event.instrument.type == core_models.InstrumentType.ctd and \
            (bottle_id > event.end_sample_id or bottle_id < event.sample_id):
        message = f"Warning: Bottle ID ({bottle_id}) for event {event.event_id} " \
                  f"is outside the ID range {event.sample_id} - {event.end_sample_id}"
        err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.bottle)
        errors.append(err)

    return errors


def validate_samples_for_biochem(mission: core_models.Mission,
                                 sample_types: list[core_models.MissionSampleType] = None) -> list[core_models.Error]:
    errors = []

    # all samples for upload must have a Mission level datatype
    for sample_type in sample_types:
        if not sample_type.datatype:
            message = str(sample_type) + " : " + _("Sensor/Sample is missing a Biochem Datatype")
            err = core_models.Error(mission=mission, message=message, type=core_models.ErrorType.biochem)
            errors.append(err)

    return errors
