import datetime
import io
import re

from enum import Enum

from django.db.models import QuerySet

import dart.utils
from settingsdb.models import FileConfiguration

from core import models as core_models

from django.utils.translation import gettext_lazy as _

import logging

from dart.utils import convertDMS_degs

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.elog')


def get_or_create_file_config() -> QuerySet[FileConfiguration]:
    file_type = 'elog'
    fields = [("event", "Event", _("Label identifying the elog event number")),
              ("time_position", "Time|Position", _("Label identifying the time|position string of an action")),
              ("station", "Station", _("Label identifying the station of the event")),
              ("action", "Action", _("Label identifying an elog action")),
              ("instrument", "Instrument", _("Label identifying the instrument of the event")),
              ('lead_scientist', 'PI', _("Label identifying the lead scientists of the mission")),
              ('protocol', "Protocol", _("Label identifying the protocol of the mission")),
              ('cruise', "Cruise", _("Label identifying the cruse name of the mission")),
              ("platform", "Platform", _("Label identifying the ship name used for the mission")),
              ("attached", "Attached", _("Label identifying accessories attached to equipment")),
              ("start_sample_id", "Sample ID", _("Label identifying a lone bottle, or starting bottle in a sequence")),
              ("end_sample_id", "End_Sample_ID", _("Label identifying the ending bottle in a sequence")),
              ("comment", "Comment", _("Label identifying an action comment")),
              ("data_collector", "Author", _("Label identifying who logged the elog action")),
              ("sounding", "Sounding", _("Label identifying the sounding depth of the action")),
              ("wire_out", "Wire out", _("Label identifying how much wire was unspooled for a net event")),
              ("flow_start", "Flowmeter Start", _("Label for the starting value of a flowmeter for a net event")),
              ("flow_end", "Flowmeter End", _("Label for the ending value of a flowmeter for a net event")),
              ]

    existing_mappings = FileConfiguration.objects.filter(file_type=file_type)
    create_mapping = []
    for field in fields:
        if not existing_mappings.filter(required_field=field[0]).exists():
            mapping = FileConfiguration(file_type=file_type)
            mapping.required_field = field[0]
            mapping.mapped_field = field[1]
            mapping.description = field[2]
            create_mapping.append(mapping)

    if len(create_mapping) > 0:
        FileConfiguration.objects.bulk_create(create_mapping)

    return existing_mappings


class ParserType(Enum):
    FILE = 'file'
    MID = 'mid'
    STATIONS = 'stations'
    INSTRUMENTS = 'Instruments'
    ERRORS = 'Errors'


def validate_buffer_fields(required_fields: list, mapped_fields: dict, mid, buffer: dict) -> list:
    field_errors = []
    keys = buffer.keys()
    for field in required_fields:
        if mapped_fields[field] in keys:
            continue

        ex = KeyError({'message': _('Message object missing key'),
                       'key': field, 'expected': mapped_fields[field]})
        logger.error(ex)
        field_errors.append((mid, ex.args[0]["message"], ex,))
    return field_errors


# Validate a message object ensuring it has all the required keys
# the queryset should be settingsdb.models.FileConfiguration.objects.filter(file_type='elog')
# loop over the queryset making sure the mapped_fields all exist in the buffer
def validate_message_object(elog_configuration: QuerySet[FileConfiguration], buffer: dict) -> [Exception]:
    errors = []
    for field in elog_configuration:
        if field.mapped_field not in buffer.keys():
            err = KeyError({'message': _('Message object missing key'),
                            'key': field.required_field, 'expected': field.mapped_field})
            errors.append(err)

    return errors


# updates the attribute (attr_key) of a given object (obj) with the new value (attr)
# if the existing value of obj.attr is equal to attr, nothing is done
# returns true if the object is updated, false otherwise
def set_attributes(obj, attr_key, attr) -> bool:
    update = False
    if hasattr(obj, attr_key) and getattr(obj, attr_key) != attr:
        setattr(obj, attr_key, attr)
        update = True

    return update


# updates multiple attributes of an object (obj). Any updates are added to the provided update dictionary,
# which has two elements.
#
# 'fields' indicating what fields were modified, if any
# 'objects' which is an array of modified objects
#
# This is specifically to work with Django's bulk update framework that requires the objects being modified
# and what fields for those objects were modified.
def update_attributes(obj, attributes: dict, update_dictionary: dict) -> None:
    update = False

    if obj in update_dictionary['objects']:
        update_dictionary['objects'].remove(obj)

    for attr_key, attribute in attributes.items():
        # we don't want to override values with blanks
        if attribute and set_attributes(obj, attr_key, attribute):
            update = True
            update_dictionary['fields'].add(attr_key)

    if update:
        update_dictionary['objects'].append(obj)


# parse an elog stream pulling out the mid events, stations, and instruments and report missing required key errors
def parse(file_name: str, stream: io.StringIO) -> dict:
    elog_configuration = get_or_create_file_config()

    message_object_buffer = {}
    file_mid_buffer = {file_name: []}
    errors = {}

    stations = set()
    instruments = set()

    # All mid objects start with $@MID@$ and end with a series of equal signs and a blank line.
    # Using regular expressions we'll split the whole stream in to mid objects, then process each object
    # each mid object represents an action, events are made up of multiple actions
    data = stream.read().strip().replace("\r\n", "\n")
    paragraph = re.split('====*\n\n', data)
    for mid in paragraph:

        # Each variable in a mid object starts with the label followed by a colon followed by the value
        tmp = re.findall('(.*?): *(.*?)\n', mid)

        # easily convert the (label, value) tuples into a dictionary
        buffer = dict(tmp)

        if '$@MID@$' not in buffer:
            raise LookupError({"message": _("Incorrectly formatted logfile missing $@MID@$ in paragraph"),
                               "paragraph": mid})

        # pop off the mid object number used to reference this process if there is an issue processing the mid object
        mid_obj = buffer.pop('$@MID@$')

        # validate the message object to ensure it has all the required fields
        # if not, save the errors to be returned and move on to the next message object
        mid_errors = validate_message_object(elog_configuration, buffer)
        if mid_errors:
            errors[mid_obj] = mid_errors
            continue

        message_object_buffer[mid_obj] = buffer
        file_mid_buffer[file_name].append(mid_obj)

        stations.add(buffer[elog_configuration.get(required_field='station').mapped_field])
        instruments.add(buffer[elog_configuration.get(required_field='instrument').mapped_field])

    message_objects = {
        # the file buffer says what objects belong to what file
        ParserType.FILE: file_mid_buffer,
        # the mid buffer contains the list of key, value pairs needed later for parsing data
        ParserType.MID: message_object_buffer,
        # the stations buffer has a set of stations
        ParserType.STATIONS: set(stations),
        # the instruments buffer has a set of instruments
        ParserType.INSTRUMENTS: set(instruments),
        # the error buffer is a dictionary with errors[mid]
        ParserType.ERRORS: errors
    }

    return message_objects


# parse multiple files for a given mission by parsing them individually and compressing their buffer
# dictionaries into one then run the algorithm to parse each section of the buffer dictionaries
def parse_files(mission, files):
    database = mission._state.db
    file_count = len(files)
    message_objects = {
        ParserType.FILE: dict(),
        ParserType.MID: dict(),
        ParserType.STATIONS: set(),
        ParserType.INSTRUMENTS: set(),
        ParserType.ERRORS: dict()
    }
    file_errors: [core_models.FileError] = []
    for index, file in enumerate(files):
        file_name = file.name
        # let the user know that we're about to start processing a file
        # send_user_notification_elog(group_name, mission, f'Processing file {process_message}')
        logger_notifications.info(_("Processing File") + " : %d/%d", (index + 1), file_count)

        # remove any existing errors for a log file of this name and update the interface
        mission.file_errors.filter(file_name=file_name).delete()

        try:
            data = file.read()
            file_message_objects = parse(file_name, io.StringIO(data.decode('utf-8')))

            # make note of missing required field errors in this file
            for mid, error_buffer in file_message_objects[ParserType.ERRORS].items():
                # Report errors to the user if there are any, otherwise process the message objects you can
                for error in error_buffer:
                    err = core_models.FileError(mission=mission, file_name=file_name, line=int(mid),
                                                type=core_models.ErrorType.event,
                                                message=f'Elog message object ($@MID@$: {mid}) missing required '
                                                        f'field [{error.args[0]["expected"]}]')
                    file_errors.append(err)

                    if mid in file_message_objects[ParserType.MID]:
                        file_message_objects[ParserType.MID].pop(mid)

            # merge the file_message_object buffer together

            message_objects[ParserType.FILE].update(file_message_objects[ParserType.FILE])
            message_objects[ParserType.MID].update(file_message_objects[ParserType.MID])
            message_objects[ParserType.STATIONS].update(file_message_objects[ParserType.STATIONS])
            message_objects[ParserType.INSTRUMENTS].update(file_message_objects[ParserType.INSTRUMENTS])
            message_objects[ParserType.ERRORS].update(file_message_objects[ParserType.ERRORS])

        except Exception as ex:
            if type(ex) is LookupError:
                logger.error(ex)
                err = core_models.FileError(mission=mission, type=core_models.ErrorType.event,
                                            file_name=file_name,
                                            message=ex.args[0]['message'] + ", " + _("see error.log for details"))
            else:
                # Something is really wrong with this file
                logger.exception(ex)
                err = core_models.FileError(mission=mission, type=core_models.ErrorType.event,
                                            file_name=file_name,
                                            message=_("Unknown error :") + f"{str(ex)}, " + _(
                                                "see error.log for details"))
            err.save()
            logger_notifications.info(_("File Error"))

            continue

    errors: [tuple] = []
    # send_user_notification_elog(group_name, mission, f"Process Stations {process_message}")
    process_stations(mission, message_objects[ParserType.STATIONS])

    # send_user_notification_elog(group_name, mission, f"Process Instruments {process_message}")
    process_instruments(mission, message_objects[ParserType.INSTRUMENTS])

    # send_user_notification_elog(group_name, mission, f"Process Events {process_message}")
    errors += process_events(mission, message_objects[ParserType.MID])

    # send_user_notification_elog(group_name, mission, f"Process Actions and Attachments {process_message}")
    errors += process_attachments_actions(mission, message_objects)

    # send_user_notification_elog(group_name, mission, f"Process Other Variables {process_message}")
    errors += process_variables(mission, message_objects[ParserType.MID])

    error_count = len(errors)
    for err, error in enumerate(errors):

        file_buffer: dict = message_objects[ParserType.FILE]
        file_name = None
        for file in file_buffer.keys():
            if error[0] in file_buffer[file]:
                file_name = file
                break

        logger_notifications.info(_("Recording Errors") + f" {file_name} : %d/%d", (err + 1), error_count)
        file_error = core_models.FileError(mission=mission, file_name=file_name, line=error[0], message=error[1])
        file_error.type = core_models.ErrorType.event
        file_errors.append(file_error)

    core_models.FileError.objects.using(database).bulk_create(file_errors)


def process_stations(mission: core_models.Mission, station_queue: [str]) -> None:
    # create any stations on the stations queue that don't exist in the DB
    stations = []
    database = mission._state.db

    # we have to track stations that have been added, but not yet created in the database
    # in case there are duplicate stations in the station_queue
    added_stations = set()
    existing_stations = core_models.Station.objects.using(database).all()
    station_count = len(station_queue)
    for index, station in enumerate(station_queue):
        logger_notifications.info(_("Processing Stations") + " : %d/%d", (index + 1), station_count)
        stn = station.upper()
        if stn not in added_stations and not existing_stations.filter(name__iexact=stn).exists():
            added_stations.add(stn)
            stations.append(core_models.Station(name=stn))

    core_models.Station.objects.using(database).bulk_create(stations)


def get_instrument_type(instrument_name: str) -> core_models.InstrumentType:
    try:
        # This is really only going to match if the instrument is a CTD or a VPR
        # if it's a type of net or buoy we'll have to see if we have a specific match in the
        # get_instrument_type method, which could be expanded later for other instruments
        # If the instrument doesn't match anyting in the get_instrument_type method
        # then the instrument is of type 'other'
        instrument_type = core_models.InstrumentType[instrument_name.lower()].value
        return instrument_type
    except KeyError:
        if instrument_name.upper() == "RINGNET":
            return core_models.InstrumentType.net

        if instrument_name.upper() == "VIKING BUOY":
            return core_models.InstrumentType.buoy

    return core_models.InstrumentType.other


# sample id is valid if it's None or a number.
def valid_sample_id(sample_id):
    id = sample_id.strip() if sample_id else None

    if id and not id.isnumeric():
        return False

    return True


def process_instruments(mission: core_models.Mission, instrument_queue: [str]) -> None:
    # create any instruments on the instruments queue that don't exist in the DB
    instruments = []
    database = mission._state.db

    # track created instruments that are not yet in the DB, no duplications
    added_instruments = set()
    existing_instruments = core_models.Instrument.objects.using(database).all()
    instrument_count = len(instrument_queue)
    for index, instrument in enumerate(instrument_queue):
        logger_notifications.info(_("Processing Instruments") + " : %d/%d", (index + 1), instrument_count)
        if instrument.upper() not in added_instruments and \
                not existing_instruments.filter(name__iexact=instrument).exists():
            instrument_type = get_instrument_type(instrument_name=instrument)
            instruments.append(core_models.Instrument(name=instrument, type=instrument_type))
            added_instruments.add(instrument.upper())

    core_models.Instrument.objects.using(database).bulk_create(instruments)


def process_events(mission: core_models.Mission, mid_dictionary_buffer: {}) -> [tuple]:
    database = mission._state.db
    errors = []

    elog_configuration = get_or_create_file_config()

    existing_events = mission.events.all()

    # hopefully stations and instruments were created in bulk before hand
    stations = core_models.Station.objects.using(database).all()
    instruments = core_models.Instrument.objects.using(database).all()

    # messge objects are 'actions', and event can have multiple actions. Track event_ids for events we've just
    # created and only add events to the new_events queue if they haven't been previously processed
    processed_events = []

    create_events = {}
    update_events = []
    update_fields = set()

    required_fields = ['event', 'station', 'instrument', 'start_sample_id', 'end_sample_id', 'wire_out', 'flow_start',
                       'flow_end']
    mapped_fields = {field.required_field: field.mapped_field for field in
                     elog_configuration.filter(required_field__in=required_fields)}

    mid_list = list(mid_dictionary_buffer.keys())
    mid_count = len(mid_list)
    for mid, buffer in mid_dictionary_buffer.items():
        index = mid_list.index(mid) + 1
        logger_notifications.info(_("Processing Event for Elog Message") + f" : %d/%d", index, mid_count)
        update_fields.add("")
        try:
            field_errors = validate_buffer_fields(required_fields, mapped_fields, mid, buffer)
            if len(field_errors) > 0:
                # if there are missing fields report the errors and move on to the next message
                errors += field_errors
                continue

            event_id = int(buffer[mapped_fields['event']])

            station = stations.get(name__iexact=buffer.pop(mapped_fields['station']))
            instrument = instruments.get(name__iexact=buffer.pop(mapped_fields['instrument']))
            sample_id: str = buffer.pop(mapped_fields['start_sample_id'])
            end_sample_id: str = buffer.pop(mapped_fields['end_sample_id'])

            wire_out: str = buffer.pop(mapped_fields['wire_out']) if mapped_fields['wire_out'] in buffer else None
            flow_start: str = buffer.pop(mapped_fields['flow_start']) if mapped_fields['flow_start'] in buffer else None
            flow_end: str = buffer.pop(mapped_fields['flow_end']) if mapped_fields['flow_end'] in buffer else None

            if valid_sample_id(sample_id):
                sample_id = sample_id if sample_id.strip() else None
            else:
                message = _("Sample id is not valid") + f" - {sample_id}"
                errors.append((mid, message, ValueError({"message": message}),))
                sample_id = None

            if valid_sample_id(end_sample_id):
                end_sample_id = end_sample_id if end_sample_id.strip() else None
            else:
                message = _("End Sample id is not valid")
                errors.append((mid, message, ValueError({"message": message}),))
                end_sample_id = None

            # we have to test that wire_out, flow_start and flow_end are numbers because someone might enter
            # a unit on the value i.e '137.4m' which will then crash the function when bulk creating/updating the
            # events. If the numbers aren't valid numbers then set the field blank and report the error.
            if wire_out is not None and wire_out != '' and \
                    ((stripped := wire_out.strip()) == '' or not stripped.replace('.', '', 1).isdigit()):
                message = _("Invalid wire out value")
                errors.append((mid, message, ValueError({"message": message}),))
                wire_out = None

            if flow_start is not None and flow_start != '' and (
                    (stripped := flow_start.strip()) == '' or not stripped.isdigit()):
                message = _("Invalid flow meter start")
                errors.append((mid, message, ValueError({"message": message}),))
                flow_start = None

            if flow_end is not None and flow_end != '' and (
                    (stripped := flow_end.strip()) == '' or not stripped.isdigit()):
                message = _("Invalid flow meter end")
                errors.append((mid, message, ValueError({"message": message}),))
                flow_end = None

            # if the event doesn't already exist, create it. Otherwise update the existing
            # event with new data if required
            if exists := existing_events.filter(event_id=event_id).exists():
                event = existing_events.get(event_id=event_id)
                if event in update_events:
                    idx = update_events.index(event)
                    event = update_events.pop(idx)
            elif event_id in create_events.keys():
                event = create_events[event_id]
            else:
                event = core_models.Event(mission=mission, event_id=event_id)
                create_events[event_id] = event

            # only override values if the new value is not none. If a value was set as part of a previous action
            # then we'll keep that previous actions value so as to not null out values that were in a deployed
            # action, but might be missing from a recovered action.
            station = station if station else event.station
            instrument = instrument if instrument else event.instrument
            sample_id = sample_id if sample_id else event.sample_id
            end_sample_id = end_sample_id if end_sample_id else event.end_sample_id
            wire_out = wire_out if wire_out else event.wire_out
            flow_start = flow_start if flow_start else event.flow_start
            flow_end = flow_end if flow_end else event.flow_end

            update_fields.add(dart.utils.updated_value(event, 'station_id', station.pk))
            update_fields.add(dart.utils.updated_value(event, 'instrument_id', instrument.pk))
            update_fields.add(dart.utils.updated_value(event, 'sample_id', sample_id))
            update_fields.add(dart.utils.updated_value(event, 'end_sample_id', end_sample_id))
            update_fields.add(dart.utils.updated_value(event, 'wire_out', wire_out))
            update_fields.add(dart.utils.updated_value(event, 'flow_start', flow_start))
            update_fields.add(dart.utils.updated_value(event, 'flow_end', flow_end))

            update_fields.remove('')

            if len(update_fields) > 0:
                if exists:
                    update_events.append(event)
                else:
                    create_events[event_id] = event

        except KeyError as ex:
            logger.error(ex)
            errors.append((mid, ex.args[0]["message"], ex,))
        except Exception as ex:
            message = _("Error processing events, see error.log for details")
            if 'message' in ex.args[0]:
                message = ex.args[0]["message"]
            logger.exception(ex)
            errors.append((mid, message, ex,))

    if len(create_events) > 0:
        core_models.Event.objects.using(database).bulk_create(create_events.values())

    if len(update_events) > 0:
        core_models.Event.objects.using(database).bulk_update(objs=update_events, fields=update_fields)

    return errors


# Some labels for actions in Elog are free text, so a user could use 'Deploy' instead of 'Deployed'
# this function will map common variations of actions to expected values
def map_action_text(text: str) -> str:
    if text is None:
        return text

    lower_text = text.lower()
    if lower_text == 'deploy':
        return "Deployed"

    if lower_text == 'recovery':
        return "Recovered"

    return text


def process_attachments_actions(mission: core_models.Mission, dictionary_buffer: {}) -> [tuple]:
    database = mission._state.db
    errors = []

    existing_events = {event.event_id: event for event in mission.events.all()}

    create_attachments = []
    create_actions = []
    update_actions = {'objects': [], 'fields': set()}

    cur_event = None

    elog_configuration = get_or_create_file_config()

    mid_dictionary_buffer = dictionary_buffer[ParserType.MID]
    mid_list = list(mid_dictionary_buffer.keys())
    mid_count = len(mid_list)

    required_fields = ['event', 'attached', 'time_position', 'comment', 'action', 'data_collector', 'sounding']
    mapped_fields = {field.required_field: field.mapped_field for field in
                     elog_configuration.filter(required_field__in=required_fields)}

    for mid, buffer in mid_dictionary_buffer.items():
        index = mid_list.index(mid) + 1
        logger_notifications.info(_("Processing Attachments/Actions for Elog Message") + f" : %d/%d", index, mid_count)
        try:
            field_errors = validate_buffer_fields(required_fields, mapped_fields, mid, buffer)
            if len(field_errors) > 0:
                # if there are missing fields report the errors and move on to the next message
                errors += field_errors
                continue

            event_id = buffer[mapped_fields['event']]
            if event_id.isnumeric():
                event_id = int(event_id)

            action_type_text: str = map_action_text(buffer[mapped_fields['action']])
            action_type = core_models.ActionType.get(action_type_text)

            if event_id not in existing_events.keys():
                # if an event doesn't exist there should already be an error for why it wasn't created
                # if it doesn't exist here skip it.
                continue

            # We're done with these objects so remove them from the buffer
            attached_str = buffer.pop(mapped_fields['attached'])

            # if the time|position doesn't exist report the issue to the user, it may not have been set by mistake
            if re.search(".*\|.*\|.*\|.*", buffer[mapped_fields['time_position']]) is None:
                raise ValueError({'message': _("Badly formatted or missing Time|Position") + f"  $@MID@$ {mid}",
                                  'key': 'time_position',
                                  'expected': mapped_fields['time_position']})

            time_position = buffer.pop(mapped_fields['time_position']).split(" | ")
            comment = None
            if mapped_fields['comment'] in buffer:
                comment = buffer.pop(mapped_fields['comment'])

            event = existing_events[event_id]

            if cur_event != event_id:
                # if this is a new event, or an event that's seen for the first time, clear it's actions and
                # attachments so we don't end up with duplicate actions and attachments if the event is
                # being reloaded
                event.attachments.all().delete()
                event.actions.all().delete()

                attached = attached_str.split(" | ")
                for a in attached:
                    if a.strip() != '':
                        if not event.attachments.filter(name=a).exists():
                            create_attachments.append(core_models.Attachment(event=event, name=a))
                cur_event = event_id

            # this is a 'naive' date time with no time zone. But it should always be in UTC
            time_part = f"{time_position[1][0:2]}:{time_position[1][2:4]}:{time_position[1][4:6]}"
            date_time = datetime.datetime.strptime(f"{time_position[0]} {time_part} +00:00", '%Y-%m-%d %H:%M:%S %z')

            lat = convertDMS_degs(time_position[2])
            lon = convertDMS_degs(time_position[3])

            data_collector = buffer[mapped_fields['data_collector']]
            sounding = buffer[mapped_fields['sounding']]

            # if an event already contains this action, we'll update it
            if event.actions.filter(type=action_type).exists():
                action = event.actions.get(mid=mid)

                attrs = {
                    'latitude': lat,
                    'longitude': lon,
                    'comment': comment,
                    'data_collector': data_collector,
                    'sounding': sounding
                }
                if action_type == core_models.ActionType.other:
                    attrs['action_type_other'] = action_type_text

                update_attributes(action, attrs, update_actions)

            else:
                file_buffer: dict[list] = dictionary_buffer[ParserType.FILE]
                file_name = None
                for file in file_buffer.keys():
                    if mid in file_buffer[file]:
                        file_name = file
                        break
                action = core_models.Action(file=file_name, event=event, date_time=date_time, mid=mid,
                                            latitude=lat, longitude=lon, type=action_type)

                # add on our optional fields if they exist
                if data_collector and data_collector != "":
                    action.data_collector = data_collector

                if comment and comment != "":
                    action.comment = comment

                try:
                    action.sounding = float(sounding)
                except ValueError:
                    action.sounding = None

                if action_type == core_models.ActionType.other:
                    action.action_type_other = action_type_text

                create_actions.append(action)
        except ValueError as ex:
            message = _("Missing or improperly set attribute, see error.log for details") + f" $@MID@$ {mid}"
            if 'message' in ex.args[0]:
                message = ex.args[0]['message']

            logger.error(f"{message} - {ex}")
            errors.append((mid, message, ex,))
        except Exception as ex:
            message = _("Error processing attachments, see error.log for details") + f" $@MID@$ {mid}"
            logger.exception(ex)
            errors.append((mid, message, ex,))

    core_models.Attachment.objects.using(database).bulk_create(create_attachments)
    core_models.Action.objects.using(database).bulk_create(create_actions)
    if update_actions['fields']:
        core_models.Action.objects.using(database).bulk_update(objs=update_actions['objects'],
                                                               fields=update_actions['fields'])

    return errors


def get_create_and_update_variables(mission: core_models.Mission, action: core_models.Action, buffer) -> [[], []]:
    database = mission._state.db
    variables_to_create = []
    variables_to_update = []
    for key, value in buffer.items():
        variable = core_models.VariableName.objects.using(database).get_or_create(name=key)[0]
        filtered_variables = action.variables.filter(name=variable)
        if not filtered_variables.exists():
            new_variable = core_models.VariableField(action=action, name=variable, value=value)
            variables_to_create.append(new_variable)
        else:
            update_variable = filtered_variables[0]
            update_variable.value = value
            variables_to_update.append(update_variable)

    return [variables_to_create, variables_to_update]


# Anything that wasn't consumed by the other process methods will be considered a variable and attached to
# the action it falls under. This way users can still query an action for a variable even if DART doesn't do
# anything with it.
def process_variables(mission: core_models.Mission, mid_dictionary_buffer: {}) -> [tuple]:
    database = mission._state.db
    errors = []

    fields_create = []
    fields_update = []

    existing_actions = {str(action.mid): action for action in
                        core_models.Action.objects.using(database).filter(event__mission=mission)}

    elog_configuration = get_or_create_file_config()
    required_fields = ['lead_scientist', 'protocol', 'cruise', 'platform']
    mapped_fields = {field.required_field: field.mapped_field for field in
                     elog_configuration.filter(required_field__in=required_fields)}

    update_mission = False
    if mission.lead_scientist == 'N/A' or mission.platform == 'N/A' or mission.protocol == 'N/A':
        update_mission = True

    mid_list = list(mid_dictionary_buffer.keys())
    mid_count = len(mid_list)
    for mid, buffer in mid_dictionary_buffer.items():
        index = mid_list.index(mid) + 1
        logger_notifications.info(_("Processing Additional Variables for Elog Message") + f" : %d/%d", index, mid_count)
        try:
            # lead_scientists_field = get_field(elog_configuration, 'lead_scientist', buffer)
            # protocol_field = get_field(elog_configuration, 'protocol', buffer)
            # cruise_field = get_field(elog_configuration, 'cruise', buffer)
            # platform_field = get_field(elog_configuration, 'platform', buffer)
            field_errors = validate_buffer_fields(required_fields, mapped_fields, mid, buffer)
            if len(field_errors) > 0:
                # if there are missing fields report the errors and move on to the next message
                errors += field_errors
                continue

            lead_scientists: str = buffer.pop(mapped_fields['lead_scientist'])
            protocol: str = buffer.pop(mapped_fields['protocol'])
            cruise: str = buffer.pop(mapped_fields['cruise'])
            platform: str = buffer.pop(mapped_fields['platform'])

            if update_mission:
                if (lead_scientists and lead_scientists.strip() != '') and mission.lead_scientist == 'N/A':
                    mission.lead_scientist = lead_scientists
                    mission.save(using=database)

                if (protocol and protocol.strip() != '') and mission.protocol == 'N/A':
                    # make sure the protocal isn't more than 50 characters if it's not 'AZMP' or 'AZOMP'
                    mission.protocol = protocol[:50]

                    proto = re.search('azmp', protocol, re.IGNORECASE)
                    if proto:
                        mission.protocol = 'AZMP'

                    proto = re.search('azomp', protocol, re.IGNORECASE)
                    if proto:
                        mission.protocol = 'AZOMP'

                if (platform and platform.strip() != '') and mission.platform == 'N/A':
                    mission.platform = platform

                if update_mission:
                    mission.save(using=database)

                update_mission = False
                if mission.platform == 'N/A' or mission.protocol == 'N/A':
                    update_mission = True

            if mid in existing_actions.keys():
                action = existing_actions[mid]
                # models.get_variable_name(name=k) is going to be a bottle neck if a variable doesn't already exist
                variables_arrays = get_create_and_update_variables(mission, action, buffer)
                fields_create += variables_arrays[0]
                fields_update += variables_arrays[1]
        except KeyError as ex:
            logger.error(ex)
            errors.append((mid, ex.args[0]["message"], ex,))
        except Exception as ex:
            message = _("Error processing variables, see error.log for details")
            logger.exception(ex)
            errors.append((mid, message, ex,))

    core_models.VariableField.objects.using(database).bulk_create(fields_create)
    core_models.VariableField.objects.using(database).bulk_update(objs=fields_update, fields=['value'])

    return errors
