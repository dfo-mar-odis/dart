import datetime
import io
import pandas as pd
import numpy as np

from django.utils.translation import gettext as _
from django.db.models import QuerySet

from core import models as core_models

from settingsdb import models as settings_models

import logging

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.filterlogparser')


def get_or_create_file_config() -> QuerySet[settings_models.FileConfiguration]:
    file_type = 'filterlog'
    fields = [
        ("bottles", "Bottle ID", _("Label identifying the Bottle ID")),
        ("pressure", "Depth", _("Label identifying the column with the nominal pressure")),
        ("oxygen", "Oxygen", _("Label identifying the column specifying if there will be an oxygen sample")),
        ("nutrient", "Nutrients", _("Label identifying the column specifying if there will be nutrient samples")),
        ("salt", "Salinity", _("Label identifying the column specifying if there will be salt samples")),
        ("chl", "Chlorophyll", _("Label identifying the column specifying if there will be chl samples")),
    ]

    existing_mappings = settings_models.FileConfiguration.objects.filter(file_type=file_type)
    create_mapping = []
    for field in fields:
        if not existing_mappings.filter(required_field=field[0]).exists():
            mapping = settings_models.FileConfiguration(file_type=file_type)
            mapping.required_field = field[0]
            mapping.mapped_field = field[1]
            mapping.description = field[2]
            create_mapping.append(mapping)

    if len(create_mapping) > 0:
        settings_models.FileConfiguration.objects.bulk_create(create_mapping)

    return existing_mappings


def get_mapping(label):
    row_mapping = get_or_create_file_config()

    return row_mapping.get(required_field=label).mapped_field


def add_sample_type(bottle: core_models.Bottle, short_name: str, samples: list, values: list, value=0):
    pressure = settings_models.GlobalSampleType.objects.get(short_name=short_name)
    mission_type: core_models.MissionSampleType = pressure.get_mission_sample_type(bottle.event.trip.mission)
    if not mission_type.samples.filter(bottle=bottle).exists():
        sample = core_models.Sample(bottle=bottle, type=mission_type)
        samples.append(sample)
    else:
        sample = mission_type.samples.get(bottle=bottle)
        sample.discrete_values.all().delete()

    value = core_models.DiscreteSampleValue(sample=sample, value=value)
    values.append(value)


def parse(event: core_models.Event, filename: str, stream: io.BytesIO):

    database = event._state.db

    station_tab = pd.read_excel(io=stream, sheet_name="HL_02", header=0, nrows=20)
    station_tab.fillna('', inplace=True)

    bottles = []
    samples = []
    values = []
    for row, data in station_tab.iterrows():
        bottle_id = data[get_mapping('bottles')]
        pressure_value = data[get_mapping('pressure')]
        oxygen = data[get_mapping('oxygen')]
        nutrients = data[get_mapping('nutrient')]
        salts = data[get_mapping('salt')]
        chl = data[get_mapping('chl')]

        closed = datetime.datetime.now()
        if not event.bottles.filter(bottle_id=bottle_id).exists():
            bottle = core_models.Bottle(event=event, bottle_id=bottle_id, pressure=pressure_value, closed=closed)
            bottles.append(bottle)
        else:
            bottle = event.bottles.get(bottle_id=bottle_id)

        add_sample_type(bottle=bottle, short_name='prDM', samples=samples, values=values, value=pressure_value)

        if oxygen:
            add_sample_type(bottle=bottle, short_name='oxy', samples=samples, values=values)

        if salts:
            add_sample_type(bottle=bottle, short_name='salts', samples=samples, values=values)

        if chl:
            add_sample_type(bottle=bottle, short_name='chl', samples=samples, values=values)
            add_sample_type(bottle=bottle, short_name='phae', samples=samples, values=values)

        if nutrients:
            add_sample_type(bottle=bottle, short_name='nitrate', samples=samples, values=values)
            add_sample_type(bottle=bottle, short_name='nitrite', samples=samples, values=values)
            add_sample_type(bottle=bottle, short_name='phosphate', samples=samples, values=values)
            add_sample_type(bottle=bottle, short_name='silicate', samples=samples, values=values)
            add_sample_type(bottle=bottle, short_name='ammonium', samples=samples, values=values)

    if len(bottles) > 0:
        core_models.Bottle.objects.using(database).bulk_create(bottles)

    if len(samples) > 0:
        core_models.Sample.objects.using(database).bulk_create(samples)

    if len(values) > 0:
        core_models.DiscreteSampleValue.objects.using(database).bulk_create(values)