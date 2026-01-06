import pandas as pd
import io

from core import models
from core.models import ActionType
from settingsdb import models as settings_models

import logging

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.csv')


def create_events(mission: models.Mission, data_frame: pd.DataFrame) -> dict:


    # Create all events
    events_map = {}  # Map of event_id to Event object for quick lookup

    total_rows = data_frame.shape[0]
    processed = 1
    create_events = []
    update_events = []
    for index, row in data_frame.iterrows():
        if processed % 10 == 0 or processed == total_rows:
            logger_notifications.info("Processing Events: %d/%d", processed, total_rows)

        station = models.Station.objects.get(name__iexact=row['STATION'])
        inst_type = get_instrument_type(row['INSTRUMENT_TYPE'])
        instrument = models.Instrument.objects.get(name__iexact=row['INSTRUMENT_NAME'], type=inst_type)

        try:
            event = models.Event.objects.get(mission=mission, event_id=row['EVENT_ID'],
                                             instrument__type=instrument.type,
                                             instrument__name__iexact=instrument.name)
            event.actions.all().delete()
            update_events.append(event)
        except models.Event.DoesNotExist:
            event = models.Event(mission=mission, event_id=row['EVENT_ID'])
            create_events.append(event)

        event.station = station
        event.instrument = instrument
        event.sample_id = row['STARTING_ID'] if row['STARTING_ID'] else None
        if 'ENDING_ID' in data_frame.columns:
            event.end_sample_id = row['ENDING_ID'] if row['ENDING_ID'] else None

        event.wire_out = row['WIRE_OUT'] if row['WIRE_OUT'] else None
        event.wire_angle = row['WIRE_ANGLE'] if row['WIRE_ANGLE'] else None
        event.flow_start = row['FLOW_DEPLOY'] if row['FLOW_DEPLOY'] else None
        event.flow_end = row['FLOW_RECOVER'] if row['FLOW_RECOVER'] else None

        events_map[(row['EVENT_ID'], event.instrument.pk)] = event
        processed += 1

    if create_events:
        models.Event.objects.bulk_create(create_events)

    if update_events:
        models.Event.objects.bulk_update(update_events, ['station', 'instrument', 'sample_id', 'end_sample_id', 'wire_out', 'wire_angle', 'flow_start', 'flow_end'])

    return events_map


def create_actions(file_name: str, data_frame: pd.DataFrame, events_map: dict):
    create_actions = []

    total_rows = data_frame.shape[0]
    processed = 1
    for index, row in data_frame.iterrows():
        if processed % 50 == 0 or processed == total_rows:
            logger_notifications.info("Processing Actions: %d/%d", processed, total_rows)

        instrument_type = get_instrument_type(row['INSTRUMENT_TYPE'])
        instrument = models.Instrument.objects.get(name__iexact=row['INSTRUMENT_NAME'], type=instrument_type)

        event = events_map[(row['EVENT_ID'], instrument.pk)]
        action_type = get_action_type(row['ACTION'])
        action_type_other = row['ACTION'] if action_type == models.ActionType.other else None
        event_action, created_action = models.Action.objects.get_or_create(
            event=event,
            type=action_type,
            defaults={
                'date_time': row['DATE_TIME'] if row['DATE_TIME'] else None,
                'latitude': row['LATITUDE'] if row['LATITUDE'] else None,
                'longitude': row['LONGITUDE'] if row['LONGITUDE'] else None,
                'sounding': row['SOUNDING'] if row['SOUNDING'] else None,
                'comment': row['COMMENT'] if 'COMMENT' in data_frame.columns and row['COMMENT'] else None,
                'data_collector': row['DATA_COLLECTOR'] if row['DATA_COLLECTOR'] else None,
                'file': file_name,
                'action_type_other': action_type_other,
            }
        )
        processed += 1


def parse(mission: models.Mission, file_name: str, data: io.StringIO):
    data_frame = pd.read_csv(data, na_filter=False)
    data_frame.columns = data_frame.columns.str.upper()

    # If the CSV provides SAMPLE_ID (e.g. "Sample_id") but not STARTING_ID,
    # use SAMPLE_ID as STARTING_ID so downstream code can rely on STARTING_ID.
    if 'SAMPLE_ID' in data_frame.columns and 'STARTING_ID' not in data_frame.columns:
        data_frame['STARTING_ID'] = data_frame['SAMPLE_ID']

    if 'DATE_TIME (UTC)' in data_frame.columns and 'DATE_TIME' not in data_frame.columns:
        data_frame['DATE_TIME'] = data_frame['DATE_TIME (UTC)']

    # Normalize DATE_TIME column to a consistent datetime format
    if 'DATE_TIME' in data_frame.columns:
        try:
            data_frame['DATE_TIME'] = pd.to_datetime(data_frame['DATE_TIME'], errors='coerce')
            if data_frame['DATE_TIME'].isnull().any():
                logger.warning("Some DATE_TIME values could not be parsed and were set to NaT.")
        except Exception as e:
            logger.error(f"Error normalizing DATE_TIME column: {e}")
            raise

    # Step 1: Get all the stations and instruments from the data frame and make sure they exist
    # to be used in the following steps

    # Process stations and instruments
    stations = data_frame['STATION'].unique().tolist()
    process_stations(stations)

    instruments = data_frame[['INSTRUMENT_NAME', 'INSTRUMENT_TYPE']].drop_duplicates().values.tolist()
    process_instruments(instruments)

    logger_notifications.info("Processing Events")

    # Step 2: Create or Update events

    # This will throw an exception if these fields aren't present in the dataframe, but that's good
    # because we don't want to process random CSV files.
    event_columns = ['EVENT_ID', 'STATION', 'STARTING_ID', 'INSTRUMENT_NAME', 'INSTRUMENT_TYPE', 'WIRE_ANGLE',
                     'WIRE_OUT', 'FLOW_DEPLOY', 'FLOW_RECOVER']

    # for net events the ending ID isn't necessary and might not be included in the CSV file.
    if 'ENDING_ID' in data_frame.columns:
        event_columns.append('ENDING_ID')

    events_df = data_frame[event_columns]
    # events_df = events_df.drop_duplicates(subset=['EVENT_ID'])

    events_map = create_events(mission, events_df)

    # Step 3: Process actions (all rows) linked to events

    action_columns = ['EVENT_ID', 'ACTION', 'INSTRUMENT_NAME', 'INSTRUMENT_TYPE', 'DATE_TIME', 'LATITUDE', 'LONGITUDE',
                      'SOUNDING', 'DATA_COLLECTOR']

    # comments is an optional column
    if 'COMMENT' in data_frame.columns:
        action_columns.append('COMMENT')

    try:
        # This will throw an exception if the action fields aren't present in the dataframe.
        # Not so good here because the events were already created and now won't have their actions created.
        # But if an existing CTD Event then we can re-use the lat/lon, sounding and data collector from that event
        actions_df = data_frame[action_columns]
    except KeyError as ex:
        missing_columns = [col for col in action_columns if col not in data_frame.columns]
        logger.error(f"Missing columns in actions data: {missing_columns}")

        if 'EVENT_ID' not in missing_columns:
            # Check for existing CTD event with matching EVENT_ID
            actions_df = data_frame[['EVENT_ID', 'ACTION', 'INSTRUMENT_NAME', 'INSTRUMENT_TYPE', 'DATE_TIME']].copy()
            # if a matching CTD event doesn't exist then we have to drop the actions from
            # the data frame. Otherwise, none of the actions will be processed for events
            # we do have data for.
            rows_to_drop = []

            for index, row in actions_df.iterrows():
                try:
                    event = models.Event.objects.get(event_id=row['EVENT_ID'],
                                                     instrument__type=models.InstrumentType.ctd)
                    first_action = event.actions.first()
                    if first_action:
                        actions_df.at[index, 'LATITUDE'] = first_action.latitude
                        actions_df.at[index, 'LONGITUDE'] = first_action.longitude
                        actions_df.at[index, 'SOUNDING'] = first_action.sounding
                        actions_df.at[index, 'DATA_COLLECTOR'] = first_action.data_collector
                except models.Event.DoesNotExist:
                    logger.warning(f"No matching CTD event found for EVENT_ID: {row['EVENT_ID']}")
                    rows_to_drop.append(index)

            # Drop rows with no matching CTD event
            actions_df.drop(index=rows_to_drop, inplace=True)
        else:
            raise ex

    create_actions(file_name, actions_df, events_map)


def process_stations(station_list: list[str]):
    logger_notifications.info("Checking Stations")

    for station in station_list:
        # Check if station exists in GlobalStation (case-insensitive)
        try:
            global_station = settings_models.GlobalStation.objects.get(name__iexact=station)
        except settings_models.GlobalStation.DoesNotExist:
            global_station = settings_models.GlobalStation.objects.create(name=station)

        models.Station.objects.get_or_create(name=global_station.name)


def process_instruments(instruments_list: list[tuple[str, str]]):
    # process instruments takes a list of tuples (instrument_name, instrument_type) and
    # makes sure that combination exists in the local DB.
    logger_notifications.info("Checking Instruments")

    for name, type in instruments_list:
        inst_type = get_instrument_type(type)
        if not (inst:=models.Instrument.objects.filter(name__iexact=name, type=inst_type)).exists():
            models.Instrument.objects.create(name=name, type=inst_type)


def get_instrument_type(instrument: str) -> models.InstrumentType:
    # converts a string into its respective type.
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
