# This is for parsing bottle files specifically for fix stations
import pytz
import io
import re
import os
import ctd
import json

import numpy as np
import pandas as pd

from geopy.distance import geodesic
from typing import List, Any

from django.utils.translation import gettext as _

from config import utils
from core import models as core_models
from bio_tables import models as bio_models
from settingsdb.models import  GlobalSampleType, GlobalStation

import logging

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.fixstationparser')


def get_btl_mapping() -> dict:
    config_dir = 'file_configs'
    default_file = os.path.join(config_dir, 'default_btl.json')
    btl_file = os.path.join(config_dir, 'btl.json')

    file_to_load = default_file if os.path.exists(default_file) else btl_file

    with open(file_to_load, 'r') as f:
        return json.load(f)


def validate_file(btl_stream, file_properties: dict = None):
    btl_mapping = get_btl_mapping()

    if not file_properties:
        data: pd.DataFrame = ctd.read.from_btl(btl_stream)

        header = data._metadata['header']

        header_lines: str = re.findall(r'\*\*.*', header, re.MULTILINE)
        cleaned_lines: list[str] = [re.sub(r'\*\*', '', line).split(":") for line in header_lines]
        file_properties = {cl[0].strip().upper(): cl[1].strip() for cl in cleaned_lines}

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

    if (event_id := file_properties.get(event_label.upper(), event_id)) is None:
        raise ValueError("Event ID is missing")

    if (station_name := file_properties.get(station_label.upper(), station_name)) is None:
        raise ValueError("Station Name is missing")

    try:
        event = core_models.Event.objects.get(event_id=event_id)
    except core_models.Event.DoesNotExist:
        message = _("Event matching file doesn't exist, you may have to load events from Elog, ANDES or CSV first")
        raise ValueError(message)

    # if the event doesn't have actions, then these fields will be required
    has_actions = event.actions.all().exists()
    if not has_actions:
        if (sounding := file_properties.get(sounding_label.upper(), sounding)) is None:
            raise ValueError("Sounding is missing from the header. Cannot create event")

        if (latitude := file_properties.get(lat_label.upper(), latitude)) is None:
            raise ValueError("Latitude is missing from the header. Cannot create event")

        if (longitude := file_properties.get(lon_label.upper(), longitude)) is None:
            raise ValueError("Longitude is missing from the header. Cannot create event")


class FixStationParser:
    field_mappings: dict = None
    file_properties: dict = None

    def _get_units(self, sensor_description: str) -> tuple[str | Any, str]:
        """given a sensor description, find, remove and return the uom and remaining string"""
        uom_pattern = " \\[(.*?)\\]"
        uom = re.findall(uom_pattern, sensor_description)
        uom = uom[0] if uom else ""
        return uom, re.sub(uom_pattern, "", sensor_description)

    def _get_priority(self, sensor_description: str) -> tuple[int, str]:
        """given a sensor description, with units removed, find, remove and return the priority and remaining string"""
        priority_pattern = r", (\d)"
        priority = re.findall(priority_pattern, sensor_description)
        priority = priority[0] if priority else 1
        return int(priority), re.sub(priority_pattern, "", sensor_description)

    def _get_sensor_type(self, sensor_description: str) -> tuple[str, str]:
        """given a sensor description with priority and units removed return the sensor type and remaining string"""
        remainder = sensor_description.split(", ")
        # if the sensor type wasn't in the remaining comma seperated list then it is the first value of the description
        return remainder[0], ", ".join([remainder[i] for i in range(1, len(remainder)) if len(remainder) > 1])

    def get_field_mapping(self) -> dict:
        if self.field_mappings:
            return self.field_mappings

        self.field_mappings = get_btl_mapping()

        return self.field_mappings

    def process_bottles(self, dataframe):
        data_frame_avg = dataframe[dataframe['Statistic'] == 'avg']
        data_frame_avg.columns = map(str.lower, data_frame_avg.columns)

        dataframe_dict = {}
        if "prdm" in data_frame_avg.columns:
            dataframe_dict['pressure'] = "prdm"
        elif "prsm" in data_frame_avg.columns:
            dataframe_dict['pressure'] = "prsm"

        if "latitude" in data_frame_avg.columns:
            dataframe_dict['latitude'] = "latitude"

        if "longitude" in data_frame_avg.columns:
            dataframe_dict['longitude'] = "longitude"

        if "bottle_" in data_frame_avg.columns:
            # if present this is the Bottle ID to use instead of the event.sample_id + Bottle number
            dataframe_dict['bottle_id'] = "bottle_"

        existing_bottles = {bottle.bottle_id: bottle for bottle in self.event.bottles.all()}

        logger_notifications.info(_("Processing Bottles"))
        create_bottles = []
        update_bottles = []
        update_fields = set()
        bottles_added = 0
        for row, bottle in data_frame_avg.iterrows():
            update_bottle_fields = set('')
            if 'bottle_id' in dataframe_dict:
                bottle_id: int = bottle[dataframe_dict['bottle_id']]
            elif self.event.sample_id:
                bottle_id: int = self.event.sample_id + bottles_added
            else:
                raise ValueError(_("Require either S/N column in BTL file or Start IDs specified for the Event"))

            if (btl := core_models.Bottle.objects.exclude(event=self.event).filter(bottle_id=bottle_id)).exists():
                # if the bottle exists for an event other than the current event
                if not (btl.first().event == self.event):
                    raise KeyError(_("Bottle with provided ID already exists") + f" {int(bottle_id)}")

            closed = pytz.utc.localize(bottle['date'])
            pressure = bottle[dataframe_dict['pressure']]

            if bottle_id in existing_bottles.keys():
                bottle = existing_bottles[bottle_id]
                update_bottle_fields.add(utils.updated_value(bottle, 'closed', closed))
                update_bottle_fields.add(utils.updated_value(bottle, 'pressure', pressure))
                if '' in update_bottle_fields:
                    update_bottle_fields.remove('')

                if len(update_bottle_fields) > 0:
                    update_bottles.append(bottle)
                    update_fields.update(update_bottle_fields)
                    bottles_added += 1
            else:
                bottle = core_models.Bottle(event=self.event, bottle_id=bottle_id)
                bottle.closed = closed
                bottle.pressure = pressure
                create_bottles.append(bottle)
                bottles_added += 1

        if len(create_bottles) > 0:
            core_models.Bottle.objects.bulk_create(create_bottles)

        if len(update_bottles) > 0:
            core_models.Bottle.objects.bulk_update(update_bottles, update_fields)

    def parse_sensor(self, sensor: str) -> tuple[Any, Any, Any, Any]:
        """given a sensor description parse out the type, priority and units """
        units, sensor_a = self._get_units(sensor)
        priority, sensor_b = self._get_priority(sensor_a)
        sensor_type, remainder = self._get_sensor_type(sensor_b)

        return sensor_type, priority, units, remainder

    def parse_sensor_name(self, sensor: str) -> list[str | int | None | Any]:
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

    def process_ros_sensors(self, sensors: list[str]):
        """given a ROS file create sensors objects from the config portion of the file"""

        summary = ctd.rosette_summary(self.ros_stream)
        sensor_headings = re.findall(r"# name \d+ = (.*?)\n", getattr(summary, '_metadata')['config'])

        existing_sensors = GlobalSampleType.objects.filter(is_sensor=True).values_list('short_name',
                                                                                       flat=True).distinct()
        new_sensors: list[GlobalSampleType] = []
        for sensor in sensor_headings:
            # [column_name]: [sensor_details]
            sensor_mapping = re.split(": ", sensor)

            # if this sensor is not in the list of sensors we're looking for, skip it.
            if sensor_mapping[0].lower() not in sensors:
                continue

            # if the sensor already exists, skip it
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

            details: list = self.parse_sensor_name(sensor)
            long_name = details[2]  # basically all we have at the moment is the units of measure
            sensor_details = GlobalSampleType(short_name=details[0], long_name=long_name, is_sensor=True)
            sensor_details.priority = details[1]
            sensor_details.units = details[2]

            create_sensors.append(sensor_details)

        if create_sensors:
            GlobalSampleType.objects.bulk_create(create_sensors)

    def process_sensors(self, column_headers: list[str]):
        # Given a list of column, 'SampleType' objects will be created if they do not already exist
        # or aren't part of a set of excluded sensors
        self.process_ros_sensors(sensors=column_headers)

        # The ROS file gives us all kinds of information about special sensors that are commonly added and removed from
        # the CTD, but it does not cover sensors that are normally on the CTD by default. i.e. Sal00, Potemp090C,
        # Sigma-é00
        existing_sensors = [sensor.short_name.lower() for sensor in GlobalSampleType.objects.all()]
        columns = [column_header for column_header in column_headers if column_header.lower() not in existing_sensors]
        self.process_common_sensors(sensors=columns)

    def process_data(self, file_name: str, data_frame: pd.DataFrame, column_headers: list[str]):
        mission = self.event.mission

        # we only want to use rows in the BTL file marked as 'avg' in the statistics column
        skipped_rows = getattr(data_frame, "_metadata")["skiprows"]

        data_frame_avg = data_frame[data_frame['Statistic'] == 'avg']
        data_frame_avg._metadata = data_frame._metadata

        # convert all column names to lowercase
        data_frame_avg.columns = map(str.lower, data_frame_avg.columns)

        new_samples: List[core_models.Sample] = []
        update_samples: List[core_models.Sample] = []
        new_discrete_samples: List[core_models.DiscreteSampleValue] = []
        update_discrete_samples: List[core_models.DiscreteSampleValue] = []

        bottles = core_models.Bottle.objects.filter(event=self.event)

        # make global sample types local to this mission to be attached to samples when they're created
        logger.info("Creating local sample types")
        for name in column_headers:
            if not mission.mission_sample_types.filter(name__iexact=name).exists():
                global_sampletype = GlobalSampleType.objects.get(short_name__iexact=name)
                new_sampletype = core_models.MissionSampleType(mission=mission, is_sensor=True,
                                                               name=global_sampletype.short_name,
                                                               long_name=global_sampletype.long_name,
                                                               datatype=global_sampletype.datatype,
                                                               priority=global_sampletype.priority)
                new_sampletype.save()

        sample_types = {
            sample_type.name.lower(): sample_type for sample_type in mission.mission_sample_types.all()
        }

        bottles_added = 0
        for row, data in data_frame_avg.iterrows():
            # if the Bottle S/N column is present then use that values as the bottle ID
            if 'bottle_' in data:
                bottle_id = int(data['bottle_'])
            elif self.event.sample_id:
                bottle_id = self.event.sample_id + bottles_added
            else:
                raise ValueError(
                    _("Require either S/N column in BTL file or Start and End Bottle IDs specified for the Event"))

            if not bottles.filter(bottle_id=bottle_id).exists():
                message = _("Bottle does not exist for event")
                message += _("Event") + f" #{self.event.event_id} " + _("Bottle ID") + f" #{bottle_id}"

                logger.warning(message)
                continue

            bottle = bottles.get(bottle_id=bottle_id)
            for column in column_headers:
                sample_type = sample_types[column.lower()]

                if (sample := core_models.Sample.objects.filter(bottle=bottle,
                                                                                     type=sample_type)).exists():
                    sample = sample.first()
                    if utils.updated_value(sample, 'file', file_name):
                        update_samples.append(sample)

                    discrete_value = sample.discrete_values.all().first()
                    new_value = data[column.lower()]
                    if utils.updated_value(discrete_value, 'value', new_value):
                        update_discrete_samples.append(discrete_value)
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

        # Invalid format
        else:
            raise ValueError(f"Unrecognized {coord_type} format: {' '.join(coord_array)}")

    def process_actions(self, data: pd.DataFrame):
        btl_mapping = self.get_field_mapping()

        # We're in the process of updating the header for fixstation BTL files.
        # station_label = self.get_mapping('event_id')
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
        latitude = self.file_properties.get(lat_label, sounding_default)
        longitude = self.file_properties.get(lon_label, sounding_default)

        # First determine if this is a fixed station BTL file or an AZMP bottle file
        # Fixed station files have latitude and longitude in the header
        is_fixed_station = latitude is not None and longitude is not None

        if self.event.actions.count() <= 0:
           # For all files, sounding is required
           if not sounding:
               message = _("Could not find sounding label to create actions: ") + sounding_label
               message += "\n" + _("You may have to load events from (Elog, Andes or CSV) first")
               raise KeyError(message)

           # For fixed station files, latitude and longitude are also required
           if is_fixed_station:
               if not latitude:
                   message = _("Could not find latitude label to create actions: ") + lat_label
                   message += "\n" + _("You may have to load events from (Elog, Andes or CSV) first")
                   raise KeyError(message)

               if not longitude:
                   message = _("Could not find longitude label to create actions: ") + lon_label
                   message += "\n" + _("You may have to load events from (Elog, Andes or CSV) first")
                   raise KeyError(message)

        # Process latitude and longitude only for fixed station files
        if is_fixed_station:
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
        else:
           # For AZMP files, just use the sounding value without lat/lon processing
           sounding = sounding[0].strip() if sounding else None

        # For all file types, process bottles and actions
        bottom_bottle = self.event.bottles.order_by('pressure').first()
        surface_bottle = self.event.bottles.order_by('pressure').last()

        # Create or update actions with appropriate coordinate values
        if is_fixed_station:
            self._create_update_action(core_models.ActionType.bottom, bottom_bottle, sounding, lat, lon)
            self._create_update_action(core_models.ActionType.recovered, surface_bottle, sounding, lat, lon)

            self.event.sample_id = min(bottom_bottle.bottle_id, surface_bottle.bottle_id)
            self.event.end_sample_id = max(bottom_bottle.bottle_id, surface_bottle.bottle_id)

            self.event.save()

    def parse(self):
        self.event.mission.file_errors.filter(file_name=self.btl_filename).delete()
        self.event.validation_errors.all().delete()

        data: pd.DataFrame = ctd.read.from_btl(self.btl_stream)

        header = data._metadata['header']

        header_lines: str = re.findall(r'\*\*.*', header, re.MULTILINE)
        cleaned_lines: list[str] = [re.sub(r'\*\*', '', line).split(":") for line in header_lines]
        self.file_properties = {cl[0].strip().upper(): cl[1].strip() for cl in cleaned_lines}

        # These are columns we either have no use for or we will specifically call and use later
        # The Bottle column is the rosette number of the bottle
        # The Bottle_ column, if present, is the bottle.bottle_id for a bottle.
        exclude = ['bottle', 'bottle_', 'date', 'scan', 'times', 'statistic',
                   'longitude', 'latitude', 'nbf', 'flag']
        col_headers = [instrument.lower() for instrument in data.columns if instrument.lower() not in exclude]

        self.process_bottles(data)
        self.process_sensors(column_headers=col_headers)
        self.process_data(self.btl_filename, data, column_headers=col_headers)

        # now create bottom, recover actions, event.sample_id, event.end_sample_id and sounding if they don't exist
        self.process_actions(data)

        # if the bottle with the highest pressure was the last bottle closed we're using bottles
        # on a wire. If it was the first one closed we're using a CTD + Rosette
        gear_type_code = 90000002  # Niskin bottle of unknown size
        bottles = self.event.bottles.all()
        if bottles.first().pressure > bottles.last().pressure:
            gear_type_code = 90000215  # CTD + Niskin bottles on a wire, not rosette
        else:
            gear_type_code = 90000171  # CTD and rosette bottle sampler

        gear_type = bio_models.BCGear.objects.get(gear_seq=gear_type_code)
        for bottle in bottles:
            bottle.gear_type = gear_type

        core_models.Bottle.objects.bulk_update(bottles, ['gear_type'])

    def __init__(self, event: core_models.Event, btl_filename: str, btl_stream: io.StringIO, ros_stream: io.StringIO):
        self.event = event
        self.database = event._state.db

        self.btl_filename = btl_filename
        self.btl_stream: io.StringIO = btl_stream
        self.ros_stream: io.StringIO = ros_stream

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

        # Fetch existing events as a list of (event_id, instrument.pk) tuples
        existing_events = list(self.mission.events.values_list('event_id', 'instrument__pk'))
        bottle_count = len(self.file_list)
        for index, file in enumerate(self.file_list):
            logger_notifications.info(_("Updating events") + " : %d/%d", (index + 1), bottle_count)
            file_name = os.path.basename(file)

            btl_sample_file = open(file, mode='rb')
            btl_data = io.StringIO(btl_sample_file.read().decode("cp1252"))
            try:
                validate_file(btl_data)
            except ValueError as e:
                message = _("Missing BTL headers or missing event") + f": {file_name}: {e}"
                self.errors_to_create.append(core_models.FileError(mission=self.mission, file_name=file_name, message=message, code=103))
                continue

            try:
                # Construct the expected .ros file path
                ros_file = os.path.splitext(file)[0] + ".ros"
                if not os.path.exists(ros_file):
                    raise FileNotFoundError(f"No matching .ros file found for: {file}")

                data = ctd.read.from_btl(file)
                header: str = data._metadata['header']
                header_lines: str = re.findall(r'\*\*.*', header, re.MULTILINE)
                cleaned_lines: list[str] = [re.sub(r'\*\*', '', line).split(":") for line in header_lines]
                event_properties: dict = {cl[0].strip().upper(): cl[1].strip() for cl in cleaned_lines}

                if station is None:
                    # Get station once loop (since it's constant)
                    station_name = event_properties.get(label_station)
                    try:
                        station = core_models.Station.objects.get(name__iexact=station_name)
                    except core_models.Station.DoesNotExist:
                        station = core_models.Station.objects.create(name=station_name)

                event_id = event_properties.get(label_event)
                parsed_events[event_id] = [file, ros_file]

                serial_number_default = mapping['instrument_name'].get('default', 'CTD')
                serial_number = event_properties.get(label_serial_number, serial_number_default)
                ctd_instrument = core_models.InstrumentType.ctd

                # Get or create instrument (using cache)
                instrument_key = (ctd_instrument, serial_number)
                if instrument_key not in instrument_cache:
                    instrument_cache[instrument_key] = core_models.Instrument.objects.get_or_create(
                        type=ctd_instrument, name=serial_number)[0]

                instrument = instrument_cache[instrument_key]

                if (int(event_id), instrument.pk) not in existing_events:
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

        return parsed_events

    def process_bottles(self, parsed_events):
        # `parsed_events` is expected to be a dictionary where:
        # - The key is an event ID.
        # - The value is a list of files, where:
        #   - file[0] is the `btl_file`.
        #   - file[1] is the associated `ros_file`.
        bottle_count = len(parsed_events.keys())
        for index, event_file in enumerate(parsed_events.items()):
            logger_notifications.info(_("Parsing Bottle Data") + " : %d/%d", (index + 1), bottle_count)
            event_id = event_file[0]
            btl_file = event_file[1][0]
            ros_file = event_file[1][1]
            file_name = os.path.basename(btl_file)
            try:
                event = core_models.Event.objects.get(event_id=event_id, instrument__type=core_models.InstrumentType.ctd)

                with open(btl_file, 'r', encoding='cp1252') as btl:
                    btl_input = io.StringIO(btl.read())

                with open(ros_file, 'r', encoding='cp1252') as ros:
                    ros_input = io.StringIO(ros.read())

                parser = FixStationParser(event=event, btl_filename=os.path.basename(btl_file),
                                          btl_stream=btl_input, ros_stream=ros_input)
                parser.parse()
            except Exception as e:
                message = _("Error parsing body ") + f": {btl_file}: {e}"
                logger.error(message)
                logger.exception(e)
                err = core_models.FileError(mission=self.mission,
                                            file_name=file_name, message=message,
                                            type=core_models.ErrorType.validation, code=101)
                self.errors_to_create.append(err)


    def parse(self):
        self.errors_to_create = []
        # Get all file names upfront for batch deletion of errors
        file_names = [os.path.basename(file) for file in self.file_list]

        core_models.FileError.objects.filter(mission=self.mission, file_name__in=file_names, code=100).delete()
        core_models.FileError.objects.filter(mission=self.mission, file_name__in=file_names, code=101).delete()
        core_models.FileError.objects.filter(mission=self.mission, file_name__in=file_names, code=103).delete()

        parsed_events = self.create_events()
        self.process_bottles(parsed_events)

        # Bulk create errors
        if self.errors_to_create:
            core_models.FileError.objects.bulk_create(self.errors_to_create)


    def __init__(self, mission: core_models.Mission, files: list):
        self.file_list = files
        self.mission = mission