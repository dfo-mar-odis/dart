from datetime import datetime

from settingsdb import utils
from settingsdb import models as settings_models

from bio_tables import models as bio_models
from core import models as core_models

def get_locations():
    return [l for l in settings_models.LocalSetting.objects.all()]

def connect_database(mission_name: str, location=None):
    utils.connect_database(mission_name, location)

def list_sensors():
    mission = core_models.Mission.objects.get(pk=1)
    datatype_ids = [d for d in mission.mission_sample_types.filter(datatype__isnull=False).values_list('datatype', flat=True)]
    datatypes = bio_models.BCDataType.objects.filter(pk__in=datatype_ids)
    load_or_loading = mission.mission_sample_types.filter(uploads__status__in=[1, 2])
    return [(s.name, s.datatype, s, datetime.strftime(s.uploads.first().upload_date, '%y-%m-%d %H:%M:%S'), datatypes.get(pk=s.datatype)) for s in load_or_loading.filter(is_sensor=True)]
