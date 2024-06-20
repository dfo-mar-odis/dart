import ctd
import re

import numpy as np
import pandas
import pytz

from datetime import datetime

from django.utils.translation import gettext as _

import core.models
from core import models as core_models
from core import validation

from settingsdb import models as settings_models
import logging

from dart.utils import updated_value

logger = logging.getLogger("dart")
logger_notifications = logging.getLogger('dart.user.ctd')


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
    event_number = re.search('event_number: *(\d+)\n', metadata['header'], re.IGNORECASE)
    if event_number and (event_number := event_number[1]).isnumeric():
        event_number = int(str(event_number)[-3:])
        return int(event_number)

    event_number = re.search(".*(?:\D|^)(\d+)", metadata['name'])[1]
    if len(str(event_number)) > 3:
        event_number = int(str(event_number)[-3:])
        return int(event_number)

    raise ValueError("Could not acquire event number from bottle file")


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


def process_ros_sensors(sensors: [str], ros_file: str):
    """given a ROS file create sensors objects from the config portion of the file"""

    summary = ctd.rosette_summary(ros_file)
    sensor_headings = re.findall("# name \d+ = (.*?)\n", getattr(summary, '_metadata')['config'])

    existing_sensors = settings_models.GlobalSampleType.objects.filter(
        is_sensor=True).values_list('short_name', flat=True).distinct()
    new_sensors: [settings_models.GlobalSampleType] = []
    for sensor in sensor_headings:
        # [column_name]: [sensor_details]
        sensor_mapping = re.split(": ", sensor)

        # if this sensor is not in the list of sensors we're looking for, skip it.
        if sensor_mapping[0].lower() not in sensors:
            continue

        # if the sensor already exists, skip it
        if settings_models.GlobalSampleType.objects.filter(short_name__iexact=sensor_mapping[0]).exists():
            continue

        sensor_type_string, priority, units, other = parse_sensor(sensor_mapping[1])
        long_name = sensor_type_string
        if other:
            long_name += f", {other}"

        if units:
            long_name += f" [{units}]"

        if sensor_mapping[0] in existing_sensors:
            continue

        sensor_type = settings_models.GlobalSampleType(short_name=sensor_mapping[0], long_name=long_name,
                                                       is_sensor=True)
        sensor_type.name = sensor_type_string
        sensor_type.priority = priority if priority else 1
        sensor_type.units = units if units else None
        sensor_type.comments = other

        new_sensors.append(sensor_type)

    if new_sensors:
        settings_models.GlobalSampleType.objects.bulk_create(new_sensors)


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


def process_common_sensors(sensors: list[str]):
    """Given a list of sensor names, or 'column headings', create a list of mission sensors that don't already exist"""
    create_sensors: [settings_models.GlobalSampleType] = []

    for sensor in sensors:

        # if the sensor exists, skip it
        if settings_models.GlobalSampleType.objects.filter(short_name__iexact=sensor).exists():
            continue

        details = parse_sensor_name(sensor)
        long_name = details[2]  # basically all we have at the moment is the units of measure
        sensor_details = settings_models.GlobalSampleType(short_name=details[0], long_name=long_name, is_sensor=True)
        sensor_details.priority = details[1]
        sensor_details.units = details[2]

        create_sensors.append(sensor_details)

    if create_sensors:
        settings_models.GlobalSampleType.objects.bulk_create(create_sensors)


def process_sensors(btl_file: str, column_headers: list[str]):
    """Given a Data File and a list of column, 'SampleType' objects will be created if they do not already exist
    or aren't part of a set of excluded sensors"""
    ros_file = get_ros_file(btl_file=btl_file)
    process_ros_sensors(sensors=column_headers, ros_file=ros_file)

    # The ROS file gives us all kinds of information about special sensors that are commonly added and removed from the
    # CTD, but it does not cover sensors that are normally on the CTD by default. i.e Sal00, Potemp090C, Sigma-é00
    existing_sensors = [sensor.short_name.lower() for sensor in settings_models.GlobalSampleType.objects.all()]
    columns = [column_header for column_header in column_headers if column_header.lower() not in existing_sensors]
    process_common_sensors(sensors=columns)


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
    database = event._state.db

    skipped_rows = getattr(data_frame, "_metadata")["skiprows"]

    # we only want to use rows in the BTL file marked as 'avg' in the statistics column
    data_frame_avg = data_frame[data_frame['Statistic'] == 'avg']
    data_frame_avg.columns = map(str.lower, data_frame_avg.columns)

    dataframe_dict = {
        'bottle_number': "bottle",
        'date': "date",
    }

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

    b_create = []
    b_update = {"data": [], "fields": set()}
    bottle_data = data_frame_avg[dataframe_dict.values()]
    errors: [core_models.ValidationError] = []

    # clear out the bottle validation errors
    event.validation_errors.filter(type=core_models.ErrorType.bottle).delete()
    # end_sample_id-sample_id is inclusive so it's one less that the bottles in the file
    if (event.end_sample_id-event.sample_id) != bottle_data.count(axis=0)[dataframe_dict['bottle_number']] - 1:
        message = _("Mismatch bottle count for event")
        validation_err = core_models.ValidationError(event=event, message=message, type=core_models.ErrorType.bottle)
        errors.append(validation_err)

    for row in bottle_data.iterrows():
        line = skipped_rows + row[0] + 1
        bottle_number = row[1][dataframe_dict['bottle_number']]

        bottle_id = bottle_number + event.sample_id - 1

        # if the Bottle S/N column is present then use that values as the bottle ID
        if 'bottle_id' in dataframe_dict.keys() and \
                dataframe_dict['bottle_id'] in row[1] and not np.isnan(row[1][dataframe_dict['bottle_id']]):
            bottle_id = int(row[1][dataframe_dict['bottle_id']])

        date = row[1][dataframe_dict['date']]
        pressure = row[1][dataframe_dict['pressure']]

        latitude = event.actions.first().latitude
        if "latitude" in dataframe_dict.keys():
            latitude = row[1][dataframe_dict["latitude"]]

        longitude = event.actions.first().longitude
        if "longitude" in dataframe_dict.keys():
            longitude = row[1][dataframe_dict["longitude"]]

        # assume UTC time if a timezone isn't set
        if not hasattr(date, 'timezone'):
            date = pytz.timezone("UTC").localize(date)

        valid = validation.validate_bottle_sample_range(event=event, bottle_id=bottle_id)
        errors += valid

        if core_models.Bottle.objects.using(database).filter(event=event, bottle_number=bottle_number).exists():
            # If a bottle already exists for this event then we'll update its fields rather than
            # creating a whole new bottle. Reason being there may be samples attached to bottles that are
            # being reloaded from a calibrated bottle file post mission.
            b = core_models.Bottle.objects.using(database).get(event=event, bottle_number=bottle_number)

            check_fields = {'bottle_id': bottle_id, 'date_time': date, 'pressure': pressure,
                            'latitude': latitude, 'longitude': longitude}
            updated_fields = update_bottle(b, check_fields)
            if len(updated_fields) > 0:
                b_update['data'].append(b)
                b_update['fields'] = b_update['fields'].union(updated_fields)
        elif len(valid) <= 0:
            # only create a new bottle if the bottle id is in a valid range.
            new_bottle = core_models.Bottle(event=event, pressure=pressure, bottle_number=bottle_number, closed=date,
                                            bottle_id=bottle_id, latitude=latitude, longitude=longitude)
            b_create.append(new_bottle)

    core_models.Bottle.objects.using(database).bulk_create(b_create)
    if len(b_update['data']) > 0:
        core_models.Bottle.objects.using(database).bulk_update(objs=b_update['data'], fields=b_update['fields'])

    if len(errors) > 0:
        core_models.ValidationError.objects.using(database).bulk_create(errors)


def process_data(event: core_models.Event, data_frame: pandas.DataFrame, column_headers: list[str]):
    mission = event.mission
    database = mission._state.db

    # we only want to use rows in the BTL file marked as 'avg' in the statistics column
    file_name = data_frame._metadata['name'] + ".BTL"
    skipped_rows = getattr(data_frame, "_metadata")["skiprows"]

    data_frame_avg = data_frame[data_frame['Statistic'] == 'avg']
    data_frame_avg._metadata = data_frame._metadata

    # convert all column names to lowercase
    data_frame_avg.columns = map(str.lower, data_frame_avg.columns)

    new_samples: [core_models.Sample] = []
    update_samples: [core_models.Sample] = []
    new_discrete_samples: [core_models.DiscreteSampleValue] = []
    update_discrete_samples: [core_models.DiscreteSampleValue] = []
    # validate and remove bottles that don't exist
    if data_frame_avg.shape[0] > (event.total_samples + 1):
        message = _('Event contained more than the expected number of bottles. Additional bottles will be dropped. ')
        message += _("Event") + f" #{event.event_id} "
        message += _("Expected") + f"[{(event.total_samples+1)}] "
        message += _("Found") + f"[{data_frame_avg.shape[0]}]"
        logger.warning(message)

        core_models.FileError(mission=mission, file_name=file_name, line=skipped_rows, message=message,
                              type=core_models.ErrorType.validation).save()

        drop_rows = data_frame_avg.shape[0] - (event.total_samples + 1)
        data_frame_avg = data_frame_avg[:-drop_rows]

    bottles = core_models.Bottle.objects.using(database).filter(event=event)

    # make global sample types local to this mission to be attached to samples when they're created
    logger.info("Creating local sample types")
    new_sample_types = []
    for name in column_headers:
        if not mission.mission_sample_types.filter(name=name).exists():
            global_sampletype = settings_models.GlobalSampleType.objects.get(short_name__iexact=name)
            new_sampletype = core_models.MissionSampleType(mission=mission, name=name, is_sensor=True,
                                                           long_name=global_sampletype.long_name,
                                                           datatype=global_sampletype.datatype,
                                                           priority=global_sampletype.priority)
            new_sampletype.save()

    sample_types = {
        sample_type.name: sample_type for sample_type in mission.mission_sample_types.all()
    }

    for row in data_frame_avg.iterrows():
        bottle_number = row[1]["bottle"]
        bottle_id = bottle_number + event.sample_id - 1

        # if the Bottle S/N column is present then use that values as the bottle ID
        if 'bottle_' in row[1]:
            bottle_id = int(row[1]['bottle_'])

        if not bottles.filter(bottle_id=bottle_id).exists():
            message = _("Bottle does not exist for event")
            message += _("Event") + f" #{event.event_id} " + _("Bottle ID") + f" #{bottle_id}"

            logger.warning(message)
            continue

        bottle = bottles.get(bottle_id=bottle_id)
        for column in column_headers:
            if (sample := core_models.Sample.objects.using(database).filter(bottle=bottle,
                                                                            type=sample_types[column])).exists():
                sample = sample.first()
                if updated_value(sample, 'file', file_name):
                    update_samples.append(sample)

                discrete_value = sample.discrete_values.all().first()
                new_value = row[1][column.lower()]
                if updated_value(discrete_value, 'value', new_value):
                    update_discrete_samples.append(discrete_value)
            else:
                sample = core_models.Sample(bottle=bottle, type=sample_types[column], file=file_name)
                new_samples.append(sample)
                discrete_value = core_models.DiscreteSampleValue(sample=sample, value=row[1][column.lower()])
                new_discrete_samples.append(discrete_value)

    if len(new_samples) > 0:
        logger.info("Creating CTD samples for file" + f" : {file_name}")
        core_models.Sample.objects.using(database).bulk_create(new_samples)

    if len(update_samples) > 0:
        logger.info("Creating CTD samples for file" + f" : {file_name}")
        core_models.Sample.objects.using(database).bulk_update(update_samples, ['file'])

    if len(new_discrete_samples) > 0:
        logger.info("Adding values to samples" + f" : {file_name}")
        core_models.DiscreteSampleValue.objects.using(database).bulk_create(new_discrete_samples)

    if len(update_discrete_samples) > 0:
        logger.info("Updating sample values" + f" : {file_name}")
        core_models.DiscreteSampleValue.objects.using(database).bulk_update(update_discrete_samples, ['value'])

    for ms_type in mission.mission_sample_types.all():
        if bcu := ms_type.uploads.first():
            bcu.status = core_models.BioChemUploadStatus.upload
            bcu.modified_date = datetime.now()
            bcu.save()


# BIO and the NFL region track events within bottle files differently
def get_elog_event_nfl(mission: core_models.Mission, event_number: int) -> core_models.Event:

    database = mission._state.db
    events = mission.events.filter(instrument__type=core_models.InstrumentType.ctd)
    event = events[event_number-1]

    return event


def get_elog_event_bio(mission: core_models.Mission, event_number: int) -> core_models.Event:
    try:
        event = mission.events.get(event_id=event_number, instrument__type=core_models.InstrumentType.ctd)
    except core_models.Event.DoesNotExist as ex:
        raise core_models.Event.DoesNotExist(event_number) from ex
    return event


def read_btl(mission: core_models.Mission, btl_file: str):
    database = mission._state.db
    data_frame = ctd.from_btl(btl_file)

    file_name = data_frame._metadata['name']
    if (errors := core_models.FileError.objects.using(database).filter(file_name=file_name)).exists():
        errors.delete()

    if (errors := core_models.FileError.objects.using(database).filter(file_name=btl_file)).exists():
        errors.delete()

    if file_name not in btl_file:
        message = _("Name of bottle file does not match name in the bottle file. Check the .hdr file and reprocess.")
        message += f" {btl_file} =/= {file_name}"
        err = core_models.FileError(mission=mission, message=message, line=-1, type=core_models.ErrorType.bottle,
                                    file_name=btl_file)
        err.save(using=database)
        raise ValueError(message)

    event_number = get_event_number_bio(data_frame=data_frame)
    try:
        event = get_elog_event_bio(mission=mission, event_number=event_number)

    except core_models.Event.DoesNotExist as ex:
        message = _("Could not find matching event for event number") + f" : {event_number}"
        err = core_models.FileError(mission=mission, message=message, line=-1, type=core_models.ErrorType.bottle,
                                    file_name=btl_file)
        err.save(using=database)
        raise ex

    if event.instrument.type != core_models.InstrumentType.ctd:
        message = "Event_Number" + f" : {event_number} - " + _("not a CTD event, check the event number in the BTL file is correct.")
        err = core_models.FileError(mission=mission, message=message, line=-1, type=core_models.ErrorType.bottle,
                                    file_name=btl_file)
        err.save(using=database)
        raise ValueError("Bad Event number")

    # These are columns we either have no use for or we will specifically call and use later
    # The Bottle column is the rosette number of the bottle
    # The Bottle_ column, if present, is the bottle.bottle_id for a bottle.
    exclude = ['bottle', 'bottle_', 'date', 'scan', 'times', 'statistic',
               'longitude', 'latitude', 'nbf', 'flag']
    col_headers = [instrument.lower() for instrument in data_frame.columns if instrument.lower() not in exclude]

    process_bottles(event=event, data_frame=data_frame)

    # If you think about it a 'sensor' and a 'sample' are really the same thing.
    # They have a column (sample) name, a BioChem DataType and a value.
    # Create any sensor from the bottle file that doesn't already exist.
    process_sensors(btl_file=btl_file, column_headers=col_headers)
    process_data(event=event, data_frame=data_frame, column_headers=col_headers)

    # make all 'standard' level data types 'mission' level
    # sample_types = [core.models.GlobalSampleType.objects.get(short_name__iexact=column) for column in col_headers]
    # create_mission_sample_types = []
    # for sample_type in sample_types:
    #     if not mission.mission_sample_types.filter(sample_type=sample_type).exists():
    #         mission_sample_type = core_models.MissionSampleType(mission=mission, sample_type=sample_type,
    #                                                             datatype=sample_type.datatype)
    #         create_mission_sample_types.append(mission_sample_type)
    #
    # if len(create_mission_sample_types) > 0:
    #     core_models.MissionSampleType.objects.bulk_create(create_mission_sample_types)
