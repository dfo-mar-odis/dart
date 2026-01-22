import logging
import numpy as np
from django.template.backends.django import reraise

from pandas import DataFrame

from django.db import IntegrityError
from django.utils.translation import gettext as _
from django.db.models import QuerySet

from core import models as core_models
from core.parsers import parser_utils

from bio_tables import models as bio_models
from config.utils import updated_value

from settingsdb.models import FileConfiguration

logger = logging.getLogger('dart')
user_logger = logging.getLogger('dart.user')


def get_or_create_phyto_file_config() -> QuerySet[FileConfiguration]:
    file_type = 'phytoplankton'
    fields = [("id", "SAMPLE_ID", _("Label identifying sample ID column")),
              ("aphia_id", "APHIA_ID", _("Label identifying the APHIA column")),
              ("taxonomic_name", "TAXONOMIC_NAME", _("Label identifying the taxonomic name column")),
              ("modifier", "MODIFIER", _("Label identifying plankton modifier")),
              ("count", "CELLS_LITRE", _("Label identifying the cells per litre count column")),
              ("life_history_seq", "LIFE_HISTORY_SEQ", _("Label identifying the Life History Stage Sequence")),
              ('certainty', 'CERTAINTY', _("Label identifying the certainty column")),
              ('comments', "COMMENTS", _("Label identifying the comments column")),
              ]

    return parser_utils._get_or_create_file_config(file_type, fields)


def get_or_create_zoo_file_config() -> QuerySet[FileConfiguration]:
    file_type = 'zooplankton'
    fields = [("mission", "MISSION", _("Label identifying mission name column")),
              ("date", "DATE", _("Label identifying the sample date column")),
              ("stn", "STN", _("Label identifying the station name column")),
              ("tow", "TOW#", _("Label identifying the tow number column")),
              ("gear", "GEAR", _("Label identifying the gear type column")),
              ('event', 'EVENT', _("Label identifying the event ID column")),
              ('id', "SAMPLEID", _("Label identifying the sample id column")),
              ("depth", "DEPTH", _("Label identifying the sample depth column")),
              ("analysis", "ANALYSIS", _("Label identifying the analysis column")),
              ("split", "SPLIT", _("Label identifying the sample split column")),
              ("aliquot", "ALIQUOT", _("Label identifying the ALIQUOT ID column")),
              ('split_fraction', 'SPLIT_FRACTION', _("Label identifying the split fraction column")),
              ('taxa', "TAXA", _("Label identifying the taxonomic name column")),
              ('ncode', "NCODE", _("Label identifying the n-code column")),
              ('stage', "STAGE", _("Label identifying the life stage column")),
              ('sex', "SEX", _("Label identifying the sex column")),
              ('data_value', "DATA_VALUE", _("Label identifying the data value column")),
              ('procedure_code', "PROC_CODE", _("Label identifying the procedure code column")),
              ('what_was_it', "WHAT_WAS_IT", _("Label identifying the 'what is it' column'")),
              ]

    return parser_utils._get_or_create_file_config(file_type, fields)


def get_or_create_bioness_file_config() -> QuerySet[FileConfiguration]:
    file_type = 'bioness'
    fields = [("mission", "MISSION", _("Label identifying mission name column")),
              ("date", "DATE", _("Label identifying the sample date column")),
              ("stn", "STN", _("Label identifying the station name column")),
              ("tow", "TOW#", _("Label identifying the tow number column")),
              ("gear", "GEAR", _("Label identifying the gear type column")),
              ('event', 'EVENT', _("Label identifying the event ID column")),
              ('id', "SAMPLEID", _("Label identifying the sample id column")),
              ("start_depth", "START_DEPTH", _("Label identifying the sample start depth column")),
              ("end_depth", "END_DEPTH", _("Label identifying the sample end depth column")),
              ("analysis", "ANALYSIS", _("Label identifying the analysis column")),
              ("split", "SPLIT", _("Label identifying the sample split column")),
              ("aliquot", "ALIQUOT", _("Label identifying the ALIQUOT ID column")),
              ('split_fraction', 'SPLIT_FRACTION', _("Label identifying the split fraction column")),
              ('taxa', "TAXA", _("Label identifying the taxonomic name column")),
              ('ncode', "NCODE", _("Label identifying the n-code column")),
              ('stage', "STAGE", _("Label identifying the life stage column")),
              ('sex', "SEX", _("Label identifying the sex column")),
              ('data_value', "DATA_VALUE", _("Label identifying the data value column")),
              ('data_qc_code', "DATA_QC_CODE", _("Label identifying the quality control flag column")),
              ('procedure_code', "PROC_CODE", _("Label identifying the procedure code column")),
              ('what_was_it', "WHAT_WAS_IT", _("Label identifying the 'what is it' column'")),
              ]

    return parser_utils._get_or_create_file_config(file_type, fields)


def parse_phytoplankton(mission: core_models.Mission, filename: str, dataframe: DataFrame):
    database = mission._state.db

    config = get_or_create_phyto_file_config()

    total_rows = dataframe.shape[0]

    # convert all columns to upper case
    dataframe.columns = map(str.upper, dataframe.columns)

    # test to make sure the column names we're looking for are in the file, report the errors if they aren't
    core_models.FileError.objects.filter(file_name=filename,
                                                         type=core_models.ErrorType.plankton).delete()
    for key in [f.mapped_field for f in config.all()]:
        if key.upper() not in dataframe.columns:
            msg = _("Missing or misspelled column name : ") + key
            core_models.FileError.objects.create(mission=mission, file_name=filename, message=msg,
                                                                 line=0, type=core_models.ErrorType.plankton, code=1)

    if core_models.FileError.objects.filter(file_name=filename, type=core_models.ErrorType.plankton):
        raise KeyError("Header Column(s) not found")

    # for phytoplankton bottles are associated with a CTD bottle
    events = mission.events.filter(instrument__type=core_models.InstrumentType.ctd)
    events = events.exclude(actions__type=core_models.ActionType.aborted)
    bottles = core_models.Bottle.objects.filter(event__in=events)

    mission.file_errors.filter(file_name=filename).delete()

    create_plankton = []
    update_plankton = {'objects': [], 'fields': set()}
    errors = []
    for line, row in dataframe.iterrows():

        line_number = line + dataframe.index.start + 1
        user_logger.info(_("Creating plankton sample") + ": %d/%d", line_number, total_rows)

        bottle_id = row[config.get(required_field='id').mapped_field]

        logger.debug(bottle_id)

        if not bottles.filter(bottle_id=bottle_id).exists():
            err = core_models.FileError(mission=mission, file_name=filename, line=line_number,
                                        type=core_models.ErrorType.plankton,
                                        message=_("Bottle does not exist for sample") + f" : {bottle_id}")
            errors.append(err)
            logger.error(err.message)
            continue

        bottle = bottles.get(bottle_id=bottle_id)

        aphiaid = row[config.get(required_field='aphia_id').mapped_field]
        name = row[config.get(required_field='taxonomic_name').mapped_field]
        count = row[config.get(required_field='count').mapped_field]
        certainty = row[config.get(required_field='certainty').mapped_field]
        modifier = row[config.get(required_field='modifier').mapped_field]
        comment = row[config.get(required_field='comments').mapped_field]
        comment = comment if str(comment) != 'nan' else ""

        base_history = 90000000
        life_history = row[config.get(required_field='life_history_seq').mapped_field]
        if life_history < base_history:
            life_history = life_history + base_history

        stage = life_history if not np.isnan(life_history) else None

        if (taxa := bio_models.BCNatnlTaxonCode.objects.filter(aphiaid=aphiaid,
                                                                               taxonomic_name__iexact=name)).exists():
            taxa = taxa[0].national_taxonomic_seq
            logger.debug(taxa)
        else:
            err = core_models.FileError(mission=mission, file_name=filename, line=line_number,
                                        type=core_models.ErrorType.plankton,
                                        message=_("Could not get taxonomic name for sample") + f" : {bottle_id}"
                                        )
            errors.append(err)
            logger.error(err.message)
            continue

        if not bottle.plankton_data.filter(taxa__national_taxonomic_seq=taxa).exists():
            plankton = core_models.PlanktonSample(file=filename, bottle=bottle)

            plankton.count = count
            plankton.modifier = modifier
            plankton.taxa_id = taxa
            plankton.comments = comment + (f' ({str(certainty)})' if certainty and not np.isnan(certainty) else '')

            if stage:
                plankton.stage_id = stage

            create_plankton.append(plankton)
        else:
            updated_fields = set('')

            plankton = bottle.plankton_data.get(taxa=taxa)
            updated_fields.add(updated_value(plankton, 'count', count))
            updated_fields.add(updated_value(plankton, 'taxa_id', taxa))
            updated_fields.add(updated_value(plankton, 'modifier', modifier))
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
    elif mesh_size == 76 or mesh_size == 70:
        return bio_models.BCGear.objects.get(pk=90000105)

    return None


# values taken from AZMP template
def get_min_sieve(proc_code: int, mesh_size: int):
    if proc_code in [21]:
        return 10
    elif proc_code in [20, 22, 23, 50, 99]:
        return mesh_size / 1000

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


# Gets the BioChem taxanomic code based on the taxa_id or the taxa_name if a matching ID can't be found
# a Value Error is raised.
def get_taxonomic_code(taxa_id: int, taxa_name: str) -> bio_models.BCNatnlTaxonCode:
    if taxa := bio_models.BCNatnlTaxonCode.objects.filter(pk=taxa_id):
        taxa = taxa.first()
    elif ((taxa := bio_models.BCNatnlTaxonCode.objects.filter(taxonomic_name__iexact=taxa_name))
          and taxa.count() == 1):
        taxa = taxa.first()
    else:
        raise ValueError(_("Could not find matching taxonomic entry in National Taxon Code Lookup"))

    return taxa

def set_data_column(plankton: core_models.PlanktonSample, what_was_it, value, updated_fields):
    match what_was_it:
        case 1:
            updated_fields.add(updated_value(plankton, 'count', value))
        case 2:
            updated_fields.add(updated_value(plankton, 'raw_wet_weight', value))
        case 3:
            updated_fields.add(updated_value(plankton, 'raw_dry_weight', value))
        case 4:
            updated_fields.add(updated_value(plankton, 'volume', value))
        case 5:
            updated_fields.add(updated_value(plankton, 'percent', value))
        case _:
            raise ValueError({'missing_value', 'what_was_it'})


def set_qc_flag(plankton: core_models.PlanktonSample, what_was_it: int, value):
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


# the default pythong .isnumeric(), .isdecimal() functions can't tell if something like '68.61' is a number, stupid
def is_number(s):
    try:
        float(s)
    except ValueError:
        return False

    return True


def validate_bottle_event(event: core_models.Event, bottle_id: int):
    # Throws an exception if the bottle doesn't validate
    if bottle_id < event.sample_id:
        raise ValueError(_("Bottle ID doesn't match expected IDs for the event"))
    elif event.end_sample_id and bottle_id > event.end_sample_id:
        raise ValueError(_("Bottle ID doesn't match expected IDs for the event"))
    elif bottle_id > event.sample_id:
        raise ValueError(_("Bottle ID doesn't match expected IDs for the event"))


def get_or_create_bottle(bottle_id: int, event_id: int, create_bottles: dict, existing_bottles: QuerySet,
                         gear_type: int, mesh_size: int, start_pressure: float = None, end_pressure: float = 0):

    if bottle_id in create_bottles.keys():
        # use a recently created bottle if it exists, but isn't in the database
         bottle = create_bottles[bottle_id]
    elif (bottle := existing_bottles.filter(bottle_id=bottle_id)).exists():
        # use an existing bottle if one hasn't been recently created
        bottle = bottle.first()

        try:
            validate_bottle_event(bottle.event, bottle.bottle_id)
        except ValueError as ex:
            bottle.delete()
            raise ex

        # update the bottle attributes if required.
        updates = set()
        updates.add(updated_value(bottle, 'gear_type_id', gear_type))
        updates.add(updated_value(bottle, 'mesh_size', mesh_size))
        updates.add(updated_value(bottle, 'pressure', start_pressure))
        updates.add(updated_value(bottle, 'end_pressure', end_pressure))

        if "" in updates:
            updates.remove("")

        if updates:
            bottle.save()
    else:
        # create a new bottle if it doesn't exist and hasn't been recently created bottles, then add the new
        # bottle to the recently created bottles array
        if start_pressure is None:
            message = _("Missing depth")
            raise ValueError(message)

        if not is_number(start_pressure) or np.isnan(start_pressure):
            message = _("Bad depth value")
            raise ValueError(message)

        # if the ringnet bottle doesn't exist in the database or in the created bottles dictionary,
        # it needs to be created and added to the created bottles dictionary
        try:
            event = core_models.Event.objects.get(event_id=event_id, instrument__type=core_models.InstrumentType.net)
        except core_models.Event.DoesNotExist as e:
            message = _("Net event matching ID doesn't exist.")
            raise ValueError(message)
        except core_models.Event.MultipleObjectsReturned as e:
            event = core_models.Event.objects.get(event_id=event_id, instrument__type=core_models.InstrumentType.net,
                                                  instrument__name__icontains=mesh_size)

        if not event.end_date:
            raise ValueError(_("Event is missing required actions"))

        try:
            validate_bottle_event(event, bottle_id)
        except ValueError as ex:
            raise ex

        bottle = core_models.Bottle(bottle_id=bottle_id, event=event, gear_type_id=gear_type, mesh_size=mesh_size,
                                    pressure=start_pressure, end_pressure=end_pressure, closed=event.end_date)
        bottle.save()
        create_bottles[bottle_id] = bottle

    return bottle

def write_plankton_data(filename, errors, create_plankton, update_plankton):
    if len(create_plankton) > 0:
        logger.info(_("Creating Zooplankton Samples"))
        try:
            core_models.PlanktonSample.objects.bulk_create(create_plankton.values())
        except IntegrityError as ex:
            message = _("Could not bulk create Plankton due to a foreign key issue")
            user_logger.error(message)
            for plankton in create_plankton.values():
                try:
                    plankton.save()
                except IntegrityError as ex1:
                    message = str(ex1)
                    message += " " + _("Bottle ID") + f" : {plankton.bottle.bottle_id}"
                    message += " " + _("Event") + f" : {plankton.bottle.event.event_id}"

                    err = core_models.FileError(mission=plankton.bottle.event.mission, file_name=filename, line=-1,
                                            message=message, type=core_models.ErrorType.plankton)
                    err.save()
                    user_logger.error(message)
                    logger.error(_("Issue with plankton: ") + f"{plankton.bottle_id} - {plankton.taxa}")

    logger.info("Setting collector comments")
    for plankton in core_models.PlanktonSample.objects.filter(file=filename):
        new_comment = plankton.comments
        if plankton.raw_wet_weight == -1 or plankton.raw_dry_weight == -1:
            new_comment = 'TOO MUCH PHYTOPLANKTON TO WEIGH'
        elif plankton.raw_wet_weight == -2 or plankton.raw_dry_weight == -2:
            new_comment = 'TOO MUCH SEDIMENT TO WEIGH'
        elif plankton.raw_wet_weight == -3 or plankton.raw_dry_weight == -3:
            new_comment = 'NO FORMALIN - COULD NOT WEIGH'
        elif plankton.raw_wet_weight == -4 or plankton.raw_dry_weight == -4:
            new_comment = 'TOO MUCH JELLY TO WEIGH'

        # if the sample has a pk then we're updating it.
        # If it doesn't have a pk, then it's being created and we should leave it alone
        if field := updated_value(plankton, 'comments', new_comment):
            update_plankton['fields'].add(field)
            if plankton not in update_plankton['objects']:
                update_plankton['objects'].append(plankton)

    if len(update_plankton['objects']) > 0:
        logger.info(_("Updating Zooplankton Samples"))

        fields = [field for field in update_plankton['fields']]
        core_models.PlanktonSample.objects.bulk_update(update_plankton['objects'], fields)


def parse_zooplankton(mission: core_models.Mission, filename: str, dataframe: DataFrame, row_mapping=None):
    config = get_or_create_zoo_file_config()

    total_rows = dataframe.shape[0]

    # convert all columns to upper case
    dataframe.columns = map(str.upper, dataframe.columns)

    # for zooplankton bottles are associated with a RingNet bottles, which won't exist and will have to be created
    # events: QuerySet = mission.events.filter(instrument__type=core_models.InstrumentType.net)

    # don't care about aborted events
    # events = events.exclude(actions__type=core_models.ActionType.aborted)
    # ringnet_bottles: QuerySet = core_models.Bottle.objects.filter(event__in=events)
    ringnet_bottles: QuerySet = core_models.Bottle.objects.filter(event__instrument__type=core_models.InstrumentType.net)

    mission.file_errors.filter(file_name=filename).delete()

    create_plankton = {}
    create_bottles = {}
    update_plankton = {'objects': [], 'fields': set()}
    errors = []
    for line, row in dataframe.iterrows():
        has_errors = False
        updated_fields = set("")

        # both the line and dataframe start at zero, but should start at 1 for human readability
        line_number = (line + 1) + (dataframe.index.start + 1)

        user_logger.info(_("Creating plankton sample") + ": %d/%d", line_number, total_rows)

        bottle = None

        bottle_id = row[config.get(required_field='id').mapped_field]
        event_id = row[config.get(required_field='event').mapped_field]
        taxa_name = row[config.get(required_field='taxa').mapped_field]
        ncode = row[config.get(required_field='ncode').mapped_field]
        taxa_id = 90000000000000 + int(ncode)

        # 90000000 means unassigned
        stage_id = row[config.get(required_field='stage').mapped_field]
        stage = 90000000 + stage_id if not np.isnan(stage_id) else 90000000

        # 90000000 means unassigned
        sex_id = row[config.get(required_field='sex').mapped_field]
        sex = 90000000 + sex_id if not np.isnan(sex_id) else 90000000

        mesh_size = row[config.get(required_field='gear').mapped_field]
        proc_code = row[config.get(required_field='procedure_code').mapped_field]
        split = row[config.get(required_field='split_fraction').mapped_field]
        value = row[config.get(required_field='data_value').mapped_field]
        what_was_it = row[config.get(required_field='what_was_it').mapped_field]
        pressure = row[config.get(required_field='depth').mapped_field]
        end_pressure = 0

        gear_type = get_gear_type(mesh_size)
        min_sieve = get_min_sieve(proc_code=proc_code, mesh_size=mesh_size)
        max_sieve = get_max_sieve(proc_code=proc_code)
        split_fraction = get_split_fraction(proc_code=proc_code, split=split)

        try:
            taxa = get_taxonomic_code(taxa_id, taxa_name)
        except ValueError as e:
            message = (_("Line ") + str(line) + " " + str(e) + f" '{taxa_id}' - '{taxa_name}'")
            error = core_models.FileError(mission=mission, file_name=filename, message=message, line=line_number,
                                          type=core_models.ErrorType.plankton)
            error.save()
            has_errors = True

        if not bio_models.BCSex.objects.filter(pk=sex).exists():
            error_message = _("Could not identify Biochem Sex code ") + str(sex)
            message = (_("Line ") + str(line) + " " + error_message)
            error = core_models.FileError(mission=mission, file_name=filename, message=message, line=line_number,
                                          type=core_models.ErrorType.plankton)
            errors.append(error)

            user_logger.error(message)
            logger.error(message)
            has_errors = True

        if not bio_models.BCLifeHistory.objects.filter(pk=stage).exists():
            error_message = _("Could not identify Biochem Life History code ") + str(stage)
            message = (_("Line ") + str(line) + " " + error_message)
            error = core_models.FileError(mission=mission, file_name=filename, message=message, line=line_number,
                                          type=core_models.ErrorType.plankton)
            errors.append(error)
            user_logger.error(message)
            logger.error(message)
            has_errors = True

        try:
            bottle = get_or_create_bottle(bottle_id, event_id, create_bottles, ringnet_bottles,
                                          gear_type=gear_type.pk, mesh_size=mesh_size,
                                          start_pressure=pressure, end_pressure=end_pressure)
        except ValueError as e:
            message = str(e)
            message += " " + _("Bottle ID") + f" : {bottle_id}"
            message += " " + _("Event") + f" : {row[config.get(required_field='event').mapped_field]}"
            message += " " + _("Line") + f" : {line_number}"

            err = core_models.FileError(mission=mission, file_name=filename, line=line_number, message=message,
                                        type=core_models.ErrorType.plankton)
            errors.append(err)

            user_logger.error(message)
            logger.error(message)
            has_errors = True

        # we want to find as many things wrong as we can on one pass so the user isn't fixing one issue
        # just to be slapped with another.
        if has_errors:
            continue

        plankton_key = f'{bottle_id}_{ncode}_{stage_id}_{sex_id}_{proc_code}'

        plankton = core_models.PlanktonSample.objects.filter(
            bottle=bottle, taxa=taxa, stage_id=stage, sex_id=sex, proc_code=proc_code)
        if plankton.exists():
            # taxa, bottle, stage and sex are all part of a primary key and therefore cannot be updated
            plankton = plankton.first()

            # Gear_type, min_sieve, max_sieve, split_fraction and values based on 'what_was_it' can be updated
            updated_fields.add(updated_value(plankton, 'min_sieve', min_sieve))
            updated_fields.add(updated_value(plankton, 'max_sieve', max_sieve))
            updated_fields.add(updated_value(plankton, 'split_fraction', split_fraction))
            updated_fields.add(updated_value(plankton, 'file', filename))

            set_data_column(plankton, what_was_it, value, updated_fields)

            updated_fields.remove("")
            if len(updated_fields) > 0:
                if plankton not in update_plankton['objects']:
                    update_plankton['objects'].append(plankton)
                update_plankton['fields'].update(updated_fields)

        else:
            if plankton_key not in create_plankton.keys():
                plankton = core_models.PlanktonSample(
                    taxa=taxa, bottle=bottle, min_sieve=min_sieve, max_sieve=max_sieve,
                    split_fraction=split_fraction, stage_id=stage, sex_id=sex,
                    file=filename, proc_code=proc_code,
                )
                create_plankton[plankton_key] = plankton

            plankton = create_plankton[plankton_key]
            set_qc_flag(plankton, what_was_it, value)

    if len(errors) > 0:
        core_models.FileError.objects.bulk_create(errors)
    else:
        write_plankton_data(filename, errors, create_plankton, update_plankton)


def parse_zooplankton_bioness(mission: core_models.Mission, filename: str, dataframe: DataFrame, row_mapping=None):
    config = get_or_create_bioness_file_config()

    total_rows = dataframe.shape[0]

    # convert all columns to upper case
    dataframe.columns = map(str.upper, dataframe.columns)

    # for zooplankton bottles are associated with a RingNet bottles, which won't exist and will have to be created
    events = mission.events.filter(instrument__type=core_models.InstrumentType.net)

    # don't care about aborted events
    # events = events.exclude(actions__type=core_models.ActionType.aborted)
    ringnet_bottles = core_models.Bottle.objects.filter(event__in=events)

    mission.file_errors.filter(file_name=filename).delete()

    create_plankton = {}
    create_bottles = {}
    update_plankton = {'objects': [], 'fields': set()}
    errors = []
    for line, row in dataframe.iterrows():
        updated_fields = set("")

        # both the line and dataframe start at zero, but should start at 1 for human readability
        line_number = (line + 1) + (dataframe.index.start + 1)

        user_logger.info(_("Creating plankton sample") + ": %d/%d", line_number, total_rows)

        bottle_id = row[config.get(required_field='id').mapped_field]
        event_id = row[config.get(required_field='event').mapped_field]
        taxa_name = row[config.get(required_field='taxa').mapped_field]
        ncode = row[config.get(required_field='ncode').mapped_field]
        taxa_id = 90000000000000 + int(ncode)

        # 90000000 means unassigned
        stage_id = row[config.get(required_field='stage').mapped_field]
        stage = 90000000 + stage_id if not np.isnan(stage_id) else 90000000

        # 90000000 means unassigned
        sex_id = row[config.get(required_field='sex').mapped_field]
        sex = 90000000 + sex_id if not np.isnan(sex_id) else 90000000

        mesh_size = row[config.get(required_field='gear').mapped_field]
        proc_code = row[config.get(required_field='procedure_code').mapped_field]
        split = row[config.get(required_field='split_fraction').mapped_field]
        value = row[config.get(required_field='data_value').mapped_field]
        what_was_it = row[config.get(required_field='what_was_it').mapped_field]
        pressure = row[config.get(required_field='start_depth').mapped_field]
        end_pressure = row[config.get(required_field='end_depth').mapped_field]
        qc_flag = row[config.get(required_field='data_qc_code').mapped_field]

        gear_type = 90000092
        min_sieve = get_min_sieve(proc_code=proc_code, mesh_size=mesh_size)
        max_sieve = get_max_sieve(proc_code=proc_code)
        split_fraction = get_split_fraction(proc_code=proc_code, split=split)

        try:
            taxa = get_taxonomic_code(taxa_id, taxa_name)
        except ValueError as e:
            message = (_("Line ") + str(line) + " " + str(e) + f" '{taxa_id}' - '{taxa_name}'")
            error = core_models.FileError(mission=mission, file_name=filename, message=message, line=line_number,
                                          type=core_models.ErrorType.plankton)
            error.save()
            continue

        try:
            # Todo: We need to check that the event exists and that the bottle_id is in the event before we create
            #       a new bottle. Otherwise we might be creating a bottle that shouldn't exist in this mission,
            #       but for loading historical data, this is actually an advantage because they have to make up
            #       bottle IDs for the historical data.
            bottle = get_or_create_bottle(bottle_id, event_id, create_bottles, ringnet_bottles,
                                          gear_type=gear_type, mesh_size=mesh_size,
                                          start_pressure=pressure, end_pressure=end_pressure)
        except ValueError as e:
            message = str(e)
            message += " " + _("Bottle ID") + f" : {bottle_id}"
            message += " " + _("Event") + f" : {row[config.get(required_field='event').mapped_field]}"
            message += " " + _("Line") + f" : {line_number}"

            err = core_models.FileError(mission=mission, file_name=filename, line=line_number, message=message,
                                        type=core_models.ErrorType.plankton)
            errors.append(err)

            user_logger.error(message)
            logger.error(message)
            continue

        plankton_key = f'{bottle_id}_{ncode}_{stage_id}_{sex_id}_{proc_code}'

        plankton = core_models.PlanktonSample.objects.filter(bottle=bottle, taxa=taxa, stage_id=stage,
                                                             sex_id=sex, proc_code=proc_code)
        if plankton.exists():
            # taxa, bottle, stage and sex are all part of a primary key and therefore cannot be updated
            plankton = plankton.first()

            # Gear_type, min_sieve, max_sieve, split_fraction and values based on 'what_was_it' can be updated
            updated_fields.add(updated_value(plankton, 'min_sieve', min_sieve))
            updated_fields.add(updated_value(plankton, 'max_sieve', max_sieve))
            updated_fields.add(updated_value(plankton, 'split_fraction', split_fraction))
            updated_fields.add(updated_value(plankton, 'file', filename))
            updated_fields.add(updated_value(plankton, 'flag', qc_flag))

            set_data_column(plankton, what_was_it, value, updated_fields)

            updated_fields.remove("")
            if len(updated_fields) > 0:
                if plankton not in update_plankton['objects']:
                    update_plankton['objects'].append(plankton)
                update_plankton['fields'].update(updated_fields)

        else:
            if plankton_key not in create_plankton.keys():
                plankton = core_models.PlanktonSample(
                    taxa=taxa, bottle=bottle, min_sieve=min_sieve, max_sieve=max_sieve,
                    split_fraction=split_fraction, stage_id=stage, sex_id=sex, file=filename, proc_code=proc_code
                )
                if qc_flag:
                    plankton.flag = qc_flag

                create_plankton[plankton_key] = plankton

            plankton = create_plankton[plankton_key]
            set_qc_flag(plankton, what_was_it, value)

    write_plankton_data(filename, errors, create_plankton, update_plankton)