import csv
import pandas as pd
import numpy as np

from core import models as core_models

import logging

logger = logging.getLogger('dart')

# popular excel extensions
excel_extensions = ['xls', 'xlsx', 'xlsm']


def get_file_configs(data, file_type):
    configs = []
    file_configs = core_models.SampleFileSettings.objects.filter(file_type=file_type)

    tab = -1
    skip = -1
    field_choices = []

    # It's expensive to read headers.
    # If a config file matches a sample_field and a value_filed to a file then we'll assume we found
    # the correct header row for the correct tab, then we can narrow down our configs using the same settings
    lowercase_fields = []
    matching_config = None
    for config in file_configs:
        if not lowercase_fields:
            # get the field choices, then see if they match the file_config's sample_type fields
            tab, skip, field_choices = get_headers(data, file_type, config.tab, config.header)
            lowercase_fields = [field[0] for field in field_choices]

        if config.sample_field in lowercase_fields and config.value_field in lowercase_fields:
            matching_config = config
            break

        lowercase_fields = []

    if matching_config:
        # we now have a queryset of all configs for this file type, matching a specific tab, header and sample row with
        # values fields in the available columns should give us all file configurations for this type of file that
        # the user can load samples from.
        file_configs = file_configs.filter(tab=matching_config.tab, header=matching_config.header,
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
        skip = df.index.start
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
    df = pd.read_excel(io=stream, sheet_name=sheet_number)
    df = find_header(df, header_row)

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

    elif header_row > 0:
        header = df.iloc[header_row-1]
        df = df[header_row:]
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


def split_sample(dataframe: pd.DataFrame, file_settings: core_models.SampleFileSettings) -> pd.DataFrame:
    """ if the sample column of the dataframe is of a string type and contains an underscore
        it should be split into s_id and r_id columns """

    # if the file settings specify blanks aren't allowed in the sample column, get rid of all nan rows
    if not file_settings.allow_blank:
        dataframe = dataframe[dataframe[file_settings.sample_field].notna()]

    # if samples have underscores in their its column split them up and create the initial 's_id', 'r_id' columns
    dataframe[['s_id', 'r_id']] = dataframe[file_settings.sample_field].apply(
        lambda x: pd.Series(_split_function(x))
    )

    # copy s_ids to nan rows
    if dataframe['s_id'].isnull().values.any():
        dataframe['s_id'].fillna(method='ffill', inplace=True)

    # drop and 's_id' row that is not numeric, keeping any nan rows
    dataframe = dataframe[dataframe["s_id"] != "N/A"]

    # set the replicate ids
    if dataframe['r_id'].isnull().values.any():
        tmp = dataframe[['s_id', 'r_id']].groupby('s_id', group_keys=True).apply(
            lambda x: pd.Series((np.arange(len(x))+1), x.index)
        )
        dataframe['r_id'] = tmp.values

    dataframe[['s_id', 'r_id']] = dataframe[['s_id', 'r_id']].apply(pd.to_numeric)
    return dataframe


# once all the options are figured out (e.g what tab, what's the sample row, what's the value column)
# this function will convert the dataframe into a sample
def parse_data_frame(mission: core_models.Mission, file_settings: core_models.SampleFileSettings,
                     file_name: str, dataframe: pd.DataFrame):

    # clear errors for this file
    core_models.FileError.objects.filter(file_name=file_name).delete()

    create_samples = {}
    create_discrete_values = []
    errors: [core_models.FileError] = []

    try:
        # convert column names to lower case because it's expected that the file_settings fields will be lowercase
        dataframe.columns = dataframe.columns.str.lower()
        # prep the dataframe by splitting the samples, adding replicates
        dataframe = split_sample(dataframe, file_settings)
        sample_id_field = 's_id'
        replicate_id_field = 'r_id'
        for row in dataframe.iterrows():
            sample_id = row[1][sample_id_field]
            value = row[1][file_settings.value_field]

            bottles = core_models.Bottle.objects.filter(event__mission=mission, bottle_id=int(sample_id))
            if not bottles.exists():
                message = f"Could not find bottle matching id {sample_id} in file {file_name}"
                error = core_models.FileError(mission=mission, file_name=file_name, line=sample_id, message=message)
                errors.append(error)
                logger.warning(message)
                continue

            bottle = bottles[0]

            db_sample = core_models.Sample(bottle=bottle, type=file_settings.sample_type, file=file_name)
            if bottle.bottle_id in create_samples:
                db_sample = create_samples[bottle.bottle_id]

            create_samples[bottle.bottle_id] = db_sample
            new_sample_discrete = core_models.DiscreteSampleValue(sample=db_sample, value=value)

            if file_settings.replicate_field:
                new_sample_discrete.replicate = row[1][file_settings.replicate_field]
            elif replicate_id_field:
                new_sample_discrete.replicate = row[1][replicate_id_field]

            # if replicates aren't allowed on this datatype then there should be an error here if the
            # replicate values is greater than 1
            if not file_settings.allow_replicate and new_sample_discrete.replicate > 1:
                message = f"Duplicate bottle found for {sample_id} in file {file_name}"
                error = core_models.FileError(mission=mission, file_name=file_name, line=sample_id, message=message)
                errors.append(error)
                logger.warning(message)
                continue

            if file_settings.comment_field:
                new_sample_discrete.comment = row[1][file_settings.comment_field]

            if file_settings.flag_field:
                new_sample_discrete.flag = row[1][file_settings.flag_field]

            create_discrete_values.append(new_sample_discrete)

        core_models.Sample.objects.bulk_create(create_samples.values())
        core_models.DiscreteSampleValue.objects.bulk_create(create_discrete_values)
    except Exception as ex:
        message = f"Unknown issue {ex}: see error log"
        logger.error(message)
        logger.exception(ex)
        error = core_models.FileError(mission=mission, file_name=file_name, line=-1, message=message)
        errors.append(error)
    finally:
        core_models.FileError.objects.bulk_create(errors)
