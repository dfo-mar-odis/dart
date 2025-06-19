import pandas as pd
import io

from core import models
from core.models import ActionType
from settingsdb import models as settings_models

import logging

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.csv')


def parse(mission: models.Mission, file_name: str, data: io.StringIO):
    data_frame = pd.read_csv(data, na_filter=False)
    data_frame.columns = data_frame.columns.str.upper()

    # Process stations and instruments
    stations = data_frame['STATION'].unique().tolist()
    process_stations(stations)

    instruments = instrument_pairs = data_frame[['INSTRUMENT_NAME','INSTRUMENT_TYPE']].drop_duplicates().values.tolist()
    process_instruments(instruments)

    # Step 1: Create events first (one per unique EVENT_ID)
    logger_notifications.info("Processing Events")

    # Get only the first occurrence of each EVENT_ID for event creation
    event_columns = ['EVENT_ID', 'STATION', 'INSTRUMENT_NAME', 'INSTRUMENT_TYPE', 'STARTING_ID', 'ENDING_ID',
                     'WIRE_ANGLE', 'WIRE_OUT', 'FLOW_DEPLOY', 'FLOW_RECOVER']
    events_df = data_frame[event_columns].drop_duplicates(subset=['EVENT_ID'])

    # Create all events
    events_map = {}  # Map of event_id to Event object for quick lookup

    total_rows = events_df.shape[0]
    processed = 1
    create_events = []
    update_events = []
    for index, row in events_df.iterrows():
        if processed % 10 == 0 or processed == total_rows:
            logger_notifications.info("Processing Events: %d/%d", processed, total_rows)

        station = models.Station.objects.get(name__iexact=row['STATION'])
        inst_type = get_instrument_type(row['INSTRUMENT_TYPE'])
        instrument = models.Instrument.objects.get(name__iexact=row['INSTRUMENT_NAME'], type=inst_type)

        try:
            event = models.Event.objects.get(mission=mission, event_id=row['EVENT_ID'])
            event.actions.all().delete()
            update_events.append(event)
        except models.Event.DoesNotExist:
            event = models.Event(mission=mission, event_id=row['EVENT_ID'])
            create_events.append(event)

        event.station = station
        event.instrument = instrument
        event.sample_id = row['STARTING_ID'] if row['STARTING_ID'] else None
        event.end_sample_id = row['ENDING_ID'] if row['ENDING_ID'] else None
        event.wire_out = row['WIRE_OUT'] if row['WIRE_OUT'] else None
        event.wire_angle = row['WIRE_ANGLE'] if row['WIRE_ANGLE'] else None
        event.flow_start = row['FLOW_DEPLOY'] if row['FLOW_DEPLOY'] else None
        event.flow_end = row['FLOW_RECOVER'] if row['FLOW_RECOVER'] else None

        events_map[row['EVENT_ID']] = event
        processed += 1

    if create_events:
        models.Event.objects.bulk_create(create_events)

    if update_events:
        models.Event.objects.bulk_update(update_events, ['station', 'instrument', 'sample_id', 'end_sample_id', 'wire_out', 'wire_angle', 'flow_start', 'flow_end'])

    # Step 2: Process actions (all rows) linked to events
    action_columns = ['EVENT_ID', 'ACTION', 'DATE_TIME', 'LATITUDE', 'LONGITUDE',
                      'SOUNDING', 'COMMENT', 'DATA_COLLECTOR']
    actions_df = data_frame[action_columns]

    total_rows = actions_df.shape[0]
    processed = 1
    for index, row in actions_df.iterrows():
        if processed % 50 == 0 or processed == total_rows:
            logger_notifications.info("Processing Actions: %d/%d", processed, total_rows)
        event = events_map[row['EVENT_ID']]
        action_type = get_action_type(row['ACTION'])
        action_type_other = row['ACTION'] if action_type==models.ActionType.other else None
        event_action, created_action = models.Action.objects.get_or_create(
            event=event,
            type=action_type,
            defaults={
                'date_time': row['DATE_TIME'] if row['DATE_TIME'] else None,
                'latitude': row['LATITUDE'] if row['LATITUDE'] else None,
                'longitude': row['LONGITUDE'] if row['LONGITUDE'] else None,
                'sounding': row['SOUNDING'] if row['SOUNDING'] else None,
                'comment': row['COMMENT'] if row['COMMENT'] else None,
                'data_collector': row['DATA_COLLECTOR'] if row['DATA_COLLECTOR'] else None,
                'file': file_name,
                'action_type_other': action_type_other,
            }
        )
        processed += 1

def process_stations(station_list: list[str]):
    logger_notifications.info("Checking Stations")

    for station in station_list:
        # Check if station exists in GlobalStation (case-insensitive)
        try:
            global_station = settings_models.GlobalStation.objects.get(name__iexact=station)
        except settings_models.GlobalStation.DoesNotExist:
            global_station = settings_models.GlobalStation.objects.create(name=station)

        models.Station.objects.get_or_create(name=global_station.name)


def process_instruments(instruments_list: list[(str, str)]):
    logger_notifications.info("Checking Instruments")

    for name, type in instruments_list:
        inst_type = get_instrument_type(type)
        if not (inst:=models.Instrument.objects.filter(name__iexact=name, type=inst_type)).exists():
            models.Instrument.objects.create(name=name, type=inst_type)


def get_instrument_type(instrument: str) -> models.InstrumentType:
    inst_type = models.InstrumentType.other
    if instrument.upper() == 'CTD':
        inst_type = models.InstrumentType.ctd
    elif instrument.upper() == 'NET':
        inst_type = models.InstrumentType.net
    elif instrument.upper() == 'MULTINET':
        inst_type = models.InstrumentType.net

    return inst_type

def get_action_type(action: str) -> models.ActionType:
    """
    Convert action string from CSV to ActionType enum value

    Args:
        action: String representation of the action

    Returns:
        Corresponding ActionType enum value
    """
    if not action or not isinstance(action, str):
        return models.ActionType.other

    action_upper = action.upper()

    if action_upper == 'DEPLOYED':
        return models.ActionType.deployed
    elif action_upper == 'BOTTOM':
        return models.ActionType.bottom
    elif action_upper == 'RECOVERED':
        return models.ActionType.recovered
    elif action_upper == 'ABORTED':
        return models.ActionType.aborted
    else:
        return models.ActionType.other
