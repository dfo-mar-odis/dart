import datetime
import io
import re

from enum import Enum

from bio_tables import models as local_biochem_models
from core import models as core_models

from django.utils.translation import gettext_lazy as _

import logging

from dart2.utils import convertDMS_degs

logger = logging.getLogger('dart')


class ParserType(Enum):
    MID = 'mid'
    STATIONS = 'stations'
    INSTRUMENTS = 'Instruments'
    ERRORS = 'Errors'


# Validates that a field exists in a mid object's buffer and either raises an error or returns the mapped field
# from the elog configuration
def get_field(elog_configuration: core_models.ElogConfig, field: str, buffer: [str]) -> str:
    mapped_field = elog_configuration.get_mapping(field)

    if mapped_field not in buffer:
        raise KeyError({'message': _('Message object missing key'), 'key': field, 'expected': mapped_field})

    return mapped_field


# Validate a message object ensuring it has all the required keys
def validate_message_object(elog_configuration: core_models.ElogConfig, buffer: dict) -> [Exception]:
    errors = []
    required_fields = elog_configuration.mappings.filter(required=True)
    for field in required_fields:
        try:
            get_field(elog_configuration, field.field, buffer)
        except KeyError as ex:
            errors.append(ex)

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
    for attr_key, attribute in attributes.items():
        if set_attributes(obj, attr_key, attribute):
            update = True
            update_dictionary['fields'].add(attr_key)

    if update:
        update_dictionary['objects'].append(obj)


# parse an elog stream pulling out the mid events, stations, and instruments and report missing required key errors
def parse(stream: io.StringIO, elog_configuration: core_models.ElogConfig) -> dict:
    mids = {}
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

        mids[mid_obj] = buffer

        stations.add(buffer[elog_configuration.get_mapping('station')])
        instruments.add(buffer[elog_configuration.get_mapping('instrument')])

    message_objects = {ParserType.MID: mids, ParserType.STATIONS: list(stations),
                       ParserType.INSTRUMENTS: list(instruments), ParserType.ERRORS: errors}

    return message_objects


def process_stations(station_queue: [str]) -> None:
    # create any stations on the stations queue that don't exist in the DB
    stations = []

    # we have to track stations that have been added, but not yet created in the database
    # in case there are duplicate stations in the station_queue
    added_stations = set()
    existing_stations = core_models.Station.objects.all()
    for station in station_queue:
        stn = station.upper()
        if stn not in added_stations and not existing_stations.filter(name__iexact=stn).exists():
            added_stations.add(stn)
            stations.append(core_models.Station(name=stn))

    core_models.Station.objects.bulk_create(stations)


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


def get_instrument(instrument_name: str) -> core_models.Instrument:
    # this will be faster if instruments were pre-processed and created in bulk, otherwise they'll have to be added
    # one at a time and it will be very slow
    instruments = core_models.Instrument.objects.filter(name__iexact=instrument_name)
    if instruments.exists():
        return instruments[0]

    process_instruments([instrument_name])
    return core_models.Instrument.objects.get(name=instrument_name)


def process_instruments(instrument_queue: [str]) -> None:
    # create any instruments on the instruments queue that don't exist in the DB
    instruments = []

    # track created instruments that are not yet in the DB, no duplications
    added_instruments = set()
    existing_instruments = core_models.Instrument.objects.all()
    for instrument in instrument_queue:
        if instrument.upper() not in added_instruments and \
                not existing_instruments.filter(name__iexact=instrument).exists():
            instrument_type = get_instrument_type(instrument_name=instrument)
            instruments.append(core_models.Instrument(name=instrument, type=instrument_type))
            added_instruments.add(instrument.upper())

    core_models.Instrument.objects.bulk_create(instruments)


def process_events(mid_dictionary_buffer: {}, mission: core_models.Mission) -> [tuple]:
    errors = []

    elog_configuration = core_models.ElogConfig.get_default_config(mission)

    existing_events = mission.events.all()

    # hopefully stations and instruments were created in bulk before hand
    stations = core_models.Station.objects.all()
    instruments = core_models.Instrument.objects.all()

    # messge objects are 'actions', and event can have multiple actions. Track event_ids for events we've just
    # created and only add events to the new_events queue if they haven't been previously processed
    processed_events = []
    new_events = []

    create_events = []
    update_events = {'objects': [], 'fields': set()}

    for mid, buffer in mid_dictionary_buffer.items():
        try:
            event_field = get_field(elog_configuration, 'event', buffer)
            station_field = get_field(elog_configuration, 'station', buffer)
            instrument_field = get_field(elog_configuration, 'instrument', buffer)
            sample_id_field = get_field(elog_configuration, 'start_sample_id', buffer)
            end_sample_id_field = get_field(elog_configuration, 'end_sample_id', buffer)

            event_id = int(buffer[event_field])
            if event_id in processed_events:
                continue

            station = stations.get(name__iexact=buffer.pop(station_field))
            instrument = instruments.get(name__iexact=buffer.pop(instrument_field))
            sample_id: str = buffer.pop(sample_id_field)
            end_sample_id: str = buffer.pop(end_sample_id_field)

            # if the event doesn't already exist, create it. Otherwise update the existing
            # event with new data if required
            if not existing_events.filter(event_id=event_id).exists():
                new_event = core_models.Event(mission=mission, event_id=event_id)

                new_event.station = station
                new_event.instrument = instrument

                # sample IDs are optional fields, they may be blank. If they are they should be None on the event
                new_event.sample_id = sample_id if sample_id.strip() else None
                new_event.end_sample_id = end_sample_id if end_sample_id.strip() else None

                new_events.append(event_id)
                create_events.append(new_event)
            else:
                attrs = {
                    'station': station,
                    'instrument': instrument,
                    'sample_id': sample_id if sample_id.strip() else None,
                    'end_sample_id': end_sample_id if end_sample_id.strip() else None
                }
                event = existing_events.get(event_id=event_id)
                update_attributes(event, attrs, update_events)

            processed_events.append(event_id)
        except KeyError as ex:
            logger.error(ex)
            errors.append((mid, ex.args[0]["message"], ex,))
        except Exception as ex:
            message = _("Error processing events, see error.log for details")
            logger.exception(ex)
            errors.append((mid, message, ex,))

    core_models.Event.objects.bulk_create(create_events)
    if update_events['fields']:
        core_models.Event.objects.bulk_update(objs=update_events['objects'], fields=update_events['fields'])

    return errors


def process_attachments_actions(mid_dictionary_buffer: {}, mission: core_models.Mission, file_name: str) -> [tuple]:
    errors = []

    existing_events = mission.events.all()

    create_attachments = []
    create_actions = []
    update_actions = {'objects': [], 'fields': set()}

    cur_event = None

    elog_configuration = core_models.ElogConfig.get_default_config(mission)

    for mid, buffer in mid_dictionary_buffer.items():
        try:
            event_field = get_field(elog_configuration, 'event', buffer)
            attached_field = get_field(elog_configuration, 'attached', buffer)
            time_position_field = get_field(elog_configuration, 'time_position', buffer)
            comment_field = get_field(elog_configuration, 'comment', buffer)
            action_field = get_field(elog_configuration, 'action', buffer)
            data_collector_field = get_field(elog_configuration, 'data_collector', buffer)
            sounding_field = get_field(elog_configuration, 'sounding', buffer)

            event_id = buffer[event_field]
            action_type_text = buffer[action_field]
            action_type = core_models.ActionType.get(action_type_text)

            # We're done with these objects so remove them from the buffer
            attached_str = buffer.pop(attached_field)

            # if the time|position doesn't exist report the issue to the user, it may not have been set by mistake
            if re.search(".*\|.*\|.*\|.*", buffer[time_position_field]) is None:
                raise ValueError({'message': _("Badly formatted or missing Time|Position") + f"  $@MID@$ {mid}",
                                  'key': 'time_position',
                                  'expected': time_position_field})

            time_position = buffer.pop(time_position_field).split(" | ")
            comment = buffer.pop(comment_field)

            event = existing_events.get(event_id=event_id)

            if cur_event != event_id:
                attached = attached_str.split(" | ")
                for a in attached:
                    if a.strip() != '':
                        if not event.attachments.filter(name=a).exists():
                            create_attachments.append(core_models.InstrumentSensor(event=event, name=a))
                cur_event = event_id

            # this is a 'naive' date time with no time zone. But it should always be in UTC
            time_part = f"{time_position[1][0:2]}:{time_position[1][2:4]}:{time_position[1][4:6]}"
            date_time = datetime.datetime.strptime(f"{time_position[0]} {time_part} +00:00", '%Y-%m-%d %H:%M:%S %z')

            lat = convertDMS_degs(time_position[2])
            lon = convertDMS_degs(time_position[3])

            data_collector = buffer[data_collector_field]
            sounding = buffer[sounding_field]

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
                action = core_models.Action(file=file_name, event=event, date_time=date_time, mid=mid,
                                            latitude=lat, longitude=lon, type=action_type)

                # add on our optional fields if they exist
                if data_collector and data_collector != "":
                    action.data_collector = data_collector

                if comment and comment != "":
                    action.comment = comment

                if sounding and sounding != "" and str(sounding).isnumeric():
                    action.sounding = sounding

                if action_type == core_models.ActionType.other:
                    action.action_type_other = action_type_text

                create_actions.append(action)
        except KeyError as ex:
            logger.error(ex)
            errors.append((mid, ex.args[0]["message"], ex,))
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

    core_models.InstrumentSensor.objects.bulk_create(create_attachments)
    core_models.Action.objects.bulk_create(create_actions)
    if update_actions['fields']:
        core_models.Action.objects.bulk_update(objs=update_actions['objects'], fields=update_actions['fields'])

    return errors


def get_create_and_update_variables(action, buffer) -> [[], []]:
    variables_to_create = []
    variables_to_update = []
    for key, value in buffer.items():
        variable = core_models.VariableName.objects.get_or_create(name=key)[0]
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
def process_variables(mid_dictionary_buffer: {}, mission: core_models.Mission) -> [tuple]:
    errors = []

    fields_create = []
    fields_update = []

    existing_actions = core_models.Action.objects.filter(event__mission=mission)

    elog_configuration = core_models.ElogConfig.get_default_config(mission)

    for mid, buffer in mid_dictionary_buffer.items():
        try:
            lead_scientists_field = get_field(elog_configuration, 'lead_scientist', buffer)
            protocol_field = get_field(elog_configuration, 'protocol', buffer)
            cruise_field = get_field(elog_configuration, 'cruise', buffer)
            platform_field = get_field(elog_configuration, 'platform', buffer)

            lead_scientists = buffer.pop(lead_scientists_field)
            protocol = buffer.pop(protocol_field)
            cruise = buffer.pop(cruise_field)
            platform = buffer.pop(platform_field)

            if mission.lead_scientist == 'N/A':
                # This is all stuff that should be optionally added to the create mission form
                mission.lead_scientist = lead_scientists
                mission.protocol = protocol
                mission.cruise = cruise
                mission.platform = platform
                mission.mission_descriptor = f'18{cruise}'
                mission.data_center = local_biochem_models.BCDataCenter.objects.get(pk=20)  # 20 is BIO
                mission.save()

                action = existing_actions.get(mid=mid)
                # models.get_variable_name(name=k) is going to be a bottle neck if a variable doesn't already exist
                variables_arrays = get_create_and_update_variables(action, buffer)
                fields_create += variables_arrays[0]
                fields_update += variables_arrays[1]
        except KeyError as ex:
            logger.error(ex)
            errors.append((mid, ex.args[0]["message"], ex,))
        except Exception as ex:
            message = _("Error processing variables, see error.log for details")
            logger.exception(ex)
            errors.append((mid, message, ex,))

    core_models.VariableField.objects.bulk_create(fields_create)
    core_models.VariableField.objects.bulk_update(objs=fields_update, fields=['value'])

    return errors
