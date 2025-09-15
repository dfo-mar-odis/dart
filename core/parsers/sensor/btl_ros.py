# This is for parsing bottle files specifically for fix stations
import pytz
import io
import re
import os
import ctd

import numpy as np
import pandas as pd

from geopy.distance import geodesic
from typing import List, Any

from django.db.models import QuerySet
from django.utils.translation import gettext as _

from config import utils
from core import models as core_models
from bio_tables import models as bio_models
from settingsdb.models import FileConfiguration, GlobalSampleType, GlobalStation

import logging

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.fixstationparser')


class FixStationParser:
    field_mappings = None

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

    def get_or_create_file_config(self) -> QuerySet[FileConfiguration]:
        if self.field_mappings:
            return self.field_mappings

        file_type = 'btl'
        fields = [
            # default parser mappings
            ('event_id', "Station", _("Label describing what event number this bottle file should be mapped to.")),
            ('sounding', "Sounding", _("Label describing the recorded sounding")),
            ('latitude', "Latitude", _("Label describing the recorded Latitude")),
            ('longitude', "Longitude", _("Label describing the recorded Longitude")),
            ('comments', "Event_Comments", _("Label describing the event comments")),
        ]

        self.field_mappings = FileConfiguration.objects.filter(file_type=file_type)
        create_mapping = []
        for field in fields:
            if not self.field_mappings.filter(required_field=field[0]).exists():
                mapping = FileConfiguration(file_type=file_type)
                mapping.required_field = field[0]
                mapping.mapped_field = field[1]
                mapping.description = field[2]
                create_mapping.append(mapping)

        if len(create_mapping) > 0:
            FileConfiguration.objects.bulk_create(create_mapping)

        return self.field_mappings

    def get_mapping(self, label):
        row_mapping = self.get_or_create_file_config()

        return row_mapping.get(required_field=label).mapped_field

    # this will allow a developer to modify mappings for specific needs
    def set_field_mappings(self, mappings: QuerySet[FileConfiguration]):
        self.field_mappings = mappings

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

    def process_ros_sensors(self, sensors: [str]):
        """given a ROS file create sensors objects from the config portion of the file"""

        summary = ctd.rosette_summary(self.ros_stream)
        sensor_headings = re.findall(r"# name \d+ = (.*?)\n", getattr(summary, '_metadata')['config'])

        existing_sensors = GlobalSampleType.objects.filter(is_sensor=True).values_list('short_name',
                                                                                       flat=True).distinct()
        new_sensors: [GlobalSampleType] = []
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
        create_sensors: [GlobalSampleType] = []

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

    # Dart should assume we're working in the northwest hemisphere
    def _convert_to_decimal_deg(self, direction, hours, minutes=0):
        lat_lon = float(hours) + (float(minutes) / 60.0)
        if direction.upper() == 'S' or direction.upper() == 'W':
            lat_lon *= -1
        return lat_lon

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

    def process_actions(self, data: pd.DataFrame):
        header = data._metadata['header']

        # We're in the process of updating the header for fixstation BTL files.
        # station_label = self.get_mapping('station')
        sounding_label = self.get_mapping('sounding')
        lat_label = self.get_mapping('latitude')
        lon_label = self.get_mapping('longitude')

        station_name = "HL_0"
        station = GlobalStation.objects.filter(name__iexact=station_name)

        # We're in the process of updating the header for fixstation BTL files.
        # station = re.findall(rf"{station_label}:(.*?)\n", header")
        sounding = re.findall(rf"{sounding_label}:(.*?)\n", header)
        latitude = re.findall(rf"{lat_label}:(.*?)\n", header)
        longitude = re.findall(rf"{lon_label}:(.*?)\n", header)

        if not sounding:
            raise KeyError(_("Could not find sounding label to create actions: ") + sounding_label)

        if not latitude:
            raise KeyError(_("Could not find latitude label to create actions: ") + latitude)

        if not longitude:
            raise KeyError(_("Could not find longitude label to create actions: ") + longitude)

        try:
            sounding = sounding[0].strip()
            lat_array = latitude[0].strip().split(" ")
            lon_array = longitude[0].strip().split(" ")

        except Exception as e:
            message = f"Invalid decimal degree Lat/Lon provided ({latitude[0].strip()}, {longitude[0].strip()})"
            raise ValueError(message) from e

        if len(lat_array) < 3 and (lat_array[0].upper() != 'N' or lat_array[0].upper() != 'S'):
            raise ValueError(_("Badly formatted latitude, missing direction") + " : " + latitude[0])

        if len(lon_array) < 3 and (lon_array[0].upper() != 'W' or lon_array[0].upper() != 'E'):
            raise ValueError(_("Badly formatted longitude, missing direction") + " : " + longitude[0])

        try:
            lat = self._convert_to_decimal_deg(*lat_array)
            lon = self._convert_to_decimal_deg(*lon_array)
        except Exception as e:
            message = f"Invalid decimal degree Lat/Lon provided ({latitude[0].strip()}, {longitude[0].strip()})"
            raise ValueError(message) from e

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

        bottom_bottle = self.event.bottles.order_by('pressure').first()
        surface_bottle = self.event.bottles.order_by('pressure').last()

        self._create_update_action(core_models.ActionType.bottom, bottom_bottle, sounding, lat, lon)
        self._create_update_action(core_models.ActionType.recovered, surface_bottle, sounding, lat, lon)

        self.event.sample_id = min(bottom_bottle.bottle_id, surface_bottle.bottle_id)
        self.event.end_sample_id = max(bottom_bottle.bottle_id, surface_bottle.bottle_id)

        self.event.save()

    def parse(self):
        self.event.mission.file_errors.filter(file_name=self.btl_filename).delete()
        self.event.validation_errors.all().delete()

        data: pd.DataFrame = ctd.read.from_btl(self.btl_stream)

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


class FixStationBulkParser:

    file_list = None
    errors_to_create = []
    mission = None

    def create_events(self) -> dict:

        label_event = 'EVENT_NUMBER'  # this should be 'EVENT', but there's a problem with the btl files
        label_serial_number = 'INSTRUMENT_SERIAL_NUMBER'
        label_station = 'STATION_NAME'  # this currently holds the event number, but will be fixed

        # Process all files
        create_events = []
        parsed_events = {}
        errors_to_create = []

        # Cache instruments to avoid repeated queries
        instrument_cache = {}
        station = None

        # Fetch existing events as a list of (event_id, instrument.pk) tuples
        existing_events = list(self.mission.events.values_list('event_id', 'instrument__pk'))
        bottle_count = len(self.file_list)
        for index, file in enumerate(self.file_list):
            logger_notifications.info(_("Updating events") + " : %d/%d", (index + 1), bottle_count)
            file_name = os.path.basename(file)

            try:
                # Construct the expected .ros file path
                ros_file = os.path.splitext(file)[0] + ".ros"
                if not os.path.exists(ros_file):
                    raise FileNotFoundError(f"No matching .ros file found for: {file}")

                data = ctd.read.from_btl(file)
                header: str = data._metadata['header']
                header_lines: str = re.findall(r'^\* \*\*.*', header, re.MULTILINE)
                cleaned_lines: list[str] = [re.sub(r'^\* \*\*', '', line).split(":") for line in header_lines]
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

                serial_number = event_properties.get(label_serial_number, "CTD")
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
                self.errors_to_create.append(core_models.FileError(
                    mission=self.mission,
                    file_name=file_name,
                    message=message,
                    type=core_models.ErrorType.validation,
                    code=100
                ))

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
                event = core_models.Event.objects.get(event_id=event_id)

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

        parsed_events = self.create_events()
        self.process_bottles(parsed_events)

        # Bulk create errors
        if self.errors_to_create:
            core_models.FileError.objects.bulk_create(self.errors_to_create)


    def __init__(self, mission: core_models.Mission, files: list):
        self.file_list = files
        self.mission = mission