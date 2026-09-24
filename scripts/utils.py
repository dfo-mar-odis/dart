from core.models import Mission
from bio_tables import models as bio_models

from settingsdb import utils as settings_utils

def change_datatypes(mission_name: str, current_datatype: int, new_datatype: int, new_label: str = None) -> None:
    settings_utils.connect_database(mission_name)
    try:
        mission = Mission.objects.get(pk=1)
        c_datatype = mission.mission_sample_types.get(datatype=current_datatype)

        if new_datatype:
            datatype = bio_models.BCDataType.objects.get(data_type_seq=new_datatype)
            c_datatype.datatype = datatype.data_type_seq
            c_datatype.name = datatype.method

        if new_label:
            c_datatype.name = new_label

        c_datatype.save()
    finally:
        settings_utils.close_connection()
