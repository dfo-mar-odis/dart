import csv
import pandas as pd
import numpy as np
from django.db import transaction

from django.utils.translation import gettext as _
from core import models as core_models
from dart2.utils import updated_value

import logging

logger = logging.getLogger('dart')

# popular excel extensions
excel_extensions = ['xls', 'xlsx', 'xlsm']


def get_file_configs(data, file_type):
    sample_configs = core_models.SampleTypeConfig.objects.filter(file_type=file_type)

    # It's expensive to read headers.
    # If a config file matches a sample_field and a value_filed to a file then we'll assume we found
    # the correct header row for the correct tab, then we can narrow down our configs using the same settings
    lowercase_fields = []
    matching_config = None
    for sample_type in sample_configs:
        if not lowercase_fields:
            # get the field choices, then see if they match the file_config's sample_type fields
            tab, skip, field_choices = get_headers(data, file_type, sample_type.tab, sample_type.skip)
            lowercase_fields = [field[0] for field in field_choices]

        if sample_type.sample_field in lowercase_fields and sample_type.value_field in lowercase_fields:
            matching_config = sample_type
            break

        lowercase_fields = []

    if matching_config:
        # we now have a queryset of all configs for this file type, matching a specific tab, header and sample row with
        # values fields in the available columns should give us all file configurations for this type of file that
        # the user can load samples from.
        file_configs = sample_configs.filter(tab=matching_config.tab, skip=matching_config.skip,
                                             sample_field=matching_config.sample_field,
                                             value_field__in=lowercase_fields)
        return file_configs

    return None


def get_headers(data, file_type: str, tab: int = 0, skip: int = -1) -> [int, int, list]:
    field_choices = []
    if file_type == 'csv':
        skip, csv_header = get_csv_header(data.decode('utf-8').split("\r\n"), skip)
        field_choices = [(str(field).lower(), field) for field in csv_header]
    elif file_type in excel_extensions:
        # users won't understand indexing starts at 0 so whatever we're showing them
        # make sure to subtract one
        df = get_excel_dataframe(data, tab, skip)
        skip = df.index.start if skip == -1 else skip
        field_choices = [(str(column).lower(), column) for column in df.columns]

    return [tab, skip, field_choices]


def get_csv_header(file_string: str, header_row: int = -1) -> [int, list]:
    """ takes a file as a stream and uses a csv reader to locate and pull out
        the most likely line to be the header. This will typically be the first
        line that has a value for every column.

        If a header row is provided that row is returned as the header row"""
    csv_reader = csv.reader(file_string, delimiter=',')
    skip = 0
    header_fields = next(csv_reader)
    if header_row < 0:
        while '' in header_fields:
            skip += 1
            header_fields = next(csv_reader)
    else:
        for i in range(header_row):
            skip += 1
            header_fields = next(csv_reader)

    return skip, header_fields


def get_excel_dataframe(stream, sheet_number=-1, header_row=-1):
    """ given a file stream this function will iterate over the rows
        to find the most likely row to use as a column header row then
        will return the dataframe """
    # iterate over the dataframe until the header column has been found.
    if header_row < 0:
        df = pd.read_excel(io=stream, sheet_name=sheet_number)
        df = find_header(df, header_row)
    else:
        df = pd.read_excel(io=stream, sheet_name=sheet_number, header=header_row)
        if header_row > 0:
            df = df[(header_row - 1):]
        else:
            df = df[(header_row):]

    return df


def find_header(df, header_row):
    if header_row < 0:
        for i in range(25):
            temp_df = find_header(df, i)
            columns = [c for c in temp_df.columns if not pd.isna(c)]
            if len(columns) <= 1:
                # if only one column was returned, this is not the data we're looking for
                continue

            if False in [isinstance(c, str) for c in columns]:
                # if the columns are not all strings, this is not the data we're looking for
                continue

            test_col = [c.split(":")[0].lower() for c in columns]
            if test_col.count('unnamed') / len(columns) > 0.75:
                # if more than 3/4 of the columns are 'unnamed', this is not the data we're looking for
                continue

            if temp_df.shape[1] / df.shape[1] < 0.75:
                # if more than 3/4 of the columns were removed, this is not the data we're looking for
                continue

            return temp_df

    elif header_row >= 0:
        header = df.iloc[header_row]
        df = df[header_row + 1:]
        df.columns = header

        # if the user says this is the header line then it's the header line
        # reshap the data to remove columns that do not have column names
        # columns = [c for c in df.columns if not pd.isna(c)]
        # df = df.loc[:, columns]

    return df


def _split_function(x):
    if isinstance(x, str):
        # if the value of x is a string, try to split it
        s_id, r_id = str(x).split("_") if '_' in str(x) else [x, np.nan]
    else:
        # if the value of x is a number keep it and create a nan replica to go with it
        s_id, r_id = [x, np.nan] if not pd.isna(x) else [np.nan, np.nan]

    # if the s_id cannot be cast to an int mark it for removal in the next step
    if not pd.isna(s_id):
        try:
            int(s_id)
        except ValueError:
            s_id = 'N/A'

    return s_id, r_id


def split_sample(dataframe: pd.DataFrame, file_settings: core_models.SampleTypeConfig) -> pd.DataFrame:
    """ if the sample column of the dataframe is of a string type and contains an underscore
        it should be split into s_id and r_id columns """

    sid, rid = 'sid', 'rid'
    # if the file settings specify blanks aren't allowed in the sample column, get rid of all nan rows
    if not file_settings.allow_blank:
        dataframe = dataframe[dataframe[file_settings.sample_field].notna()]

    # if samples have underscores in their column split, them up and create the initial 's_id', 'r_id' columns
    dataframe[[sid, rid]] = dataframe[file_settings.sample_field].apply(
        lambda x: pd.Series(_split_function(x))
    )

    # copy s_ids to nan rows
    if dataframe[sid].isnull().values.any():
        dataframe[sid].fillna(method='ffill', inplace=True)

    # drop and 's_id' row that is not numeric, keeping any nan rows
    dataframe = dataframe[dataframe["sid"] != "N/A"]

    # set the replicate ids
    if dataframe[rid].isnull().values.any():
        tmp = dataframe[[sid, rid]].groupby(sid, group_keys=True).apply(
            lambda x: pd.Series((np.arange(len(x)) + 1), x.index)
        )
        dataframe[rid] = tmp.values

    dataframe[[sid, rid]] = dataframe[[sid, rid]].apply(pd.to_numeric)
    return dataframe


# once all the options are figured out (e.g what tab, what's the sample row, what's the value column)
# this function will convert the dataframe into a sample
def parse_data_frame(settings: core_models.MissionSampleConfig, file_name: str, dataframe: pd.DataFrame):
    mission = settings.mission
    # clear errors for this file
    core_models.FileError.objects.filter(file_name=file_name).delete()

    existing_samples = core_models.Sample.objects.filter(bottle__event__mission=mission)

    create_samples = {}
    update_samples = {'fields': set(), 'models': []}

    create_discrete_values = {}
    update_discrete_values = {'fields': set(), 'models': []}

    errors: [core_models.FileError] = []

    try:
        # convert column names to lower case because it's expected that the file_settings fields will be lowercase
        dataframe.columns = dataframe.columns.str.lower()
        # prep the dataframe by splitting the samples, adding replicates
        sample_config = settings.config

        dataframe = split_sample(dataframe, sample_config)
        sample_id_field, replicate_id_field = 'sid', 'rid'
        value_field = sample_config.value_field
        flag_field = sample_config.flag_field
        comment_field = sample_config.comment_field
        replicate_field = sample_config.replicate_field

        sample_type = sample_config.sample_type
        for row in dataframe.iterrows():
            replicate = 1  # All samples will have at least one 'replicate'
            sample_id = int(row[1][sample_id_field])
            value = row[1][value_field]

            bottles = core_models.Bottle.objects.filter(event__mission=mission, bottle_id=int(sample_id))
            if not bottles.exists():
                message = f"Could not find bottle matching id {sample_id} in file {file_name}"
                error = core_models.FileError(mission=mission, file_name=file_name, line=sample_id, message=message)
                errors.append(error)
                logger.warning(message)
                continue

            bottle = bottles[0]

            db_sample = core_models.Sample(bottle=bottle, type=sample_type, file=file_name)
            if (existing_sample := existing_samples.filter(bottle=bottle, type=sample_type)).exists():
                # if the sample exists then we want to update it. Not create a new one
                db_sample = existing_sample[0]
                update_samples['fields'].add(updated_value(db_sample, 'file', file_name))

                if '' in update_samples['fields']:
                    update_samples['fields'].remove('')

                if len(update_samples['fields']) > 0:
                    update_samples['models'].append(db_sample)
            elif bottle.bottle_id in create_samples:
                db_sample = create_samples[bottle.bottle_id]
            else:
                create_samples[bottle.bottle_id] = db_sample

            if replicate_field:
                replicate = row[1][replicate_field]
            elif replicate_id_field:
                replicate = row[1][replicate_id_field]

                # if replicates aren't allowed on this datatype then there should be an error here if the
                # replicate values is greater than 1
            if not sample_config.allow_replicate and replicate > 1:
                message = _("Duplicate bottle found for sample ") + sample_id
                error = core_models.FileError(mission=mission, file_name=file_name, line=sample_id, message=message)
                errors.append(error)
                logger.warning(message)
                continue

            comment = None
            if comment_field and comment_field in row[1] and not pd.isna(row[1][comment_field]):
                comment = row[1][comment_field]

            flag = None
            if flag_field and flag_field in row[1] and not pd.isna(row[1][flag_field]):
                flag = row[1][flag_field]

            # if db_sample doesn't have a pk, then it hasn't been created yet
            if db_sample.pk and (replicates := db_sample.discrete_values.filter(replicate=replicate)).exists():
                if len(replicates) > 1:
                    message = _("Duplicate replicate id found for sample ") + str(db_sample.bottle.bottle_id)
                    error = core_models.FileError(mission=mission, file_name=file_name, line=sample_id, message=message)
                    errors.append(error)
                    logger.warning(message)
                    continue

                discrete_sample = db_sample.discrete_values.get(replicate=replicate)
                update_discrete_values['fields'].add(updated_value(discrete_sample, 'value', value))
                update_discrete_values['fields'].add(updated_value(discrete_sample, 'comment', comment))
                update_discrete_values['fields'].add(updated_value(discrete_sample, 'flag', flag))

                if '' in update_discrete_values['fields']:
                    update_discrete_values['fields'].remove('')

                if len(update_discrete_values['fields']) > 0:
                    update_discrete_values['models'].append(discrete_sample)
            elif f'{db_sample.bottle_id}_{replicate}' in create_discrete_values:
                message = _("Duplicate replicate id found for sample ") + str(db_sample.bottle.bottle_id)
                error = core_models.FileError(mission=mission, file_name=file_name, line=sample_id, message=message)
                errors.append(error)
                logger.warning(message)
                continue
            else:
                discrete_sample = core_models.DiscreteSampleValue(sample=db_sample, value=value)
                discrete_sample.replicate = replicate
                discrete_sample.comment = comment
                discrete_sample.flag = flag

                create_discrete_values[f'{db_sample.bottle_id}_{replicate}'] = discrete_sample

        with transaction.atomic():
            core_models.Sample.objects.bulk_create(create_samples.values())
            if len(update_samples['models']) > 0:
                core_models.Sample.objects.bulk_update(update_samples['models'], update_samples['fields'])

            core_models.DiscreteSampleValue.objects.bulk_create(create_discrete_values.values())
            if len(update_discrete_values['models']) > 0:
                core_models.DiscreteSampleValue.objects.bulk_update(update_discrete_values['models'],
                                                                    update_discrete_values['fields'])

    except ValueError as ex:
        message = f"Could not parse sample id column '{sample_config.sample_field}', " \
                  f"make sure the right column was selected"
        logger.error(message)
        logger.exception(ex)
        error = core_models.FileError(mission=mission, file_name=file_name, line=-1, message=message)
        errors.append(error)
    except Exception as ex:
        message = f"Unknown issue {ex}: see error log"
        logger.error(message)
        logger.exception(ex)
        error = core_models.FileError(mission=mission, file_name=file_name, line=-1, message=message)
        errors.append(error)

    core_models.FileError.objects.bulk_create(errors)
