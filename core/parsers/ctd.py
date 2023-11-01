import ctd
import re
import os

import pandas
import pytz

from django.utils.translation import gettext as _

from core import models as core_models
from core import validation

import logging

logger = logging.getLogger("dart")


def get_event_number(data_frame: pandas.DataFrame) -> int:
    """retrieve the elog event number this bottle file is attached to"""
    pass


def get_event_number_nfl(data_frame: pandas.DataFrame):
    # when a bottle file is read using the ctd package the top part of the file is saved in the _metadata
    metadata = getattr(data_frame, "_metadata")

    # for the NFL Region uses the CTD number to link a BTL file to an Elog event.
    event_number = re.search('CTD NUMBER: (\d+)\n', metadata['header'])[1]
    if len(str(event_number)) > 3:
        event_number = int(str(event_number)[-3:])
    return int(event_number)


def get_event_number_bio(data_frame: pandas.DataFrame):
    # when a bottle file is read using the ctd package the top part of the file is saved in the _metadata
    metadata = getattr(data_frame, "_metadata")

    # for the Atlantic Region the last three digits of the bottle file name contains the elog event number,
    # but if there's a 'event_number' in the header use that instead.
    event_number = re.search('event_number: (\d+)\n', metadata['header'], re.IGNORECASE)[1]
    if event_number.isnumeric():
        event_number = int(str(event_number)[-3:])
        return int(event_number)

    event_number = re.search(".*(?:\D|^)(\d+)", metadata['name'])[1]
    if len(str(event_number)) > 3:
        event_number = int(str(event_number)[-3:])
        return int(event_number)

    raise ValueError("Could not acquire event number from bottle file")


def get_sensor_names(data_frame: pandas.DataFrame, exclude=None) -> list:
    """given a dataframe and a list of columns to exclude, return the remaining column that represent sensors"""

    if exclude is None:
        exclude = []
    return [instrument for instrument in data_frame.columns if instrument not in exclude]


def get_ros_file(btl_file: str) -> str:
    # TODO: Throw an error if the ros file doesn't exist

    """given a CTD BTL file return the matching ROS file"""
    file = btl_file[:-3] + "ROS"

    return file


def _get_units(sensor_description: str) -> [str, str]:
    """given a sensor description, find, remove and return the uom and remaining string"""
    uom_pattern = " \\[(.*?)\\]"
    uom = re.findall(uom_pattern, sensor_description)
    uom = uom[0] if uom else ""
    return uom, re.sub(uom_pattern, "", sensor_description)


def _get_priority(sensor_description: str) -> [int, str]:
    """given a sensor description, with units removed, find, remove and return the priority and remaining string"""
    priority_pattern = ", (\d)"
    priority = re.findall(priority_pattern, sensor_description)
    priority = priority[0] if priority else 1
    return int(priority), re.sub(priority_pattern, "", sensor_description)


def _get_sensor_type(sensor_description: str) -> [str, str]:
    """given a sensor description with priority and units removed return the sensor type and remaining string"""
    remainder = sensor_description.split(", ")
    # if the sensor type wasn't in the remaining comma seperated list then it is the first value of the description
    return remainder[0], ", ".join([remainder[i] for i in range(1, len(remainder)) if len(remainder) > 1])


def parse_sensor(sensor: str) -> [str, int, str, str]:
    """given a sensor description parse out the type, priority and units """
    units, sensor_a = _get_units(sensor)
    priority, sensor_b = _get_priority(sensor_a)
    sensor_type, remainder = _get_sensor_type(sensor_b)

    return sensor_type, priority, units, remainder


def process_ros_sensors(exclude_sensors: [str], ros_file: str):
    """given a ROS file create sensors objects from the config portion of the file"""

    summary = ctd.rosette_summary(ros_file)
    sensors = re.findall("# name \d+ = (.*?)\n", getattr(summary, '_metadata')['config'])

    excluding_sensors = [exclude.lower() for exclude in exclude_sensors]
    new_sensors: [core_models.SampleType] = []
    for sensor in sensors:
        # [column_name]: [sensor_details]
        sensor_mapping = re.split(": ", sensor)

        # if this sensor is in the list of excluded sensors, skip it.
        if sensor_mapping[0].lower() in excluding_sensors:
            continue

        # if the sensor already exists, skip it
        if core_models.SampleType.objects.filter(short_name__iexact=sensor_mapping[0]).exists():
            continue

        sensor_type_string, priority, units, other = parse_sensor(sensor_mapping[1])
        long_name = sensor_type_string
        if other:
            long_name += f", {other}"

        if units:
            long_name += f" [{units}]"

        sensor_type = core_models.SampleType(short_name=sensor_mapping[0], long_name=long_name, is_sensor=True)
        sensor_type.name = sensor_type_string
        sensor_type.priority = priority if priority else 1
        sensor_type.units = units if units else None
        sensor_type.comments = other

        new_sensors.append(sensor_type)

    if new_sensors:
        core_models.SampleType.objects.bulk_create(new_sensors)


def parse_sensor_name(sensor: str) -> [str, int, str]:
    """Given a sensor name, return the type of sensor, its priority and units where available"""
    # For common sensors the common format for the names is [sensor_type][priority][units]
    # Sbeox0ML/L -> Sbeox (Sea-bird oxygen), 0 (primary sensor), ML/L
    # many sensors follow this format, the ones that don't are likely located, in greater detail, in
    # the ROS file configuration
    details = re.match("(\D\D*)(\d{0,1})([A-Z]*.*)", sensor).groups()
    if not details:
        raise Exception(f"Sensor '{sensor}' does not follow the expected naming convention")

    sensor_name = sensor
    priority = int(details[1] if len(details[1]) >= 1 else 0) + 1  # priority 0 means primary sensor, 1 means secondary
    units = None
    if len(details) > 2:
        at_least_one_letter = re.search(r'[a-zA-Z]+', details[2])
        if at_least_one_letter:
            units = details[2]

    return [sensor_name, priority, units]


def process_common_sensors(sensors: list[str], exclude_sensors: [str]):
    """Given a list of sensor names, or 'column headings', create a list of mission sensors that don't already exist"""
    create_sensors: [core_models.SampleType] = []
    excluding_sensors = [sensor.lower() for sensor in exclude_sensors]

    for sensor in sensors:

        # if this sensor is in the list of excluded sensors, skip it.
        if sensor.lower() in excluding_sensors:
            continue

        # if the sensor exists, skip it
        if core_models.SampleType.objects.filter(short_name__iexact=sensor).exists():
            continue

        details = parse_sensor_name(sensor)
        long_name = details[2]  # basically all we have at the moment is the units of measure
        sensor_details = core_models.SampleType(short_name=details[0], long_name=long_name, is_sensor=True)
        sensor_details.priority = details[1]
        sensor_details.units = details[2]

        create_sensors.append(sensor_details)

    if create_sensors:
        core_models.SampleType.objects.bulk_create(create_sensors)


def process_sensors(btl_file: str, column_headers: list[str], exclude_sensors: list[str]):
    """Given a Data File and a list of column, 'SampleType' objects will be created if they do not already exist
    or aren't part of a set of excluded sensors"""
    ros_file = get_ros_file(btl_file=btl_file)
    process_ros_sensors(exclude_sensors=exclude_sensors, ros_file=ros_file)

    # The ROS file gives us all kinds of information about special sensors that are commonly added and removed from the
    # CTD, but it does not cover sensors that are normally on the CTD by default.
    existing_sensors = [sensor.short_name.lower() for sensor in core_models.SampleType.objects.all()]
    columns = [column_header for column_header in column_headers if column_header.lower() not in existing_sensors]
    process_common_sensors(exclude_sensors=exclude_sensors, sensors=columns)


def update_field(obj, field_name: str, value) -> bool:
    if not hasattr(obj, field_name):
        return False
    if getattr(obj, field_name) == value:
        return False

    setattr(obj, field_name, value)
    return True


def update_bottle(bottle: core_models.Bottle, check_fields: dict[str, object]) -> set:
    """Given a bottle and a dictionary of field name and 'new' value, check if a bottles attributes need to be updated
    return a set of fields that changed if an update was required."""
    fields = set()
    for field in check_fields:
        if update_field(bottle, field, check_fields[field]):
            fields.add(field)

    return fields


def process_bottles(event: core_models.Event, data_frame: pandas.DataFrame):
    skipped_rows = getattr(data_frame, "_metadata")["skiprows"]

    # we only want to use rows in the BTL file marked as 'avg' in the statistics column
    data_frame_avg = data_frame[data_frame['Statistic'] == 'avg']
    data_frame_avg.columns = map(str.lower, data_frame_avg.columns)

    dataframe_columns = ["bottle", "date", "prdm"]

    if "latitude" in data_frame_avg.columns:
        dataframe_columns.append("latitude")

    if "longitude" in data_frame_avg.columns:
        dataframe_columns.append("longitude")

    if "bottle_" in data_frame_avg.columns:
        # if present this is the Bottle ID to use instead of the event.sample_id + Bottle number
        dataframe_columns.append("bottle_")

    b_create = []
    b_update = {"data": [], "fields": set()}
    bottle_data = data_frame_avg[dataframe_columns]
    errors: [core_models.ValidationError] = []

    # clear out the bottle validation errors
    event.validation_errors.filter(type=core_models.ErrorType.bottle).delete()
    # end_sample_id-sample_id is includes so it's one less that the bottles in the file
    if (event.end_sample_id-event.sample_id) != bottle_data.count(axis=0)['bottle'] - 1:
        message = _("Mismatch bottle count for event")
        validation_err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.bottle)
        errors.append(validation_err)

    for row in bottle_data.iterrows():
        line = skipped_rows + row[0] + 1
        bottle_number = row[1]["bottle"]

        bottle_id = bottle_number + event.sample_id - 1

        # if the Bottle S/N column is present then use that values as the bottle ID
        if 'Bottle_' in row[1]:
            bottle_id = int(row[1]['bottle_'])

        date = row[1]["date"]
        pressure = row[1]["prdm"]
        latitude = row[1]["latitude"] if "latitude" in dataframe_columns else event.actions.first().latitude
        longitude = row[1]["longitude"] if "longitude" in dataframe_columns else event.actions.first().longitude

        # assume UTC time if a timezone isn't set
        if not hasattr(date, 'timezone'):
            date = pytz.timezone("UTC").localize(date)

        valid = validation.validate_bottle_sample_range(event=event, bottle_id=bottle_id)
        errors += valid

        if core_models.Bottle.objects.filter(event=event, bottle_number=bottle_number).exists():
            # If a bottle already exists for this event then we'll update it's fields rather than
            # creating a whole new bottle. Reason being there may be samples attached to bottles that are
            # being reloaded from a calibrated bottle file post mission.
            b = core_models.Bottle.objects.get(event=event, bottle_number=bottle_number)

            check_fields = {'bottle_id': bottle_id, 'date_time': date, 'pressure': pressure,
                            'latitude': latitude, 'longitude': longitude}
            updated_fields = update_bottle(b, check_fields)
            if len(updated_fields) > 0:
                b_update['data'].append(b)
                b_update['fields'] = b_update['fields'].union(updated_fields)
        elif len(valid) <= 0:
            # only create a new bottle if the bottle id is in a valid range.
            new_bottle = core_models.Bottle(event=event, pressure=pressure, bottle_number=bottle_number, date_time=date,
                                            bottle_id=bottle_id, latitude=latitude, longitude=longitude)
            b_create.append(new_bottle)

    core_models.Bottle.objects.bulk_create(b_create)
    if len(b_update['data']) > 0:
        core_models.Bottle.objects.bulk_update(objs=b_update['data'], fields=b_update['fields'])

    if len(errors) > 0:
        core_models.ValidationError.objects.bulk_create(errors)


# Todo: This function doesn't follow the standard pattern for creating/updating database elements
def process_data(event: core_models.Event, data_frame: pandas.DataFrame, column_headers: list[str]):
    # we only want to use rows in the BTL file marked as 'avg' in the statistics column
    file_name = data_frame._metadata['name'] + ".BTL"
    data_frame_avg = data_frame[data_frame['Statistic'] == 'avg']
    data_frame_avg._metadata = data_frame._metadata

    new_samples: [core_models.DiscreteSampleValue] = []
    update_samples: [core_models.DiscreteSampleValue] = []
    bottle_id_columns = ['Bottle']
    if 'Bottle_' in data_frame_avg.columns:
        bottle_id_columns.append('Bottle_')

    for column_name in column_headers:
        try:
            sensor_type = core_models.SampleType.objects.get(short_name__iexact=column_name)

            columns = bottle_id_columns
            columns.append(column_name)
            df = data_frame_avg[columns]
            create_sensors: {int: core_models.Sample} = {}
            for data in df.iterrows():
                bottle = event.bottles.filter(bottle_number=data[1]["Bottle"])
                if not bottle.exists():
                    message = _('Bottle') + f" {data[1]['Bottle']}"
                    if 'Bottle_' in bottle_id_columns:
                        message += " " + _('with bottle id') + f" {data[1]['Bottle_']}"
                    message += " " + _('for event') + f" {event.event_id}"
                    message += " " + _("does not exist. It may be outside the bottle range for the event")
                    logger.warning(message)
                    continue

                bottle = bottle[0]
                sensor = core_models.Sample.objects.filter(bottle=bottle, type=sensor_type, file=file_name)
                if sensor.exists():
                    sensor = sensor[0]
                elif bottle.bottle_id in create_sensors:
                    sensor = create_sensors[bottle.bottle_id]
                else:
                    sensor = core_models.Sample(bottle=bottle, type=sensor_type, file=file_name)
                    create_sensors[bottle.bottle_id] = sensor

                # bottle files don't contain replicates for discrete values, there should only be one sample value
                # per bottle per sensor type
                if sensor.pk and sensor.discrete_values.all().exists():
                    discrete_value = sensor.discrete_values.get(replicate=1)
                    discrete_value.value = data[1][column_name]
                    update_samples.append(discrete_value)
                else:
                    discrete_value = core_models.DiscreteSampleValue(sample=sensor, value=data[1][column_name])
                    new_samples.append(discrete_value)

            if create_sensors:
                core_models.Sample.objects.bulk_create(create_sensors.values())
        except Exception as ex:
            logger.exception(ex)

    core_models.DiscreteSampleValue.objects.bulk_create(new_samples)
    core_models.DiscreteSampleValue.objects.bulk_update(update_samples, fields=["value"])


# BIO and the NFL region track events within bottle files differently
def get_elog_event_nfl(mission: core_models.Mission, event_number: int) -> core_models.Event:
    events = mission.events.filter(instrument__type=core_models.InstrumentType.ctd)
    event = events[event_number-1]

    return event


def get_elog_event_bio(mission: core_models.Mission, event_number: int) -> core_models.Event:
    event = mission.events.get(event_id=event_number)

    return event


def read_btl(mission: core_models.Mission, btl_file: str):
    data_frame = ctd.from_btl(btl_file)

    file_name = data_frame._metadata['name']
    core_models.FileError.objects.filter(file_name=file_name).delete()
    if file_name not in btl_file:
        message = _("Name of bottle file does not match name in the bottle file. Check the .hdr file and reprocess.")
        message += f" {btl_file} =/= {file_name}"
        err = core_models.FileError(mission=mission, message=message, line=-1, type=core_models.ErrorType.validation,
                                    file_name=file_name)
        err.save()
        return

    event_number = get_event_number_bio(data_frame=data_frame)
    event = get_elog_event_bio(mission=mission, event_number=event_number)

    # These are columns we either have no use for or we will specifically call and use later
    # The Bottle column is the rosette number of the bottle
    # the Bottle_ column, if present, is the bottle.bottle_id for a bottle.
    pop = ['Bottle', 'Bottle_', 'Date', 'Scan', 'TimeS', 'Statistic', "Longitude", "Latitude"]
    col_headers = get_sensor_names(data_frame=data_frame, exclude=pop)

    process_bottles(event=event, data_frame=data_frame)

    # this will exclude common columns in either a ROS or BTL file
    exclude_sensors = ['scan', 'timeS', 'latitude', 'longitude', 'nbf', 'flag', 'prdm']
    columns = [col_header for col_header in col_headers if col_header.lower() not in exclude_sensors]

    # If you think about it a 'sensor' and a 'sample' are really the same thing.
    # They have a column (sample) name, a BioChem DataType and a value.
    # Create any sensor from the bottle file that doesn't already exist.
    process_sensors(btl_file=btl_file, column_headers=columns, exclude_sensors=exclude_sensors)
    process_data(event=event, data_frame=data_frame, column_headers=columns)

