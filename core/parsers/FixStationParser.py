import io

from datetime import datetime

import pandas as pd
from django.db.models import QuerySet
from django.utils.translation import gettext as _

from core import models as core_models
from settingsdb.models import FileConfiguration

import logging

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.fixstationparser')


def get_or_create_file_config() -> QuerySet[FileConfiguration]:
    file_type = 'fixstation'
    fields = [
        # Event related fields
        ("event", "Event#", _("Label identifying the event ID")),
        ("station", "Station", _("Label identifying the station of the event")),
        ("data_collector", "Author", _("Label identifying who logged the elog action")),
        ("instrument", "Instrument", _("Label identifying the instrument of the event")),
        ("attached", "Mesh Size", _("Label identifying the mesh size a net uses if the instrument is a net")),
        ("flow_start", "Flowmeter Start", _("Label for the starting value of a flowmeter for a net event")),
        ("flow_end", "Flowmeter End", _("Label for the ending value of a flowmeter for a net event")),
        ("wire_out", "Wire Out", _("Label identifying how much wire was unspooled for a net event")),

        # Action related fields
        ("date", "Date", _("Label identifying the date an action occurred")),
        ("time", "Time", _("Label identifying the time an action occurred")),
        ("lat", "Lat", _("Label identifying an action latitude")),
        ("lon", "Lon", _("Label identifying an action longitude")),
        ("comment", "Comment", _("Label identifying an action comment")),
        ("sounding", "Sounding", _("Label identifying the sounding depth of the action")),

        # Bottle related fields
        ("bottle_id", "Bottle ID", _("Label identifying a bottle on the station tab")),

        # Sample Type related Fields
        ("oxy", "Oxygen", _("Column label identifying if a bottle has oxygen samples")),
        ("nuts", "Nutrients", _("Column label identifying if a bottle has nutrient samples")),
        ("sal", "Salinity", _("Column label identifying if a bottle has salt samples")),
        ("chl", "Chlorophyll", _("Column label identifying if a bottle has chlorophyll samples")),
        ("pyto", "Int Phytopl.", _("Column label identifying if a bottle has plankton samples")),
        ("tic", "TIC", _("Column label identifying if a bottle has tic samples")),
        ("pco2", "PCO2", _("Column label identifying if a bottle has PCO2 samples")),
        ("abs", "ABS", _("Column label identifying if a bottle has ABS samples")),
        ("hplc", "HPLC", _("Column label identifying if a bottle has HPLC samples")),
        ("poc", "POC", _("Column label identifying if a bottle has POC samples")),
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


def get_mapping(label):
    row_mapping = get_or_create_file_config()

    return row_mapping.get(required_field=label).mapped_field


def parse_fixstation(trip: core_models.Trip, filename: str, stream: io.BytesIO):

    database = trip._state.db

    trip_tab = pd.read_excel(io=stream, sheet_name="Trip", header=1, nrows=20)
    trip_tab.fillna('', inplace=True)
    for row, data in trip_tab.iterrows():
        event_id = data[get_mapping('event')]
        if not event_id:
            continue

        logger_notifications.info(f"Events: {event_id}")

        station_name = data[get_mapping('station')]
        if (stations := core_models.Station.objects.using(database).filter(name__iexact=station_name)).exists():
            station = stations.first()
        else:
            (station := core_models.Station(name=station_name)).save(using=database)

        instrument_name = data[get_mapping('instrument')]
        if (instruments := core_models.Instrument.objects.using(database).filter(name__iexact=instrument_name)).exists():
            instrument = instruments.first()
        else:
            instrument = core_models.Instrument(name=instrument_name)
            if instrument_name.lower() == 'ctd':
                instrument.type = core_models.InstrumentType.ctd
            elif instrument_name.lower() == 'net':
                instrument.type = core_models.InstrumentType.net
            instrument.save()

        wire_out = data[get_mapping('wire_out')]
        flow_start = data[get_mapping('flow_start')]
        flow_end = data[get_mapping('flow_end')]

        event = core_models.Event(trip=trip, event_id=event_id, station=station, instrument=instrument)

        event.wire_out = wire_out if wire_out else None
        event.flow_start = flow_start if flow_start else None
        event.flow_end = flow_end if flow_end else None

        event.save(using=database)

        attachment_name = data[get_mapping('attached')]
        if attachment_name:
            if not event.attachments.filter(name__iexact=attachment_name).exists():
                core_models.Attachment(event=event, name=attachment_name).save(using=database)

        process_actions(event, data)


def process_actions(event, data):
    database = event._state.db

    action_date_columns = [col for col in data.index.values if col.startswith(get_mapping('date'))]
    action_time_columns = [col for col in data.index.values if col.startswith(get_mapping('time'))]
    action_lat_columns = [col for col in data.index.values if col.startswith(get_mapping('lat'))]
    action_lon_columns = [col for col in data.index.values if col.startswith(get_mapping('lon'))]
    action_sounding_columns = [col for col in data.index.values if col.startswith(get_mapping('sounding'))]
    action_comment_columns = [col for col in data.index.values if col.startswith(get_mapping('comment'))]
    for i in range(len(action_date_columns)):
        date_str = data[action_date_columns[i]]
        time_str = '%#06d' % data[action_time_columns[i]]
        lat = data[action_lat_columns[i]]
        lon = data[action_lon_columns[i]]
        sounding = data[action_sounding_columns[i]]
        comment = data[action_comment_columns[i]]
        date = datetime.strptime(f"{date_str} {time_str} +00:00", '%Y-%m-%d 00:00:00 %H%M%S %z')

        action = core_models.Action(event=event, date_time=date, sounding=sounding,
                                    latitude=lat, longitude=lon, comment=comment, type=(i+1))
        action.save(using=database)
