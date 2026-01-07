import pandas as pd
import io

from core import models
from settingsdb import models as settings_models
from django.utils.translation import gettext_lazy as _

import logging

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.csv')


def create_events(mission: models.Mission, data_frame: pd.DataFrame) -> dict:
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

        # if the event already exists in the database we're going to update it on our first pass
        # if it doesn't exist we'll create a new event.
        # if the event was added to the event map for either updating or creation, we're done
        if (row['EVENT_ID'], instrument.pk) in events_map:
            processed += 1
            continue

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

        events_map[(row['EVENT_ID'], instrument.pk)] = event
        processed += 1

    if create_events:
        models.Event.objects.bulk_create(create_events)

    if update_events:
        models.Event.objects.bulk_update(update_events, ['station', 'instrument', 'sample_id', 'end_sample_id', 'wire_out', 'wire_angle', 'flow_start', 'flow_end'])

    return events_map


def create_actions(file_name: str, data_frame: pd.DataFrame, events_map: dict):
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


def rename_dataframe_fields(data_frame: pd.DataFrame):
    # these are some common field names that might be used and a mapping to what the CSV parser would prefer
    rename_fields = [
        ('SAMPLE_ID','STARTING_ID'),
        ('DATE_TIME (UTC)','DATE_TIME')
    ]
    for fields in rename_fields:
        if fields[0] in data_frame.columns and fields[1] not in data_frame.columns:
            data_frame[fields[1]] = data_frame[fields[0]]


def normalize_date_format(data_frame: pd.DataFrame):
    # Normalize DATE_TIME column to a consistent datetime format
    if 'DATE_TIME' in data_frame.columns:
        try:
            data_frame['DATE_TIME'] = pd.to_datetime(data_frame['DATE_TIME'], errors='coerce')
            if data_frame['DATE_TIME'].isnull().any():
                logger.warning("Some DATE_TIME values could not be parsed and were set to NaT.")
        except Exception as ex:
            logger.exception(ex)
            raise


def normal_csv_parser(mission: models.Mission, file_name: str, data_frame: pd.DataFrame):
    # Step 2: Create or Update events
    event_columns = ['EVENT_ID', 'STATION', 'STARTING_ID', 'ENDING_ID', 'INSTRUMENT_NAME', 'INSTRUMENT_TYPE',
                     'WIRE_ANGLE', 'WIRE_OUT', 'FLOW_DEPLOY', 'FLOW_RECOVER']

    events_df = data_frame[event_columns]
    events_map = create_events(mission, events_df)

    # Step 3: Process actions (all rows) linked to events

    action_columns = ['EVENT_ID', 'ACTION', 'INSTRUMENT_NAME', 'INSTRUMENT_TYPE', 'DATE_TIME',
                      'LATITUDE', 'LONGITUDE', 'SOUNDING', 'DATA_COLLECTOR', 'COMMENT']

    actions_df = data_frame[action_columns]

    create_actions(file_name, actions_df, events_map)


def fixed_station_csv_parser(mission: models.Mission, file_name: str, data_frame: pd.DataFrame):
    # The create events function is going to add events that don't exist to the database. Later the create_actions
    # function will add the actions from the dataframe to the events returned in the events_map.
    #
    # Presuming the created events are net events, we might be dealing with a fixed station bulk load csv:
    # If the LATITUDE, LONGITUDE and SOUNDING columns are missing from the dataframe the create_actions function
    # is going to try and find an existing CTD event with a matching EVENT_ID and will use that event's first action
    # to get the lat/lon and sounding for the newly created net event.
    #
    # If the LATITUDE, LONGITUDE and SOUNDING columns are missing We should check the dataframe for net events
    # to be created and remove events that don't have existing CTD events.

    # if this is a fixed station csv, these columns will likely be missing from the dataframe
    # location_columns = ['LATITUDE', 'LONGITUDE', 'SOUNDING', 'DATA_COLLECTOR']

    action_columns = ['EVENT_ID', 'ACTION', 'INSTRUMENT_NAME', 'INSTRUMENT_TYPE', 'DATE_TIME']
    # comments is an optional column
    if 'COMMENT' in data_frame.columns:
        action_columns.append('COMMENT')

    # Check for existing CTD event with matching EVENT_ID
    actions_df = data_frame[action_columns].copy()

    df_event_ids = actions_df['EVENT_ID'].unique().tolist()
    ctd_event_query = models.Event.objects.filter(event_id__in=df_event_ids, instrument__type=models.InstrumentType.ctd)
    ctd_events: dict[int, models.Event] = {event.event_id: event for event in ctd_event_query}

    # This will throw an exception if these fields aren't present in the dataframe, but that's good
    # because we don't want to process random CSV files.
    event_columns = ['EVENT_ID', 'STATION', 'STARTING_ID', 'INSTRUMENT_NAME', 'INSTRUMENT_TYPE',
                     'WIRE_ANGLE', 'WIRE_OUT', 'FLOW_DEPLOY', 'FLOW_RECOVER']

    # for net events the ending ID isn't necessary and might not be included in the CSV file if this is a fixed station.
    if 'ENDING_ID' in data_frame.columns:
        event_columns.append('ENDING_ID')

    events_df = data_frame[event_columns].copy()

    # we don't want to create events for nets that don't have a matching CTD event.
    net_event_keys = events_df['EVENT_ID'].unique().tolist()
    ctd_event_keys = ctd_events.keys()

    # find the difference between these two key arrays and remove the elements from the events_df
    drop_events = net_event_keys - ctd_event_keys

    # Remove rows from the dataframe where an element in drop_events exists in the EVENT_ID column
    if drop_events:
        for evt in drop_events:
            message = _("Missing CTD event for Net event creation")
            models.FileError.objects.create(mission=mission, file_name=file_name, message=message, line=evt,
                                            code=200, type=models.ErrorType.missing_id)

        events_df = events_df[~events_df['EVENT_ID'].isin(drop_events)]
        actions_df = actions_df[~actions_df['EVENT_ID'].isin(drop_events)]

    events_map = create_events(mission, events_df)

    # Step 3: Process actions (all rows) linked to events

    for index, row in actions_df.iterrows():
        event = ctd_events[row['EVENT_ID']]
        first_action = event.actions.first()
        if first_action:
            actions_df.at[index, 'LATITUDE'] = first_action.latitude
            actions_df.at[index, 'LONGITUDE'] = first_action.longitude
            actions_df.at[index, 'SOUNDING'] = first_action.sounding
            actions_df.at[index, 'DATA_COLLECTOR'] = first_action.data_collector

    create_actions(file_name, actions_df, events_map)


def parse(mission: models.Mission, file_name: str, data: io.StringIO):
    models.FileError.objects.filter(file_name__iexact=file_name, code__range=[200, 299]).delete()
    data_frame = pd.read_csv(data, na_filter=False)

    data_frame.columns = data_frame.columns.str.upper()
    rename_dataframe_fields(data_frame)
    normalize_date_format(data_frame)


    # Step 1: Get all the stations and instruments from the data frame and make sure they exist
    # to be used in the following steps

    # Process stations and instruments by finding unique strings in the dataframe and making sure
    # they exist in the mission database to be used when creating events later.
    stations = data_frame['STATION'].unique().tolist()
    process_stations(stations)

    instruments = data_frame[['INSTRUMENT_NAME', 'INSTRUMENT_TYPE']].drop_duplicates().values.tolist()
    process_instruments(instruments)

    logger_notifications.info("Processing Events")

    # Check for fixed_station_test_columns in the dataframe
    fixed_station_test_columns = ['LATITUDE', 'LONGITUDE', 'SOUNDING', 'DATA_COLLECTOR']
    if all(column in data_frame.columns for column in fixed_station_test_columns):
        normal_csv_parser(mission, file_name, data_frame)
    else:
        fixed_station_csv_parser(mission, file_name, data_frame)


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


