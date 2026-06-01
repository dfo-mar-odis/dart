import io
import json
import os
import re
import threading
from typing import Any, List

import ctd
import pandas as pd
import pytz

from geopy.distance import geodesic

from dataclasses import dataclass
from django.utils.translation import gettext_lazy as _

from config import utils
from core.utils import is_number
from settingsdb.models import GlobalSampleType, GlobalStation
from core import models as core_models
from bio_tables import models as bio_models

import logging
logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.fixstationparser')

@dataclass
class ParsedBtlFile:
    event_id: str
    btl_filename: str
    file_properties: dict
    col_headers: list[str]
    bottles_df: pd.DataFrame       # the 'avg' rows for bottle creation
    data_df: pd.DataFrame          # the 'avg' rows for sample data
    sensor_headings: list[str]     # from the ROS file, if present
    errors: list[str]              # any parse errors encountered


btl_column_mapping = {
    'pressure': ['prdm', 'prsm'],
    'latitude': ['latitude'],
    'longitude': ['longitude'],
    'bottle_id': ['bottle_']
}

def get_btl_mapping() -> dict:
    config_dir = 'file_configs'
    default_file = os.path.join(config_dir, 'default_btl.json')
    btl_file = os.path.join(config_dir, 'btl.json')

    file_to_load = default_file if os.path.exists(default_file) else btl_file

    with open(file_to_load, 'r') as f:
        return json.load(f)


def parse_file_to_intermediate(btl_file, ros_file, results: list, errors_to_create: list):
    """Thread-safe: reads files and parses to intermediate structure. No DB calls."""
    try:
        with open(btl_file, 'r', encoding='cp1252') as btl:
            btl_input = io.StringIO(btl.read())

        ros_input = None
        if ros_file:
            with open(ros_file, 'r', encoding='cp1252') as ros:
                ros_input = io.StringIO(ros.read())

        # FixStationParser.__init__ currently requires an event — we need a lightweight
        # version that only holds streams and filename for parse_to_intermediate
        parser = FixStationParser.from_streams(
            btl_filename=os.path.basename(btl_file),
            btl_stream=btl_input,
            ros_stream=ros_input
        )
        parsed = parser.parse_to_intermediate()
        results.append(parsed)
    except Exception as e:
        message = _("Error parsing file ") + f": {btl_file}: {e}"
        logger.error(message)
        logger.exception(e)
        errors_to_create.append((os.path.basename(btl_file), str(e)))


def validate_fixed_station_file(btl_stream, file_properties: dict = None) -> None:
    btl_mapping = get_btl_mapping()

    if not file_properties:
        data: pd.DataFrame = ctd.read.from_btl(btl_stream)

        metadata: dict = data.__getattr__('_metadata')
        header = metadata['header']

        header_lines: str = re.findall(r'\*\*.*', header, re.MULTILINE)
        cleaned_lines: list[str] = [re.sub(r'\*\*', '', line).split(":") for line in header_lines]
        file_properties = {cl[0].strip().upper(): cl[1].strip() for cl in cleaned_lines if len(cl) >= 2}

    # required values. Event_id to get an event, station to confirm this BTL file is for the correct station
    event_label = btl_mapping['event_id'].get('label', 'Event_Number')
    event_id = btl_mapping['event_id'].get('default', None)

    station_label = btl_mapping['station'].get('label', 'Station_Name')
    station_name = btl_mapping['station'].get('default', None)

    # If loading for a fixed station, these are required to automatically create actions
    # If actions have been created using an event file first, these are optional.
    # event data will be overridden if they're present in the BTL file.
    sounding_label = btl_mapping['sounding'].get('label', 'Sounding')
    sounding = btl_mapping['sounding'].get('default', None)

    lat_label = btl_mapping['latitude'].get('label', 'Latitude')
    latitude = btl_mapping['latitude'].get('default', None)

    lon_label = btl_mapping['longitude'].get('label', 'Longitude')
    longitude = btl_mapping['longitude'].get('default', None)

    # Instrument name is optional. If not provided the name of a CTD is 'CTD'
    # instrument_name = self.get_mapping('instrument_name')

    if event_label.upper() not in file_properties.keys():
        raise KeyError(_('Missing header variable') + " : " + event_label.upper())

    if (event_id := file_properties.get(event_label.upper(), event_id)) is None:
        raise ValueError("Event ID is missing")

    if station_label.upper() not in file_properties.keys():
        raise KeyError(_('Missing header variable') + " : " + station_label.upper())

    if (station_name := file_properties.get(station_label.upper(), station_name)) is None:
        raise ValueError("Station Name is missing")

    try:
        event = core_models.Event.objects.get(event_id=event_id, instrument__type=core_models.InstrumentType.ctd)
    except core_models.Event.DoesNotExist:
        # If no event exists for this file, then we have to check if the file has the headers required to
        # create the event. If it doesn't then this is not a fixed station BTL file and events will have
        # to be loaded first. We've already checked for the event ID and the Station name
        if sounding_label.upper() not in file_properties.keys():
            raise KeyError(_('Missing header variable') + " : " + sounding_label.upper())

        if (file_properties.get(sounding_label.upper(), sounding)) is None:
            message = _("File is missing a sounding header, you may have to load events from Elog, ANDES or CSV first")
            raise ValueError(message)

        if lat_label.upper() not in file_properties.keys():
            raise KeyError(_('Missing header variable') + " : " + sounding_label.upper())

        if (file_properties.get(lat_label.upper(), latitude)) is None:
            message = _("File is missing a latitude header, you may have to load events from Elog, ANDES or CSV first")
            raise ValueError(message)

        if lon_label.upper() not in file_properties.keys():
            raise KeyError(_('Missing header variable') + " : " + sounding_label.upper())

        if (file_properties.get(lon_label.upper(), longitude)) is None:
            message = _("File is missing a longitude header, you may have to load events from Elog, ANDES or CSV first")
            raise ValueError(message)

        return

    file_cruise = file_properties.get('CRUISE', '').strip()
    if file_cruise:
        mission = core_models.Mission.objects.first()  # one mission per DB
        if mission and file_cruise.upper() != mission.name.strip().upper():
            raise ValueError(
                _("Cruise mismatch: BTL file is from cruise") + f" '{file_cruise}' " +
                _("but this database contains mission") + f" '{mission.name}'"
            )

    # Event exists — validate station name matches
    file_station_name = file_properties.get(station_label.upper(), '').strip()
    if event.station and file_station_name:
        if event.station.name.strip().lower() != file_station_name.lower():
            raise ValueError(
                _("Station mismatch: BTL file contains station") + f" '{file_station_name}' " +
                _("but Event") + f" #{event_id} " +
                _("is assigned to station") + f" '{event.station.name}'"
            )

    # if the event doesn't have actions, then these fields will be required
    has_actions = event.actions.all().exists()
    if not has_actions:
        if (sounding := file_properties.get(sounding_label.upper(), sounding)) is None:
            raise ValueError("Sounding is missing from the header. Cannot create event")

        if (latitude := file_properties.get(lat_label.upper(), latitude)) is None:
            raise ValueError("Latitude is missing from the header. Cannot create event")

        if (longitude := file_properties.get(lon_label.upper(), longitude)) is None:
            raise ValueError("Longitude is missing from the header. Cannot create event")


def validate_btl_file(btl_stream, file_properties: dict = None) -> None:
    btl_mapping = get_btl_mapping()

    if not file_properties:
        data: pd.DataFrame = ctd.read.from_btl(btl_stream)
        metadata: dict = data.__getattr__('_metadata')
        header = metadata['header']
        header_lines: str = re.findall(r'\*\*.*', header, re.MULTILINE)
        cleaned_lines: list[str] = [re.sub(r'\*\*', '', line).split(":") for line in header_lines]
        file_properties = {cl[0].strip().upper(): cl[1].strip() for cl in cleaned_lines if len(cl) >= 2}

    event_label = btl_mapping['event_id'].get('label', 'Event_Number')
    event_id = btl_mapping['event_id'].get('default', None)
    station_label = btl_mapping['station'].get('label', 'Station_Name')

    if event_label.upper() not in file_properties.keys():
        raise KeyError(_('Missing header variable') + " : " + event_label.upper())

    if (event_id := file_properties.get(event_label.upper(), event_id)) is None:
        raise ValueError("Event ID is missing")

    if station_label.upper() not in file_properties.keys():
        raise KeyError(_('Missing header variable') + " : " + station_label.upper())

    file_station_name = file_properties.get(station_label.upper(), '').strip()

    # Event must already exist — it should have been loaded from Elog, ANDES or CSV
    try:
        event = core_models.Event.objects.get(
            event_id=event_id,
            instrument__type=core_models.InstrumentType.ctd
        )
    except core_models.Event.DoesNotExist:
        raise ValueError(
            _("Event") + f" #{event_id} " +
            _("does not exist. Load event data from Elog, ANDES or CSV before loading BTL files.")
        )

    file_cruise = file_properties.get('CRUISE', '').strip()
    if file_cruise:
        mission = core_models.Mission.objects.first()  # one mission per DB
        if mission and file_cruise.upper() != mission.name.strip().upper():
            raise ValueError(
                _("Cruise mismatch: BTL file is from cruise") + f" '{file_cruise}' " +
                _("but this database contains mission") + f" '{mission.name}'"
            )

    # Confirm the station in the file matches the event's station
    if event.station and file_station_name:
        if event.station.name.strip().lower() != file_station_name.lower():
            raise ValueError(
                _("Station mismatch: BTL file contains station") + f" '{file_station_name}' " +
                _("but Event") + f" #{event_id} " +
                _("is assigned to station") + f" '{event.station.name}'"
            )


class FixStationParser:

    @classmethod
    def from_streams(cls, btl_filename: str, btl_stream: io.StringIO, ros_stream: io.StringIO | None):
        """Lightweight constructor for pure parsing — no event or DB references needed."""
        instance = cls.__new__(cls)
        instance.btl_filename = btl_filename
        instance.btl_stream = btl_stream
        instance.ros_stream = ros_stream
        instance.field_mappings = None
        # these are not used by parse_to_intermediate, but set to safe defaults
        instance.event = None
        instance.mission = None
        instance.mission_sample_types = {}
        instance.file_properties = None
        instance.errors_to_create = []
        return instance

    # Dart should assume we're working in the northwest hemisphere
    def _convert_to_decimal_deg(self, direction, hours, minutes=0):
        lat_lon = float(hours) + (float(minutes) / 60.0)
        if direction.upper() == 'S' or direction.upper() == 'W':
            lat_lon *= -1
        return lat_lon

    def _process_coordinate(self, coord_array, is_latitude=True):
        direction_values = ['N', 'S'] if is_latitude else ['E', 'W']
        coord_type = "latitude" if is_latitude else "longitude"

        # Case 1: Single value - likely decimal degrees
        if len(coord_array) == 1:
            try:
                return float(coord_array[0])
            except ValueError:
                raise ValueError(f"Invalid decimal degrees format for {coord_type}: {' '.join(coord_array)}")

        # Case 2: Direction + degrees + minutes format (e.g., "N 45 30.0")
        elif len(coord_array) == 3 and coord_array[0].upper() in direction_values:
            try:
                return self._convert_to_decimal_deg(coord_array[0], coord_array[1], coord_array[2])
            except ValueError:
                raise ValueError(f"Invalid degrees/minutes format for {coord_type}: {' '.join(coord_array)}")

        # Case 3: degrees + minutes format no direction specified (e.g., "45 30.0")
        elif len(coord_array) == 2 and is_number(coord_array[0]):
            try:
                # If not specified we're going to assume this takes place in the Northwest Atlantic
                return self._convert_to_decimal_deg('W' if is_latitude else 'N', coord_array[0], coord_array[1])
            except ValueError:
                raise ValueError(f"Invalid degrees/minutes format for {coord_type}: {' '.join(coord_array)}")

        # Invalid format
        else:
            raise ValueError(f"Unrecognized {coord_type} format: {' '.join(coord_array)}")

    def _create_update_action(self, action_type: core_models.ActionType, bottle, sounding, latitude, longitude):
        bottom_action = self.event.actions.filter(type=action_type)
        if not bottom_action.exists():
            self.event.actions.create(type=action_type,
                                      date_time=bottle.closed, sounding=sounding,
                                      latitude=latitude, longitude=longitude)
        else:
            action = bottom_action.first()
            action.date_time = bottle.closed
            action.sounding = sounding
            action.latitude = latitude
            action.longitude = longitude
            action.save()

    def _get_units(self, sensor_description: str) -> tuple[str | Any, str]:
        """given a sensor description, find, remove and return the uom and remaining string"""
        uom_pattern = " \\[(.*?)\\]"
        uom = re.findall(uom_pattern, sensor_description)
        uom = uom[0] if uom else ""
        return uom, re.sub(uom_pattern, "", sensor_description)

    @staticmethod
    def _get_priority(sensor_description: str) -> tuple[int, str]:
        """given a sensor description, with units removed, find, remove and return the priority and remaining string"""
        priority_pattern = r", (\d)"
        priority = re.findall(priority_pattern, sensor_description)
        priority = priority[0] if priority else 1
        return int(priority), re.sub(priority_pattern, "", sensor_description)

    @staticmethod
    def _get_sensor_type(sensor_description: str) -> tuple[str, str]:
        """given a sensor description with priority and units removed return the sensor type and remaining string"""
        remainder = sensor_description.split(", ")
        # if the sensor type wasn't in the remaining comma seperated list then it is the first value of the description
        return remainder[0], ", ".join([remainder[i] for i in range(1, len(remainder)) if len(remainder) > 1])

    def _get_bottle_id(self, bottle, column_mapping: dict, row: int) -> int:
        if 'bottle_id' in column_mapping:
            return bottle[column_mapping['bottle_id'][0]]
        elif self.event.sample_id:
            return self.event.sample_id + (row - 1)
        else:
            raise ValueError(_("Require either S/N column in BTL file or Start IDs specified for the Event"))

    def _validate_bottle_id(self, bottle_id):
        # when looking for existing bottles that overlap with another event exclude bottles from this event
        # and bottles created for net events
        existing_bottle = core_models.Bottle.objects.exclude(event=self.event).exclude(
            event__instrument__type=core_models.InstrumentType.net).filter(bottle_id=bottle_id).first()

        # if the bottle exists for an event other than the current event
        if existing_bottle and existing_bottle.event == self.event:
            raise KeyError(_("Bottle with provided ID already exists") + f" {int(bottle_id)}")

    def _get_field_mapping(self) -> dict:
        if self.field_mappings:
            return self.field_mappings

        self.field_mappings = get_btl_mapping()

        return self.field_mappings

    @staticmethod
    def _parse_sensor_name(sensor: str) -> list[str | int | None | Any]:
        # Given a sensor name, return the type of sensor, its priority and units where available
        # For common sensors the common format for the names is [sensor_type][priority][units]
        # Sbeox0ML/L -> Sbeox (Sea-bird oxygen), 0 (primary sensor), ML/L
        # many sensors follow this format, the ones that don't are likely located, in greater detail, in
        # the ROS file configuration
        details = re.match(r"(\D\D*)(\d{0,1})([A-Z]*.*)", sensor).groups()
        if not details:
            raise Exception(f"Sensor '{sensor}' does not follow the expected naming convention")

        sensor_name = sensor
        priority = int(
            details[1] if len(details[1]) >= 1 else 0) + 1  # priority 0 means primary sensor, 1 means secondary
        units = None
        if len(details) > 2:
            at_least_one_letter = re.search(r'[a-zA-Z]+', details[2])
            if at_least_one_letter:
                units = details[2]

        return [sensor_name, priority, units]

    def _update_existing_bottle(self, existing_bottle: core_models.Bottle, closed, pressure, latitude, longitude) -> set:
        updated_fields = set()
        updated_fields.add(utils.updated_value(existing_bottle, 'closed', closed))
        updated_fields.add(utils.updated_value(existing_bottle, 'pressure', pressure))
        if latitude:
            updated_fields.add(utils.updated_value(existing_bottle, 'latitude', latitude))
        if longitude:
            updated_fields.add(utils.updated_value(existing_bottle, 'longitude', longitude))

        updated_fields.discard('')
        return updated_fields

    def parse_to_intermediate(self) -> ParsedBtlFile:
        """Read BTL (and optionally ROS) streams and return a ParsedBtlFile.
        No database calls are made here."""
        errors: list[str] = []

        # --- Read BTL file ---
        data: pd.DataFrame = ctd.read.from_btl(self.btl_stream)

        header: str = data._metadata['header']
        header_lines = re.findall(r'\*\*.*', header, re.MULTILINE)
        cleaned_lines = [re.sub(r'\*\*', '', line).split(":") for line in header_lines]
        file_properties = {cl[0].strip().upper(): cl[1].strip() for cl in cleaned_lines if len(cl) >= 2}

        btl_mapping = get_btl_mapping()
        event_label = btl_mapping['event_id'].get('label', 'Event_Number').upper()
        event_id = file_properties.get(event_label)

        exclude = ['bottle', 'bottle_', 'date', 'scan', 'times', 'statistic',
                   'longitude', 'latitude', 'nbf', 'flag']
        col_headers = [col.lower() for col in data.columns if col.lower() not in exclude]

        # --- Read ROS file (if present) ---
        sensor_headings: list[str] = []
        if self.ros_stream:
            try:
                summary = ctd.rosette_summary(self.ros_stream)
                sensor_headings = re.findall(
                    r"# name \d+ = (.*?)\n",
                    getattr(summary, '_metadata')['config']
                )
            except Exception as e:
                errors.append(f"Could not parse ROS file: {e}")

        return ParsedBtlFile(
            event_id=event_id,
            btl_filename=self.btl_filename,
            file_properties=file_properties,
            col_headers=col_headers,
            bottles_df=data,        # process_bottles filters to 'avg' itself
            data_df=data,           # process_data filters to 'avg' itself
            sensor_headings=sensor_headings,
            errors=errors,
        )

    def parse_sensor(self, sensor: str) -> tuple[Any, Any, Any, Any]:
        """given a sensor description parse out the type, priority and units """
        units, sensor_a = self._get_units(sensor)
        priority, sensor_b = self._get_priority(sensor_a)
        sensor_type, remainder = self._get_sensor_type(sensor_b)

        return sensor_type, priority, units, remainder

    def process_ros_sensors(self, sensors: list[str], sensor_headings: list[str]):
        """given pre-parsed sensor headings, create sensor objects"""
        # remove the ctd.rosette_summary() call — sensor_headings is passed in
        existing_sensors = GlobalSampleType.objects.filter(is_sensor=True).values_list('short_name',
                                                                                       flat=True).distinct()
        new_sensors: list[GlobalSampleType] = []
        for sensor in sensor_headings:
            sensor_mapping = re.split(": ", sensor)
            if sensor_mapping[0].lower() not in sensors:
                continue
            if GlobalSampleType.objects.filter(short_name__iexact=sensor_mapping[0]).exists():
                continue

            sensor_type_string, priority, units, other = self.parse_sensor(sensor_mapping[1])
            long_name = sensor_type_string
            if other:
                long_name += f", {other}"

            if units:
                long_name += f" [{units}]"

            if sensor_mapping[0] in existing_sensors:
                continue

            sensor_type = GlobalSampleType(short_name=sensor_mapping[0], long_name=long_name, is_sensor=True)
            sensor_type.name = sensor_type_string
            sensor_type.priority = priority if priority else 1
            sensor_type.units = units if units else None
            sensor_type.comments = other

            new_sensors.append(sensor_type)

        if new_sensors:
            GlobalSampleType.objects.bulk_create(new_sensors)

    def process_common_sensors(self, sensors: list[str]):
        # Given a list of sensor names, or 'column headings', create a list of mission sensors that don't already exist
        create_sensors: list[GlobalSampleType] = []

        for sensor in sensors:

            # if the sensor exists, skip it
            if GlobalSampleType.objects.filter(short_name__iexact=sensor).exists():
                continue

            details: list = self._parse_sensor_name(sensor)
            long_name = details[2]  # basically all we have at the moment is the units of measure
            sensor_details = GlobalSampleType(short_name=details[0], long_name=long_name, is_sensor=True)
            sensor_details.priority = details[1]
            sensor_details.units = details[2]

            create_sensors.append(sensor_details)

        if create_sensors:
            GlobalSampleType.objects.bulk_create(create_sensors)

    def process_sensors(self, column_headers: list[str], sensor_headings: list[str]):
        if sensor_headings:
            self.process_ros_sensors(sensors=column_headers, sensor_headings=sensor_headings)

        # The ROS file gives us all kinds of information about special sensors that are commonly added and removed from
        # the CTD, but it does not cover sensors that are normally on the CTD by default. i.e. Sal00, Potemp090C,
        # Sigma-é00
        existing_sensors = [sensor.short_name.lower() for sensor in GlobalSampleType.objects.all()]
        columns = [column_header for column_header in column_headers if column_header.lower() not in existing_sensors]
        self.process_common_sensors(sensors=columns)

    def process_bottles(self, dataframe):
        data_frame_avg = dataframe[dataframe['Statistic'] == 'avg']
        data_frame_avg.columns = map(str.lower, data_frame_avg.columns)

        column_mapping = {
            key: col for key, col in btl_column_mapping.items() if any(c in data_frame_avg.columns for c in col)
        }

        existing_bottles = {bottle.bottle_id: bottle for bottle in self.event.bottles.all()}

        create_bottles = []
        update_bottles = []
        update_fields = set()
        bottle_count = data_frame_avg.shape[0]
        bottles_added = 0
        for index, (row, bottle) in enumerate(data_frame_avg.iterrows()):
            logger_notifications.info(_("Processing bottles for event") + f" {self.event.event_id} : %d/%d", (index + 1), bottle_count)
            try:
                bottle_id: int = self._get_bottle_id(bottle, column_mapping, bottles_added)

                self._validate_bottle_id(bottle_id)

                closed = pytz.utc.localize(bottle['date'])
                pressure = bottle.get(column_mapping.get('pressure', [None])[0])
                latitude = bottle.get(column_mapping.get('latitude', [None])[0])
                longitude = bottle.get(column_mapping.get('longitude', [None])[0])

                if bottle_id in existing_bottles:
                    existing_bottle = existing_bottles[bottle_id]
                    updated_fields = self._update_existing_bottle(existing_bottle, closed, pressure, latitude, longitude)

                    if updated_fields:
                        update_bottles.append(existing_bottle)
                        update_fields.update(updated_fields)
                else:
                    new_bottle = core_models.Bottle(event=self.event, bottle_id=bottle_id, bottle_number=row, closed=closed, pressure=pressure)
                    if latitude:
                        new_bottle.latitude = latitude
                    if longitude:
                        new_bottle.longitude = longitude
                    create_bottles.append(new_bottle)

                bottles_added += 1
            except Exception as e:
                logger.exception(e)
                self.errors_to_create.append(core_models.FileError(
                    mission=self.event.mission, file_name=self.btl_filename, message=str(e), code=101
                ))

        if create_bottles:
            core_models.Bottle.objects.bulk_create(create_bottles)

        if update_bottles:
            core_models.Bottle.objects.bulk_update(update_bottles, update_fields)


    def process_actions(self):
        btl_mapping = self._get_field_mapping()

        sounding_label = btl_mapping['sounding'].get('label', 'Sounding').upper()
        sounding_default = btl_mapping['sounding'].get('default', None)

        lat_label = btl_mapping['latitude'].get('label', 'Latitude').upper()
        lat_default = btl_mapping['latitude'].get('default', None)

        lon_label = btl_mapping['longitude'].get('label', 'Longitude').upper()
        lon_default = btl_mapping['longitude'].get('default', None)

        station_name = btl_mapping['station'].get('label', 'Station_Name').upper()
        station_default = btl_mapping['station'].get('default', None)

        station = GlobalStation.objects.filter(name__iexact=station_name)

        sounding = self.file_properties.get(sounding_label, sounding_default)
        latitude = self.file_properties.get(lat_label, lat_default)
        longitude = self.file_properties.get(lon_label, lon_default)

        if self.event.actions.count() <= 0:
           # For all files, sounding is required
           if not sounding:
               message = _("Could not find sounding label to create actions: ") + sounding_label
               message += "\n" + _("You may have to load events from (Elog, Andes or CSV) first")
               raise KeyError(message)

           if not latitude:
               message = _("Could not find latitude label to create actions: ") + lat_label
               message += "\n" + _("You may have to load events from (Elog, Andes or CSV) first")
               raise KeyError(message)

           if not longitude:
               message = _("Could not find longitude label to create actions: ") + lon_label
               message += "\n" + _("You may have to load events from (Elog, Andes or CSV) first")
               raise KeyError(message)

        try:
           sounding = sounding.strip()
           lat_array = latitude.strip().split(" ")
           lon_array = longitude.strip().split(" ")
        except Exception as e:
           message = f"Invalid decimal degree Lat/Lon provided ({latitude[0].strip() if latitude else 'Missing'}, {longitude[0].strip() if longitude else 'Missing'})"
           raise ValueError(message) from e

        lat = self._process_coordinate(lat_array, is_latitude=True)
        lon = self._process_coordinate(lon_array, is_latitude=False)

        if station.exists():
           station = station.first()
           if station.latitude and station.longitude:
               station_coords = (station.latitude, station.longitude)
               new_coords = (lat, lon)
               distance_km = geodesic(station_coords, new_coords).kilometers
               if distance_km > 1:
                   error_message = _("Coordinates are more than 1 km away from the nominal station") + f" : {station_coords}"
                   core_models.EventError.objects.create(
                       event=self.event,
                       message=error_message,
                       type=core_models.ErrorType.validation,
                       code=102
                   )

        for btl in self.event.bottles.all():
           btl.latitude = lat
           btl.longitude = lon
           btl.save()

        # For all file types, process bottles and actions
        bottom_bottle = self.event.bottles.order_by('pressure').first()
        surface_bottle = self.event.bottles.order_by('pressure').last()

        self._create_update_action(core_models.ActionType.bottom, bottom_bottle, sounding, lat, lon)
        self._create_update_action(core_models.ActionType.recovered, surface_bottle, sounding, lat, lon)

        self.event.sample_id = min(bottom_bottle.bottle_id, surface_bottle.bottle_id)
        self.event.end_sample_id = max(bottom_bottle.bottle_id, surface_bottle.bottle_id)

        self.event.save()

    def process_data(self, file_name: str, data_frame: pd.DataFrame, column_headers: list[str]):
        # we only want to use rows in the BTL file marked as 'avg' in the statistics column
        skipped_rows = getattr(data_frame, "_metadata")["skiprows"]

        data_frame_avg = data_frame[data_frame['Statistic'] == 'avg']
        data_frame_avg._metadata = data_frame._metadata

        # convert all column names to lowercase
        data_frame_avg.columns = map(str.lower, data_frame_avg.columns)

        column_mapping = {
            key: col for key, col in btl_column_mapping.items() if any(c in data_frame_avg.columns for c in col)
        }

        new_samples: List[core_models.Sample] = []
        update_samples: List[core_models.Sample] = []
        new_discrete_samples: List[core_models.DiscreteSampleValue] = []
        update_discrete_samples: List[core_models.DiscreteSampleValue] = []

        bottles = self.event.bottles.all()

        # make global sample types local to this mission to be attached to samples when they're created
        missing_sample_types = [name for name in column_headers if name.lower() not in self.mission_sample_types.keys()]
        if len(missing_sample_types) > 0:
            logger.info("Creating local sample types")
            new_sample_types = []
            for name in missing_sample_types:
                global_sampletype = GlobalSampleType.objects.get(short_name__iexact=name)
                new_sampletype = core_models.MissionSampleType(
                    mission=self.mission, is_sensor=True, name=global_sampletype.short_name,
                    long_name=global_sampletype.long_name, datatype=global_sampletype.datatype,
                    priority=global_sampletype.priority)
                new_sample_types.append(new_sampletype)

            if len(new_sample_types) > 0:
                core_models.MissionSampleType.objects.bulk_create(new_sample_types)
                self.mission_sample_types = {
                    sample_type.name.lower(): sample_type for sample_type in self.mission.mission_sample_types.all()
                }

        sample_types = self.mission_sample_types
        bottles_added = 0
        for index, (row, data) in enumerate(data_frame_avg.iterrows()):
            logger_notifications.info(_("Processing data for event") + f" {self.event.event_id} : %d/%d", (index + 1),
                                      data_frame_avg.shape[0])
            bottle_id = self._get_bottle_id(data, column_mapping, bottles_added)

            if not bottles.filter(bottle_id=bottle_id).exists():
                message = _("Bottle does not exist for event")
                message += _("Event") + f" #{self.event.event_id} " + _("Bottle ID") + f" #{bottle_id}"

                logger.warning(message)
                continue

            bottle = bottles.get(bottle_id=bottle_id)
            bottles_added += 1
            for column in column_headers:
                sample_type = sample_types[column.lower()]

                if (sample := core_models.Sample.objects.filter(bottle=bottle, type=sample_type)).exists():
                    sample = sample.first()
                    if utils.updated_value(sample, 'file', file_name):
                        update_samples.append(sample)

                    # sensor data doesn't have replicates, so we're always just dealing with the first discrete value
                    discrete_value = sample.discrete_values.first()
                    if discrete_value:
                        # there's a case here where a mission may have been created with uncalibrated data,
                        # then bad values were removed so the mission could be uploaded to Biochem. This
                        # happens frequently with pH data. When calibrated BTL files are loaded later,
                        # discrete_value will be None and utils.updated_value will raise a NoneType exception
                        new_value = data[column.lower()]
                        if utils.updated_value(discrete_value, 'value', new_value):
                            update_discrete_samples.append(discrete_value)
                    else:
                        discrete_value = core_models.DiscreteSampleValue(sample=sample, value=data[column.lower()])
                        new_discrete_samples.append(discrete_value)
                else:
                    sample = core_models.Sample(bottle=bottle, type=sample_types[column], file=file_name)
                    new_samples.append(sample)
                    discrete_value = core_models.DiscreteSampleValue(sample=sample, value=data[column.lower()])
                    new_discrete_samples.append(discrete_value)

        if len(new_samples) > 0:
            logger.info("Creating CTD samples for file" + f" : {file_name}")
            core_models.Sample.objects.bulk_create(new_samples)

        if len(update_samples) > 0:
            logger.info("Creating CTD samples for file" + f" : {file_name}")
            core_models.Sample.objects.bulk_update(update_samples, ['file'])

        if len(new_discrete_samples) > 0:
            logger.info("Adding values to samples" + f" : {file_name}")
            core_models.DiscreteSampleValue.objects.bulk_create(new_discrete_samples)

        if len(update_discrete_samples) > 0:
            logger.info("Updating sample values" + f" : {file_name}")
            core_models.DiscreteSampleValue.objects.bulk_update(update_discrete_samples, ['value'])

    def parse(self):
        self.mission.file_errors.filter(file_name=self.btl_filename).delete()
        self.event.validation_errors.all().delete()

        parsed = self.parse_to_intermediate()

        # propagate file_properties so process_actions can access it
        self.file_properties = parsed.file_properties

        self.process_bottles(parsed.bottles_df)
        if self.errors_to_create:
            core_models.FileError.objects.bulk_create(self.errors_to_create)
            self.errors_to_create = []

        self.process_sensors(column_headers=parsed.col_headers, sensor_headings=parsed.sensor_headings)
        self.process_data(parsed.btl_filename, parsed.data_df, column_headers=parsed.col_headers)

        is_fixed_station = self.mission.fixed_station
        if is_fixed_station:
            self.process_actions()

        bottles = self.event.bottles.order_by('closed')
        if bottles.first().pressure < bottles.last().pressure:
            gear_type_code = 90000215
        else:
            gear_type_code = 90000171

        gear_type = bio_models.BCGear.objects.get(gear_seq=gear_type_code)
        for bottle in bottles:
            bottle.gear_type = gear_type

        core_models.Bottle.objects.bulk_update(bottles, ['gear_type'])

    def __init__(self, event: core_models.Event, btl_filename: str, btl_stream: io.StringIO, ros_stream: io.StringIO | None):
        self.field_mappings = None
        self.errors_to_create = []
        self.event = event
        self.mission = self.event.mission
        self.mission_sample_types = {
            sample_type.name.lower(): sample_type for sample_type in self.mission.mission_sample_types.all()
        }
        self.database = event._state.db

        self.btl_filename = btl_filename
        self.btl_stream: io.StringIO = btl_stream
        self.ros_stream: io.StringIO|None = ros_stream

        self.file_properties: dict = None


class FixStationBulkParser:

    file_list = []
    errors_to_create = []
    mission = None

    def create_events(self) -> dict:

        mapping = get_btl_mapping()
        label_event = mapping['event_id'].get('label', 'Event_Number').upper()
        label_serial_number = mapping['instrument_name'].get('label', 'Instrument_serial_number').upper()
        label_station = mapping['station'].get('label', 'Station_Name').upper()

        # Process all files
        create_events = []
        parsed_events = {}

        # Cache instruments to avoid repeated queries
        instrument_cache = {}
        station = None

        # Fetch existing events as a list of event_ids tuples
        existing_events = self.mission.events.filter(instrument__type=core_models.InstrumentType.ctd).values_list('event_id', flat=True)
        bottle_count = len(self.file_list)

        serial_number_default = mapping['instrument_name'].get('default', 'CTD')

        # How do we know if this is a fixed station?
        # if CTD events were loaded from a CSV, ANDES or Elog file, this is not a fixed station
        is_fixed_station = self.mission.fixed_station

        for index, file in enumerate(self.file_list):
            logger_notifications.info(_("checking events") + " : %d/%d", (index + 1), bottle_count)
            file_name = os.path.basename(file)

            btl_sample_file = open(file, mode='rb')
            btl_data = io.StringIO(btl_sample_file.read().decode("cp1252"))
            try:
                if is_fixed_station:
                    validate_fixed_station_file(btl_data)
                else:
                    validate_btl_file(btl_data)
            except KeyError as e:
                logger.exception(e)
                self.errors_to_create.append(core_models.FileError(mission=self.mission, file_name=file_name, message=str(e), code=104))
                continue
            except ValueError as e:
                logger.exception(e)
                self.errors_to_create.append(core_models.FileError(mission=self.mission, file_name=file_name, message=str(e), code=103))
                continue
            except Exception as e:
                logger.exception(e)
                self.errors_to_create.append(core_models.FileError(mission=self.mission, file_name=file_name, message=str(e), code=105))
                continue

            try:
                # Construct the expected .ros file path
                ros_file = os.path.splitext(file)[0] + ".ros"
                if not os.path.exists(ros_file):
                    logger.warning(f"No matching .ros file found for: {file}")
                    ros_file = None
                    # raise FileNotFoundError(f"No matching .ros file found for: {file}")

                data = ctd.read.from_btl(file)

                header: str = data._metadata['header']
                header_lines: str = re.findall(r'\*\*.*', header, re.MULTILINE)
                cleaned_lines: list[str] = [re.sub(r'\*\*', '', line).split(":") for line in header_lines]
                event_properties: dict = {cl[0].strip().upper(): cl[1].strip() for cl in cleaned_lines if len(cl) >= 2}

                event_id = event_properties.get(label_event)
                parsed_events[event_id] = [file, ros_file]

                if int(event_id) not in existing_events:
                    if station is None:
                        # Get station once loop (since it's constant)
                        station_name = event_properties.get(label_station)
                        try:
                            station = core_models.Station.objects.get(name__iexact=station_name)
                        except core_models.Station.DoesNotExist:
                            station = core_models.Station.objects.create(name=station_name)

                    serial_number = event_properties.get(label_serial_number, serial_number_default)
                    ctd_instrument = core_models.InstrumentType.ctd

                    # Get or create instrument (using cache)
                    instrument_key = (ctd_instrument, serial_number)
                    if instrument_key not in instrument_cache:
                        instrument_cache[instrument_key] = core_models.Instrument.objects.get_or_create(
                            type=ctd_instrument, name=serial_number)[0]

                    instrument = instrument_cache[instrument_key]

                    # Get or create event
                    event = core_models.Event(
                        mission=self.mission,
                        event_id=int(event_id),
                        instrument=instrument,
                        station=station
                    )

                    create_events.append(event)
            except Exception as e:
                message = _("Error parsing Header ") + f": {file}: {e}"
                logger.error(message)
                logger.exception(e)
                error = core_models.FileError(
                    mission=self.mission,
                    file_name=file_name,
                    message=message,
                    type=core_models.ErrorType.validation,
                    code=100
                )
                self.errors_to_create.append(error)

        if create_events:
            core_models.Event.objects.bulk_create(create_events)

        # we're going to attach the event files to the event.
        new_files = []
        btl_file_type = core_models.FileType.objects.get_or_create(name='BTL', extension='BTL',
                                                                   description='Bottle files')[0]

        ros_file_type = core_models.FileType.objects.get_or_create(name='ROS', extension='ROS',
                                                                   description='Rosette files')[0]
        for event_id in parsed_events:
            btl_file = os.path.basename(parsed_events[event_id][0])
            event = core_models.Event.objects.get(event_id=event_id, instrument__type=core_models.InstrumentType.ctd)
            event.files.filter(file_type__in=[btl_file_type, ros_file_type]).delete()

            new_files.append(core_models.EventFile(event=event, file_name=btl_file, file_type=btl_file_type))

            if len(parsed_events) > 1:
                ros_file = os.path.basename(parsed_events[event_id][1])
                new_files.append(core_models.EventFile(event=event, file_name=ros_file, file_type=ros_file_type))

        if new_files:
            core_models.EventFile.objects.bulk_create(new_files)

        return parsed_events

    def process_bottles(self, parsed_events: dict) -> list[ParsedBtlFile]:
        """Thread the pure file parsing, return list of ParsedBtlFile for sequential DB writes."""
        threads = []
        results = []  # ParsedBtlFile objects collected from threads
        thread_errors = []  # (filename, message) tuples
        bottle_count = len(parsed_events)

        for index, (event_id, files) in enumerate(parsed_events.items()):
            logger_notifications.info(_("Parsing Bottle Data") + " : %d/%d", (index + 1), bottle_count)
            btl_file = files[0]
            ros_file = files[1]

            thread = threading.Thread(
                target=parse_file_to_intermediate,
                args=(btl_file, ros_file, results, thread_errors)
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Convert thread errors into FileError objects
        for filename, message in thread_errors:
            self.errors_to_create.append(core_models.FileError(
                mission=self.mission, file_name=filename, message=message,
                type=core_models.ErrorType.validation, code=101
            ))

        return results

    def parse(self):
        self.errors_to_create = []
        file_names = [os.path.basename(f) for f in self.file_list]
        core_models.FileError.objects.filter(
            mission=self.mission, file_name__in=file_names, code__gte=100, code__lte=299
        ).delete()

        parsed_events = self.create_events()

        # Step 3: threads do pure parsing
        parsed_files = self.process_bottles(parsed_events)

        # Step 4 (next step): sequential DB writes
        for parsed in parsed_files:
            event = core_models.Event.objects.get(
                event_id=parsed.event_id,
                instrument__type=core_models.InstrumentType.ctd
            )
            writer = FixStationParser(event=event, btl_filename=parsed.btl_filename,
                                      btl_stream=None, ros_stream=None)
            writer.file_properties = parsed.file_properties
            writer.process_bottles(parsed.bottles_df)
            writer.process_sensors(column_headers=parsed.col_headers, sensor_headings=parsed.sensor_headings)
            writer.process_data(parsed.btl_filename, parsed.data_df, column_headers=parsed.col_headers)
            if self.mission.fixed_station:
                writer.process_actions()
            # gear type
            bottles = event.bottles.order_by('closed')
            if bottles.first() and bottles.last():
                gear_type_code = 90000215 if bottles.first().pressure < bottles.last().pressure else 90000171
                gear_type = bio_models.BCGear.objects.get(gear_seq=gear_type_code)
                for bottle in bottles:
                    bottle.gear_type = gear_type
                core_models.Bottle.objects.bulk_update(bottles, ['gear_type'])

        if self.errors_to_create:
            core_models.FileError.objects.bulk_create(self.errors_to_create)


    def __init__(self, mission: core_models.Mission, files: list):
        self.file_list = files
        self.mission = mission