import datetime
import io
import re

from enum import Enum

import dart.utils
from bio_tables import models as local_biochem_models
from core import models as core_models

from django.utils.translation import gettext_lazy as _

import logging

from dart.utils import convertDMS_degs

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.elog')


class ParserType(Enum):
    MID = 'mid'
    STATIONS = 'stations'
    INSTRUMENTS = 'Instruments'
    ERRORS = 'Errors'


# Validates that a field exists in a mid object's buffer and either raises an error or returns the mapped field
# from the elog configuration
def get_field(elog_configuration: core_models.ElogConfig, field: str, buffer: [str]) -> str:
    try:
        mapped_field = elog_configuration.mappings.get(field=field)
    except core_models.FileConfigurationMapping.DoesNotExist as e:
        required = False

        # if a mapping hasn't been set then create it from the default, this shouldn't happen unless a new field
        # was added and a user is using an existing deployment that was just updated from the git repo
        required_fields = {f[0]: (f[1], f[2]) for f in core_models.ElogConfig.required_fields}
        optional_fields = {f[0]: (f[1], f[2]) for f in core_models.ElogConfig.fields}
        if field in required_fields.keys():
            mapped_field = required_fields[field][0]
            purpose = required_fields[field][1]
            required = True
        elif field in optional_fields.keys():
            mapped_field = optional_fields[field][0]
            purpose = optional_fields[field][1]
        else:
            logger.exception(e)
            logger.error("Mapping for field does not exist in core.models.ElogConfig")
            raise e

        new_mapping = core_models.FileConfigurationMapping(
            field=field, mapped_to=mapped_field, required=required, purpose=purpose
        )
        elog_configuration.mappings.add(new_mapping)

    if mapped_field.required and mapped_field.mapped_to not in buffer:
        raise KeyError({'message': _('Message object missing key'), 'key': field, 'expected': mapped_field.mapped_to})

    return mapped_field.mapped_to


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


def process_stations(trip: core_models.Trip, station_queue: [str]) -> None:
    # create any stations on the stations queue that don't exist in the DB
    stations = []

    # we have to track stations that have been added, but not yet created in the database
    # in case there are duplicate stations in the station_queue
    added_stations = set()
    existing_stations = core_models.Station.objects.filter(mission=trip.mission)
    station_count = len(station_queue)
    for index, station in enumerate(station_queue):
        logger_notifications.info(_("Processing Stations") + " : %d/%d", (index + 1), station_count)
        stn = station.upper()
        if stn not in added_stations and not existing_stations.filter(name__iexact=stn).exists():
            added_stations.add(stn)
            stations.append(core_models.Station(mission=trip.mission, name=stn))

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


# sample id is valid if it's None or a number.
def valid_sample_id(sample_id):
    id = sample_id.strip() if sample_id else None

    if id and not id.isnumeric():
        return False

    return True


def process_instruments(trip: core_models.Trip, instrument_queue: [str]) -> None:
    # create any instruments on the instruments queue that don't exist in the DB
    instruments = []

    # track created instruments that are not yet in the DB, no duplications
    added_instruments = set()
    existing_instruments = core_models.Instrument.objects.filter(mission=trip.mission)
    instrument_count = len(instrument_queue)
    for index, instrument in enumerate(instrument_queue):
        logger_notifications.info(_("Processing Instruments") + " : %d/%d", (index + 1), instrument_count)
        if instrument.upper() not in added_instruments and \
                not existing_instruments.filter(name__iexact=instrument).exists():
            instrument_type = get_instrument_type(instrument_name=instrument)
            instruments.append(core_models.Instrument(mission=trip.mission, name=instrument, type=instrument_type))
            added_instruments.add(instrument.upper())

    core_models.Instrument.objects.bulk_create(instruments)


def process_events(trip: core_models.Trip, mid_dictionary_buffer: {}) -> [tuple]:
    errors = []

    elog_configuration = core_models.ElogConfig.get_default_config(trip.mission)

    existing_events = trip.events.all()

    # hopefully stations and instruments were created in bulk before hand
    stations = core_models.Station.objects.all()
    instruments = core_models.Instrument.objects.all()

    # messge objects are 'actions', and event can have multiple actions. Track event_ids for events we've just
    # created and only add events to the new_events queue if they haven't been previously processed
    processed_events = []

    create_events = {}
    update_events = []
    update_fields = set()

    mid_list = list(mid_dictionary_buffer.keys())
    mid_count = len(mid_list)
    for mid, buffer in mid_dictionary_buffer.items():
        index = mid_list.index(mid) + 1
        logger_notifications.info(_("Processing Event for Elog Message") + f" : %d/%d", index, mid_count)
        update_fields.add("")
        try:
            event_field = get_field(elog_configuration, 'event', buffer)
            station_field = get_field(elog_configuration, 'station', buffer)
            instrument_field = get_field(elog_configuration, 'instrument', buffer)
            sample_id_field = get_field(elog_configuration, 'start_sample_id', buffer)
            end_sample_id_field = get_field(elog_configuration, 'end_sample_id', buffer)
            wire_out_field = get_field(elog_configuration, 'wire_out', buffer)
            flow_start_field = get_field(elog_configuration, 'flow_start', buffer)
            flow_end_field = get_field(elog_configuration, 'flow_end', buffer)

            event_id = int(buffer[event_field])

            station = stations.get(name__iexact=buffer.pop(station_field), mission=trip.mission)
            instrument = instruments.get(name__iexact=buffer.pop(instrument_field), mission=trip.mission)
            sample_id: str = buffer.pop(sample_id_field)
            end_sample_id: str = buffer.pop(end_sample_id_field)

            wire_out: str = buffer.pop(wire_out_field) if wire_out_field in buffer else None
            flow_start: str = buffer.pop(flow_start_field) if flow_start_field in buffer else None
            flow_end: str = buffer.pop(flow_end_field) if flow_end_field in buffer else None

            if valid_sample_id(sample_id):
                sample_id = sample_id if sample_id.strip() else None
            else:
                message = _("Sample id is not valid")
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

            if flow_start is not None and flow_start != '' and ((stripped := flow_start.strip()) == '' or not stripped.isdigit()):
                message = _("Invalid flow meter start")
                errors.append((mid, message, ValueError({"message": message}),))
                flow_start = None

            if flow_end is not None and flow_end != '' and ((stripped := flow_end.strip()) == '' or not stripped.isdigit()):
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
                event = core_models.Event(trip=trip, event_id=event_id)
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
        core_models.Event.objects.bulk_create(create_events.values())

    if len(update_events) > 0:
        core_models.Event.objects.bulk_update(objs=update_events, fields=update_fields)

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


def process_attachments_actions(trip: core_models.Trip, mid_dictionary_buffer: {}, file_name: str) -> [tuple]:
    errors = []

    existing_events = trip.events.all()

    create_attachments = []
    create_actions = []
    update_actions = {'objects': [], 'fields': set()}

    cur_event = None

    elog_configuration = core_models.ElogConfig.get_default_config(trip.mission)

    mid_list = list(mid_dictionary_buffer.keys())
    mid_count = len(mid_list)
    for mid, buffer in mid_dictionary_buffer.items():
        index = mid_list.index(mid) + 1
        logger_notifications.info(_("Processing Attachments/Actions for Elog Message") + f" : %d/%d", index, mid_count)
        try:
            event_field = get_field(elog_configuration, 'event', buffer)
            attached_field = get_field(elog_configuration, 'attached', buffer)
            time_position_field = get_field(elog_configuration, 'time_position', buffer)
            comment_field = get_field(elog_configuration, 'comment', buffer)
            action_field = get_field(elog_configuration, 'action', buffer)
            data_collector_field = get_field(elog_configuration, 'data_collector', buffer)
            sounding_field = get_field(elog_configuration, 'sounding', buffer)

            event_id = buffer[event_field]
            action_type_text: str = map_action_text(buffer[action_field])
            action_type = core_models.ActionType.get(action_type_text)

            if not existing_events.filter(event_id=event_id).exists():
                # if an event doesn't exist there sould already be an error for why it wasn't created
                # if it doesn't exist here skip it.
                continue

            # We're done with these objects so remove them from the buffer
            attached_str = buffer.pop(attached_field)

            # if the time|position doesn't exist report the issue to the user, it may not have been set by mistake
            if re.search(".*\|.*\|.*\|.*", buffer[time_position_field]) is None:
                raise ValueError({'message': _("Badly formatted or missing Time|Position") + f"  $@MID@$ {mid}",
                                  'key': 'time_position',
                                  'expected': time_position_field})

            time_position = buffer.pop(time_position_field).split(" | ")
            comment = None
            if comment_field in buffer:
                comment = buffer.pop(comment_field)

            event = existing_events.get(event_id=event_id)

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

                try:
                    action.sounding = float(sounding)
                except ValueError:
                    action.sounding = None

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

    core_models.Attachment.objects.bulk_create(create_attachments)
    core_models.Action.objects.bulk_create(create_actions)
    if update_actions['fields']:
        core_models.Action.objects.bulk_update(objs=update_actions['objects'], fields=update_actions['fields'])

    return errors


def get_create_and_update_variables(trip: core_models.Trip, action: core_models.Action, buffer) -> [[], []]:
    variables_to_create = []
    variables_to_update = []
    for key, value in buffer.items():
        variable = core_models.VariableName.objects.get_or_create(mission=trip.mission, name=key)[0]
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
def process_variables(trip: core_models.Trip, mid_dictionary_buffer: {}) -> [tuple]:
    errors = []

    fields_create = []
    fields_update = []

    existing_actions = core_models.Action.objects.filter(event__trip=trip)

    elog_configuration = core_models.ElogConfig.get_default_config(trip.mission)

    update_mission = False
    if trip.mission.lead_scientist == 'N/A' or trip.platform == 'N/A' or trip.protocol == 'N/A':
        update_mission = True

    mid_list = list(mid_dictionary_buffer.keys())
    mid_count = len(mid_list)
    for mid, buffer in mid_dictionary_buffer.items():
        index = mid_list.index(mid) + 1
        logger_notifications.info(_("Processing Additional Variables for Elog Message") + f" : %d/%d", index, mid_count)
        try:
            lead_scientists_field = get_field(elog_configuration, 'lead_scientist', buffer)
            protocol_field = get_field(elog_configuration, 'protocol', buffer)
            cruise_field = get_field(elog_configuration, 'cruise', buffer)
            platform_field = get_field(elog_configuration, 'platform', buffer)

            lead_scientists: str = buffer.pop(lead_scientists_field)
            protocol: str = buffer.pop(protocol_field)
            cruise: str = buffer.pop(cruise_field)
            platform: str = buffer.pop(platform_field)

            if update_mission:
                if (lead_scientists and lead_scientists.strip() != '') and trip.mission.lead_scientist == 'N/A':
                    trip.mission.lead_scientist = lead_scientists
                    trip.mission.save()

                if (protocol and protocol.strip() != '') and trip.protocol == 'N/A':
                    # make sure the protocal isn't more than 50 characters if it's not 'AZMP' or 'AZOMP'
                    trip.protocol = protocol[:50]

                    proto = re.search('azmp', protocol, re.IGNORECASE)
                    if proto:
                        trip.protocol = 'AZMP'

                    proto = re.search('azomp', protocol, re.IGNORECASE)
                    if proto:
                        trip.protocol = 'AZOMP'

                if (platform and platform.strip() != '') and trip.platform == 'N/A':
                    trip.platform = platform

                if update_mission:
                    trip.save()

                update_mission = False
                if trip.platform == 'N/A' or trip.protocol == 'N/A':
                    update_mission = True

            action = existing_actions.get(mid=mid)
            # models.get_variable_name(name=k) is going to be a bottle neck if a variable doesn't already exist
            variables_arrays = get_create_and_update_variables(trip, action, buffer)
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
