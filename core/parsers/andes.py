import io
import json
import logging

from datetime import datetime

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

import core.models
from settingsdb.models import FileConfiguration

from core import models as core_models

logger = logging.getLogger(f"dart.{__name__}")
logger_notifications = logging.getLogger('dart.user.andes')


def get_or_create_file_config() -> QuerySet[FileConfiguration]:
    file_type = 'andes_json'
    # These are all things the Elog parser requires, so we should probably figure out how to tackle them when reading
    # an Andes Report
    fields = [
        ("lead_scientists", "chief_scientist", _("Label identifying the chief scientists for the mission")),
        ("platform", "name", _("Label identifying the ship name used for the mission")),

        ("instrument_name", "name", _("Label identifying an instrument name")),
        ("instrument_type", "instrument_type", _("Label identifying an instrument type")),
        ("station_name", "station", _("Label identifying a station name")),
        ("event_id", "event_number", _("Label identifying the event number")),
        ("bottle_id", "uid", _("Label identifying the bottle ids for an event")),
        ("mesh_size", "mesh_size_um", _("Label identifying net mesh size for a plankton sample")),
        ("event_instrument_name", "instrument", _("Label identifying the name instrument an event is using")),
        ("sounding", "Sounding", _("Label identifying the sounding depth of the action")),
        ("wire_angle", "wire_angle", _("Label identifying the general angle of the wire for the event")),
        ("wire_out", "wire_out", _("Label identifying how much wire was unspooled for a net event")),
        ("flow_start", "flow_meter_start", _("Label for the starting value of a flowmeter for a net event")),
        ("flow_end", "flow_meter_end", _("Label for the ending value of a flowmeter for a net event")),

        ("action_type", "action_type", _("Label identifying an action type")),
        ("action_created_time", "created_at", _("Label identifying the date/time an action was created")),
        ("action_operator", "operator", _("Label identifying the operator who created the action")),
        ("action_comment", "comment", _("Label identifying the event comment to apply to actions")),
        ("action_lat", "latitude", _("Label identifying the latitude recorded for the action")),
        ("action_lon", "longitude", _("Label identifying the longitude recorded for the action")),
        ("action_sounding", "sounding", _("Label identifying the event sounding to apply to actions")),
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


def parse_instruments(mission: core_models.Mission, file_name: str, instruments: list[dict]) -> (
        list[core_models.FileError]):
    """
    Provided a list of instruments, CTD and Nets will be added to the mission's instrument table
    """
    logger_notifications.info("Processing Instruments")

    config: QuerySet[FileConfiguration] = get_or_create_file_config()
    database = mission._state.db

    errors = []

    for instrument in instruments:
        name = instrument[config.get(required_field='instrument_name').mapped_field]
        type_name = instrument[config.get(required_field='instrument_type').mapped_field]

        if type_name.lower() == 'plankton net':
            type_name = 'net'

        if not core_models.Instrument.objects.using(database).filter(name=name).exists():
            type = core_models.InstrumentType.other
            if core_models.InstrumentType.has_value(type_name):
                type = core_models.InstrumentType.get(type_name)

            core_models.Instrument.objects.using(database).create(name=name, type=type)

    return errors


def parse_stations(mission: core_models.Mission, file_name: str, samples: list[dict]) -> list[core_models.FileError]:

    config: QuerySet[FileConfiguration] = get_or_create_file_config()
    database = mission._state.db

    errors = []

    existing_stations = [stn.name.lower() for stn in core_models.Station.objects.using(database).all()]
    create_stations = {}
    station_count = len(samples)
    for index, station in enumerate(samples):
        logger_notifications.info("Processing stations %d/%d", index+1, station_count)
        name = station[config.get(required_field='station_name').mapped_field]

        if name.lower() not in existing_stations and name.lower() not in create_stations.keys():
            create_stations[name.lower()] = core_models.Station(name=name)

    core_models.Station.objects.using(database).bulk_create(create_stations.values())

    return errors


def parse_events(mission: core_models.Mission, file_name: str, samples: list[dict]) -> list[core_models.FileError]:
    # we're actually going to get the same list that stations gets because there are values in the 'samples'
    # list that we'll need for creating actions later.

    config: QuerySet[FileConfiguration] = get_or_create_file_config()
    database = mission._state.db

    stations = core_models.Station.objects.using(database).all()
    instruments = core_models.Instrument.objects.using(database).all()
    mission_events = core_models.Event.objects.using(database).all()

    errors = []
    create_events = {}
    update_events = {}
    update_fields = ['instrument', 'station', 'wire_out', 'wire_angle', 'flow_start', 'flow_end',
                     'sample_id', 'end_sample_id']

    add_attachments = {}

    station_count = len(samples)
    for index, sample in enumerate(samples):
        logger_notifications.info("Processing events %d/%d", index+1, station_count)

        station_name = sample[config.get(required_field='station_name').mapped_field]
        station = stations.get(name__iexact=station_name)

        events = sample['events']
        for event in events:
            event_id = event[config.get(required_field='event_id').mapped_field]
            instrument_name = event[config.get(required_field='event_instrument_name').mapped_field]
            type_name = event[config.get(required_field='instrument_type').mapped_field]

            if type_name.lower() == 'plankton net':
                type_name = 'net'

            type = core_models.InstrumentType.other
            if core_models.InstrumentType.has_value(type_name):
                type = core_models.InstrumentType.get(type_name)

            instrument = instruments.get(name__iexact=instrument_name, type=type)

            sample_id = None
            end_sample_id = None
            if instrument.type == core_models.InstrumentType.ctd:
                bottles = event.get('bottles', None)
                if bottles:
                    sample_id = bottles[0].get(config.get(required_field='bottle_id').mapped_field, None)
                    end_sample_id = bottles[-1].get(config.get(required_field='bottle_id').mapped_field, None)
            elif instrument.type == core_models.InstrumentType.net:
                bottles = event.get('plankton_samples', None)
                if bottles:
                    sample_id = bottles[0].get(config.get(required_field='bottle_id').mapped_field, None)
                    if len(bottles) > 1:  # > 1 bottle, this is a multinet
                        end_sample_id = bottles[-1].get(config.get(required_field='bottle_id').mapped_field, None)

                if 'mesh_size_um' in bottles[0]:
                    add_attachments[int(event_id)] = (
                        str(bottles[0].get(config.get(required_field='mesh_size').mapped_field, None)) + "um"
                    )

            if sample_id:
                try:
                    int(sample_id)
                except ValueError:
                    sample_id = None
                    message = _("Bad Bottle ID for Event : ") + str(event_id) + " " + _("Bottle ID : ") + str(sample_id)
                    err = core_models.FileError(mission=mission, file_name=file_name,
                                                message=message, type=core_models.ErrorType.event)
                    errors.append(err)
                    logger.error(message)
            wire_out_string = event.get(config.get(required_field='wire_out').mapped_field, None)
            wire_angle_string = event.get(config.get(required_field='wire_angle').mapped_field, None)
            flow_meter_start = event.get(config.get(required_field='flow_start').mapped_field, None)
            flow_meter_end = event.get(config.get(required_field='flow_end').mapped_field, None)

            wire_out = None
            if wire_out_string:
                if 'm' in wire_out_string:
                    wire_out = float(wire_out_string.split(' ')[0])
                else:
                    wire_out = float(wire_out_string)

            wire_angle = None
            if wire_angle_string:
                if 'degrees' in wire_angle_string:
                    wire_angle = float(wire_angle_string.split(' ')[0])
                else:
                    wire_angle = float(wire_angle_string)

            mission_event = None
            if not mission_events.filter(event_id=event_id).exists():
                if event_id not in create_events.keys():
                    mission_event = core_models.Event(mission=mission, event_id=event_id)

                    create_events[event_id] = mission_event
            else:
                mission_event = mission_events.get(event_id=event_id)
                mission_event.attachments.all().delete()
                update_events[event_id] = mission_event

            if mission_event:
                mission_event.instrument = instrument
                mission_event.station = station
                mission_event.wire_out = wire_out
                mission_event.wire_angle = wire_angle
                mission_event.flow_start = int(flow_meter_start) if flow_meter_start else None
                mission_event.flow_end = int(flow_meter_end) if flow_meter_end else None
                mission_event.sample_id = sample_id
                mission_event.end_sample_id = end_sample_id

    core_models.Event.objects.using(database).bulk_create(create_events.values())
    core_models.Event.objects.using(database).bulk_update(update_events.values(), update_fields)

    mission_events = {event.event_id: event for event in core_models.Event.objects.using(database).all()}
    create_attachments = []
    if add_attachments:
        for key, value in add_attachments.items():
            attachment = core_models.Attachment(event=mission_events[key], name=value)
            create_attachments.append(attachment)

    core_models.Attachment.objects.using(database).bulk_create(create_attachments)

    return errors


def parse_actions(mission: core_models.Mission, file_name: str, samples: list[dict]) -> list[core_models.FileError]:
    config: QuerySet[FileConfiguration] = get_or_create_file_config()
    database = mission._state.db

    errors = []

    mission_events = {event.event_id: event for event in mission.events.all()}
    create_actions = []

    station_count = len(samples)
    for index, sample in enumerate(samples):
        logger_notifications.info("Processing actions %d/%d", index+1, station_count)
        events = sample['events']
        action_operator = sample.get(config.get(required_field='action_operator').mapped_field, None)
        action_comment = sample.get(config.get(required_field='action_comment').mapped_field, None)
        action_sounding_string = sample.get(config.get(required_field='action_sounding').mapped_field, None)
        action_sounding = None
        if action_sounding_string:
            if 'm' in action_sounding_string:
                action_sounding = float(action_sounding_string.split(' ')[0])
            else:
                action_sounding = float(action_sounding_string)
        for event in events:
            event_id = event.get(config.get(required_field='event_id').mapped_field, None)
            mission_event = mission_events[event_id]
            mission_event.actions.all().delete()
            for action in event['actions']:
                action_type_string = action.get(config.get(required_field='action_type').mapped_field, None)
                action_time_string = action.get(config.get(required_field='action_created_time').mapped_field, None)
                action_lat_string = action.get(config.get(required_field='action_lat').mapped_field, None)
                action_lon_string = action.get(config.get(required_field='action_lon').mapped_field, None)

                try:
                    action_date = datetime.strptime(action_time_string, '%Y-%m-%d %H:%M:%S.%f%z')
                except ValueError:
                    action_date = datetime.strptime(action_time_string, '%Y-%m-%d %H:%M:%S%z')

                if action_type_string.lower() == 'recovery':
                    action_type_string = 'recovered'
                elif action_type_string.lower() == 'deploy':
                    action_type_string = 'deployed'

                action_lat = float(action_lat_string) if action_lat_string else None
                action_lon = float(action_lon_string) if action_lon_string else None
                action_type = core_models.ActionType.get(action_type_string)

                action = core_models.Action(event=mission_event, date_time=action_date, type=action_type,
                                            latitude=action_lat, longitude=action_lon, data_collector=action_operator,
                                            comment=action_comment, sounding=action_sounding, file=file_name)
                create_actions.append(action)

    core_models.Action.objects.using(database).bulk_create(create_actions)

    return errors


def parse(mission: core_models.Mission, file_name: str, stream: io.StringIO):
    """
    Parse a JSON formatted mission report outputed from the ANDES application

    Keyword arguments:
        mission -- The mission to add data to
        stream -- io.StringIO object reading from the file
    """

    config: QuerySet[FileConfiguration] = get_or_create_file_config()

    # Step 1 - read the file
    data = json.load(stream)
    database = mission._state.db
    core_models.FileError.objects.using(database).filter(file_name=file_name).delete()

    errors = []

    if not mission.lead_scientist or (mission.lead_scientist and mission.lead_scientist == 'N/A'):
        mission.lead_scientist = data['mission'].get(config.get(required_field='lead_scientists').mapped_field, "N/A")

    if not mission.platform or (mission.platform and mission.platform == 'N/A'):
        mission.platform = data['mission']['vessel'].get(config.get(required_field='platform').mapped_field, "N/A")

    mission.save()

    errors += parse_instruments(mission, file_name, data['mission']['instruments'])
    errors += parse_stations(mission, file_name, data['mission']['samples'])
    errors += parse_events(mission, file_name, data['mission']['samples'])
    errors += parse_actions(mission, file_name, data['mission']['samples'])

    core_models.FileError.objects.using(database).bulk_create(errors)
