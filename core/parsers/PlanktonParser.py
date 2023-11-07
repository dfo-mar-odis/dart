import datetime
import logging
import numpy as np

from pandas import DataFrame

from django.utils.translation import gettext as _

from core import models as core_models
from bio_tables import models as bio_models
from dart2.utils import updated_value

logger = logging.getLogger('dart')
user_logger = logging.getLogger('dart.user')

phyto_column_dict = {
    'ID': "ID",
    'APHIA_ID': "APHIA_ID",
    'TAXONOMIC_NAME': "TAXONOMIC_NAME",
    'CELLS_LITRE': "CELLS_LITRE",
    'LIFE_HISTORY_SEQ': "LIFE_HISTORY_SEQ",
    'CERTAINTY': "CERTAINTY",
    'COMMENTS': "COMMENTS"
}

zoo_column_dict = {
    'MISSION': 'MISSION',
    'DATE': 'DATE',
    'STN': 'STN',
    'TOW#': 'TOW#',
    'GEAR': 'GEAR',
    'EVENT': 'EVENT',
    'SAMPLEID': 'SAMPLEID',
    'DEPTH': 'DEPTH',
    'ANALYSIS': 'ANALYSIS',
    'SPLIT': 'SPLIT',
    'ALIQUOT': 'ALIQUOT',
    'SPLIT_FRACTION': 'SPLIT_FRACTION',
    'TAXA': 'TAXA',
    'NCODE': 'NCODE',
    'STAGE': 'STAGE',
    'SEX': 'SEX',
    'DATA_VALUE': 'DATA_VALUE',
    'PROC_CODE': 'PROC_CODE',
    'WHAT_WAS_IT': 'WHAT_WAS_IT'
}

def parse_phytoplankton(mission_id: int, filename: str, dataframe: DataFrame, row_mapping=None):
    if row_mapping is None:
        row_mapping = phyto_column_dict

    total_rows = dataframe.shape[0]

    # convert all columns to upper case
    dataframe.columns = map(str.upper, dataframe.columns)

    # for phytoplankton bottles are associated with a CTD bottle
    mission = core_models.Mission.objects.get(pk=mission_id)
    events = core_models.Event.objects.filter(mission_id=mission_id,
                                              instrument__type=core_models.InstrumentType.ctd)
    events = events.exclude(actions__type=core_models.ActionType.aborted)
    bottles = core_models.Bottle.objects.filter(event__in=events)

    core_models.FileError.objects.filter(mission=mission, file_name=filename).delete()

    create_plankton = []
    update_plankton = {'objects': [], 'fields': set()}
    errors = []
    for line, row in dataframe.iterrows():

        line_number = line + dataframe.index.start + 1
        user_logger.info(_("Creating plankton sample") + "%d/%d", line_number, total_rows)

        bottle_id = row['ID']

        logger.debug(bottle_id)

        if not bottles.filter(bottle_id=bottle_id).exists():
            err = core_models.FileError(mission=mission, file_name=filename, line=line_number,
                                        type=core_models.ErrorType.missing_id,
                                        message=_("Bottle does not exist for sample") + f" : {bottle_id}")
            errors.append(err)
            logger.error(err.message)
            continue

        bottle = bottles.get(bottle_id=bottle_id)

        aphiaid = row[row_mapping['APHIA_ID']]
        name = row[row_mapping['TAXONOMIC_NAME']]
        count = row[row_mapping['CELLS_LITRE']]
        certainty = row[row_mapping['CERTAINTY']]
        comment = row[row_mapping['COMMENTS']]
        comment = comment if str(comment) != 'nan' else ""

        base_history = 90000000
        life_history = row[row_mapping['LIFE_HISTORY_SEQ']]
        if life_history < base_history:
            life_history = life_history + base_history

        stage = life_history if not np.isnan(life_history) else None

        if (taxa := bio_models.BCNatnlTaxonCode.objects.filter(aphiaid=aphiaid,
                                                               taxonomic_name__iexact=name)).exists():
            taxa = taxa[0].national_taxonomic_seq
            logger.debug(taxa)
        else:
            err = core_models.FileError(mission=mission, file_name=filename, line=line_number,
                                        type=core_models.ErrorType.missing_id,
                                        message=_("Could not get taxonomic name for sample") + f" : {bottle_id}"
                                        )
            errors.append(err)
            logger.error(err.message)
            continue

        if not core_models.PlanktonSample.objects.filter(bottle=bottle, taxa__national_taxonomic_seq=taxa).exists():
            plankton = core_models.PlanktonSample(file=filename, bottle=bottle)

            plankton.count = count
            plankton.taxa_id = taxa
            plankton.comments = comment + (f' ({str(certainty)})' if certainty and not np.isnan(certainty) else '')

            if stage:
                plankton.stage_id = stage

            create_plankton.append(plankton)
        else:
            updated_fields = set('')

            plankton = core_models.PlanktonSample.objects.get(bottle=bottle, taxa=taxa)
            updated_fields.add(updated_value(plankton, 'count', count))
            updated_fields.add(updated_value(plankton, 'taxa_id', taxa))
            updated_fields.add(updated_value(plankton, 'stage_id', stage if stage else 90000000))

            comment = comment + (f' ({str(certainty)})' if certainty and not np.isnan(certainty) else '')
            updated_fields.add(updated_value(plankton, 'comments', comment if comment else None))

            updated_fields.remove('')
            if len(updated_fields) > 0:
                update_plankton['objects'].append(plankton)
                update_plankton['fields'].update(updated_fields)

    core_models.FileError.objects.bulk_create(errors)

    if len(create_plankton) > 0:
        logger.info(f'Creating {len(create_plankton)} plankton samples')
        core_models.PlanktonSample.objects.bulk_create(create_plankton)

    if len(update_plankton['objects']) > 0:
        logger.info(f'Updating {len(update_plankton["objects"])} plankton samples')
        fields = [field for field in update_plankton["fields"]]
        core_models.PlanktonSample.objects.bulk_update(update_plankton["objects"], fields)


# values taken from AZMP template
def get_gear_type(mesh_size: int):
    if mesh_size == 202:
        return bio_models.BCGear.objects.get(pk=90000102)
    elif mesh_size == 76:
        return bio_models.BCGear.objects.get(pk=90000105)

    return None


# values taken from AZMP template
def get_min_sieve(proc_code: int, mesh_size: int):
    if proc_code in [21]:
        return 10
    elif proc_code in [20, 22, 23, 50, 99]:
        return mesh_size/1000

    return None


# values taken from AZMP template
def get_max_sieve(proc_code: int):
    if proc_code in [20, 22, 50, 99]:
        return 10
    elif proc_code in [21, 23]:
        return None

    return None


# values taken from AZMP template
def get_split_fraction(proc_code: int, split: float):
    if proc_code in [20]:
        return round(split, 4)
    elif proc_code in [21, 22, 23]:
        return 1
    elif proc_code in [50]:
        return 0.5
    elif proc_code in [99]:
        return split

    return 9999


def parse_zooplankton(mission_id: int, filename: str, dataframe: DataFrame, row_mapping=None):
    if row_mapping is None:
        row_mapping = zoo_column_dict

    total_rows = dataframe.shape[0]

    # convert all columns to upper case
    dataframe.columns = map(str.upper, dataframe.columns)

    # for zooplankton bottles are associated with a RingNet bottles, which won't exist and will have to be created
    mission = core_models.Mission.objects.get(pk=mission_id)
    events = core_models.Event.objects.filter(mission_id=mission_id,
                                              instrument__type=core_models.InstrumentType.net)

    # don't care about aborted events
    events = events.exclude(actions__type=core_models.ActionType.aborted)
    ringnet_bottles = core_models.Bottle.objects.filter(event__in=events)

    core_models.FileError.objects.filter(mission=mission, file_name=filename).delete()

    create_plankton = {}
    create_bottles = []
    update_plankton = {'objects': [], 'fields': set()}
    errors = []
    for line, row in dataframe.iterrows():

        line_number = line + dataframe.index.start + 1
        user_logger.info(_("Creating plankton sample") + "%d/%d", line_number, total_rows)

        bottle_id = row[row_mapping['SAMPLEID']]
        taxonomic_name = row[row_mapping['TAXA']]
        ncode = row[row_mapping['NCODE']]
        taxa_id = 90000000000000 + int(ncode)

        stage_id = row[row_mapping['STAGE']]
        stage = 90000000 + stage_id if not np.isnan(stage_id) else None

        sex_id = row[row_mapping['SEX']]
        sex = 90000000 + sex_id if not np.isnan(sex_id) else None

        mesh_size = row[row_mapping['GEAR']]
        proc_code = row[row_mapping['PROC_CODE']]
        split = row[row_mapping['SPLIT_FRACTION']]
        value = row[row_mapping['DATA_VALUE']]
        what_was_it = row[row_mapping['WHAT_WAS_IT']]

        gear_type = get_gear_type(mesh_size)
        min_sieve = get_min_sieve(proc_code=proc_code, mesh_size=mesh_size)
        max_sieve = get_max_sieve(proc_code=proc_code)
        split_fraction = get_split_fraction(proc_code=proc_code, split=split)

        taxa = bio_models.BCNatnlTaxonCode.objects.get(pk=taxa_id)

        # if the ringnet bottle doesn't exist it needs to be created
        bottle = None
        if not ringnet_bottles.filter(bottle_id=bottle_id).exists():
            date = row[row_mapping['DATE']]
            event = events.get(event_id=row[row_mapping['EVENT']])
            pressure = row[row_mapping['DEPTH']]

            bottle = core_models.Bottle(bottle_id=bottle_id, event=event, pressure=pressure, date_time=date)
            create_bottles.append(bottle)

        plankton_key = f'{bottle_id}_{ncode}_{stage_id}_{sex_id}'

        plankton = core_models.PlanktonSample.objects.filter(taxa=taxa, bottle=bottle, stage_id=stage, sex_id=sex)
        if not plankton.exists():
            if plankton_key not in create_plankton.keys():
                plankton = core_models.PlanktonSample(
                    taxa=taxa, bottle=bottle, gear_type=gear_type, min_sieve=min_sieve, max_sieve=max_sieve,
                    split_fraction=split_fraction
                )

                if stage:
                    plankton.stage_id = stage

                if sex:
                    plankton.sex_id = sex

                create_plankton[plankton_key] = plankton

            plankton = create_plankton[plankton_key]
            match what_was_it:
                case 1:
                    plankton.count = value
                case 2:
                    plankton.raw_wet_weight = value
                case 3:
                    plankton.raw_dry_weight = value
                case 4:
                    plankton.volume = value
                case 5:
                    plankton.percent = value
                case _:
                    raise ValueError({'missing_value', 'what_was_it'})

    if len(create_bottles) > 0:
        logger.info(_("Creating Net Bottles"))
        core_models.Bottle.objects.bulk_create(create_bottles)

    if len(create_plankton) > 0:
        logger.info(_("Creating Zooplankton Samples"))
        core_models.PlanktonSample.objects.bulk_create(create_plankton.values())