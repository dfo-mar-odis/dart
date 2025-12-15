import chardet
import re

from io import BytesIO, StringIO

import numpy as np
import pandas as pd
import pandas.errors
from pandas import ExcelFile

from django.utils.translation import gettext_lazy as _

from bio_tables.sync_tables import create_fixture
from biochem.upload import create_model
from settingsdb import models
from core import models as core_models

import logging

logger = logging.getLogger("dart.user")


class BottleError(ValueError):
    code = None
    message = None

    def __init__(self, message, code):
        super(BottleError, self).__init__(message)
        self.code = code
        self.message = message


def bottle_test(bottle_ids, bottle_id):
    if bottle_id not in bottle_ids:
        if bottle_id > bottle_ids[0] - 100:
            message = _("Possible TSG Sample." + f" : {bottle_id}")
            code = 201
        else:
            message = _("Bottle does not exist in this mission." + f" : {bottle_id}")
            code = 200
        raise BottleError(message, code)


class SampleParser:
    _sample_file_config: models.SampleFileType = models.SampleFileType()

    excel = None
    headers: list[str] | None = None
    buffer: BytesIO | StringIO = None
    dataframe: pd.DataFrame = None

    def set_allowed_replicates(self, allowed_replicates: int):
        self._sample_file_config.allowed_replicates = allowed_replicates
        return self

    def set_allow_blank_sample_ids(self, are_blank_sample_ids_replicates: bool):
        self._sample_file_config.are_blank_sample_ids_replicates = are_blank_sample_ids_replicates
        return self

    def set_tab(self, tab):
        # if the tab changes we will want to relocate the headers if that function is called.
        if tab != self._sample_file_config.tab:
            self.headers = None

        self._sample_file_config.tab = tab
        return self

    def set_skip(self, skip):
        # if the skip changes we will want to relocate the headers if that function is called.
        if skip != self._sample_file_config.tab:
            self.headers = None

        self._sample_file_config.skip = skip
        return self

    def set_sample_field(self, sample_field):
        self._sample_file_config.sample_field = sample_field
        return self

    def set_comment_field(self, comment_field):
        self._sample_file_config.comment_field = comment_field
        return self

    def get_file_type(self):
        return self._sample_file_config.file_type

    def get_skip(self):
        return self._sample_file_config.skip

    def get_tab(self):
        return self._sample_file_config.tab

    def get_allowed_replicates(self):
        return self._sample_file_config.allowed_replicates

    def get_blank_samples_allowed(self):
        return self._sample_file_config.are_blank_sample_ids_replicates

    def get_sample_field(self) -> str | None:
        if self._sample_file_config.sample_field is None:
            potential_sample_fields = ['BOTTLE LABEL', 'SAMPLE', 'ID', 'I.D.']
            try:
                headers = [head.upper() for head in self.get_headers()]
                for field in potential_sample_fields:
                    if field in headers:
                        self._sample_file_config.sample_field = field

                if self._sample_file_config.sample_field is None:
                    self._sample_file_config.sample_field = headers[0]

            except ValueError:
                self._sample_file_config.sample_field = None

        return self._sample_file_config.sample_field

    def get_comment_field(self) -> str | None:
        if self._sample_file_config.comment_field is None:
            potential_sample_fields = ['COMMENT', 'COMMENTS']
            try:
                headers = [head.upper() for head in self.get_headers()]
                for field in potential_sample_fields:
                    if field in headers:
                        self._sample_file_config.comment_field = field
            except ValueError:
                self._sample_file_config.comment_field = None

        return self._sample_file_config.comment_field

    def get_sample_config(self):
        return self._sample_file_config

    def set_sample_config(self, sample_config: models.SampleFileType):
        self._sample_file_config = sample_config
        return self

    def get_data_frame(self) -> pd.DataFrame:
        if self.dataframe is not None:
            return self.dataframe

        if self.excel:
            tab_names = self.get_tabs()
            self.dataframe = pd.read_excel(self.buffer, skiprows=self._sample_file_config.skip,
                                           sheet_name=tab_names[self._sample_file_config.tab])
        else:
            self.dataframe = pd.read_csv(self.buffer, skiprows=self._sample_file_config.skip)
        return self.dataframe

    def _get_csv_header_row(self, skip=0):
        try:
            data_frame = pd.read_csv(self.buffer, skiprows=skip, nrows=30, header=None)
        except pandas.errors.ParserError as e:
            # if a csv file starts with a bunch of metadata then we could expect an error like:
            #   'Error tokenizing data. C error: Expected 1 fields in line 9, saw 14'
            #
            # Which tells us we should try parsing the file again starting with line 9
            error_message = str(e)
            if "Expected" in error_message and "fields in line" in error_message:
                line_number = int(error_message.split("line")[1].split(",")[0].strip())
                self.buffer.seek(0)  # Reset buffer for re-reading
                return self._get_csv_header_row(line_number - 1)
            else:
                raise e  # Re-raise if it's a different error

        for index, row in data_frame.iterrows():
            if all(isinstance(value, str) for value in row):
                return skip + index

        raise ValueError("No header row with only strings found in the first 30 rows.")

    def _get_xls_header_row(self, skip=0):
        try:
            tab_names = self.get_tabs()
            data_frame = pd.read_excel(self.buffer, sheet_name=tab_names[self._sample_file_config.tab], skiprows=skip,
                                       nrows=30, header=None)
        except pandas.errors.ParserError as e:
            # if a csv file starts with a bunch of metadata then we could expect an error like:
            #   'Error tokenizing data. C error: Expected 1 fields in line 9, saw 14'
            #
            # Which tells us we should try parsing the file again starting with line 9
            error_message = str(e)
            if "Expected" in error_message and "fields in line" in error_message:
                line_number = int(error_message.split("line")[1].split(",")[0].strip())
                self.buffer.seek(0)  # Reset buffer for re-reading
                return self._get_xls_header_row(line_number - 1)
            else:
                raise e  # Re-raise if it's a different error

        for index, row in data_frame.iterrows():
            if all(isinstance(value, str) for value in row):
                return skip + index

        raise ValueError("No header row with only strings found in the first 30 rows.")

    def get_headers(self) -> list[str]:
        if self.headers:
            return self.headers

        # if skip == -1 then we're going to try and automatically locate the line
        # most likely to be the header line for the tabular data.
        # Otherwise, self.get_data_frame() will return whatever line skip is referencing.
        if self._sample_file_config.skip == -1:
            if self.excel is None:
                self._sample_file_config.skip = self._get_csv_header_row()
            else:
                self._sample_file_config.skip = self._get_xls_header_row()
            self.buffer.seek(0)  # Reset buffer for re-reading

        data_frame: pd.DataFrame = self.get_data_frame()
        self.headers = [str(col) for col in data_frame.columns if not str(col).startswith("Unnamed:")]
        return self.headers

    def get_tabs(self) -> list[str] | None:
        if not self.excel:
            return None

        return self.excel.sheet_names

    def __init__(self, mission_id, file_name: str, file_type: str, data):
        self.mission_id = mission_id
        self.file_name = file_name
        self._sample_file_config.file_type = file_type.upper()
        self.set_skip(-1)

        if isinstance(data, bytes):
            detected = chardet.detect(data)
            encoding = detected.get('encoding', 'utf-8')
            self.buffer = BytesIO(data) if file_type.startswith('XLS') else StringIO(data.decode(encoding))
        elif isinstance(data, str):
            self.buffer = StringIO(data)
        else:
            raise ValueError("Data must be either string or bytes.")

        if file_type.startswith('XLS'):
            self.excel = ExcelFile(self.buffer)

    def process_dataframe(self) -> pd.DataFrame:
        sample_field = self._sample_file_config.sample_field
        dataframe = self.get_data_frame()
        dataframe.columns = dataframe.columns.map(str.upper)
        if sample_field not in dataframe.columns:
            raise ValueError(f"Column '{sample_field}' not found in the dataframe.")

        if self._sample_file_config.are_blank_sample_ids_replicates:
            # Fill blank rows in the sample_field column with the last non-blank value
            dataframe[sample_field] = dataframe[sample_field].fillna(method='ffill')
        else:
            dataframe = dataframe.dropna(subset=[sample_field])

        # Determine if the sample_field contains xxx_# format
        def is_xxx_format(value):
            return bool(re.search(r'_(\d+)$', str(value)))

        if dataframe[sample_field].dropna().apply(is_xxx_format).any():
            # Case 1: Handle xxx_# format
            def extract_replicate(value):
                match = re.search(r'_(\d+)$', value)
                if match:
                    return int(match.group(1)), value[:match.start()]
                return None, value

            replicate_column = []
            updated_sample_field = []

            for value in dataframe[sample_field]:
                replicate, updated_value = extract_replicate(value)
                replicate_column.append(replicate)
                updated_sample_field.append(updated_value)

            dataframe[sample_field] = updated_sample_field
            # Ensure the field is converted to numeric
            dataframe[sample_field] = pd.to_numeric(dataframe[sample_field], errors='coerce').fillna(0).astype(int)
            dataframe['rid'] = replicate_column
        else:
            # Case 2: Handle blanks in the sample_field
            dataframe[sample_field] = dataframe[sample_field].fillna(method='ffill')
            dataframe['rid'] = dataframe.groupby(sample_field).cumcount() + 1

        # Remove rows where the sample_field is a string
        dataframe = dataframe[~dataframe[sample_field].apply(lambda x: isinstance(x, str))]
        return dataframe

    def parse(self):
        vars = self._sample_file_config.variables.all()
        dataframe = self.process_dataframe()

        # this handles bottle type errors that occur when a bottle isn't within a rage of bottles the mission allows
        error_type = core_models.ErrorType.bottle
        base_error_attrs = {
            "mission_id": self.mission_id,
            "file_name": self.file_name,
            "type": error_type
        }

        core_models.FileError.objects.filter(file_name__iexact=self.file_name, code=200, type=error_type).delete()
        core_models.FileError.objects.filter(file_name__iexact=self.file_name, code=201, type=error_type).delete()

        bottle_ids = dict(
            core_models.Bottle.objects.order_by('bottle_id').filter(event__mission_id=self.mission_id).values_list(
                'bottle_id', 'id'))

        # Create core_models.MissionSampleType objects for each SampleTypeVariable
        mission_sample_types = dict()
        existing_discrete_values = dict()

        create_sample_type = []
        for var in vars:
            if (st := core_models.MissionSampleType.objects.filter(
                    mission_id=self.mission_id, name__iexact=var.name)).exists():
                mission_sample_type = st.first()
                ds_vals = core_models.DiscreteSampleValue.objects.filter(sample__type=mission_sample_type)
                for ds in ds_vals:
                    existing_discrete_values[(ds.sample.bottle_id, ds.sample.type_id, ds.replicate)] = ds
            else:
                mission_sample_type = core_models.MissionSampleType(
                    mission_id=self.mission_id, name=var.name, datatype_id=var.datatype)
                create_sample_type.append(mission_sample_type)
            mission_sample_types[var.value_field] = mission_sample_type

        # Create core_models.Sample and core_models.DiscreteSampleValue objects for each row
        create_samples = dict()
        update_samples = []
        create_discrete_sample_values = []
        update_discrete_sample_values = []
        update_discrete_fields = set()
        errors = []
        total_rows = len(dataframe)
        for row_index, row in dataframe.iterrows():
            if row_index % 10 == 0:
                logger.info("Processing row %d/%d", row_index, total_rows)

            replicate_id = row['rid']
            bottle_id = row[self._sample_file_config.sample_field]
            if np.isnan(bottle_id):
                # if the bottle id column is nan at this point then skip it. It's a blank line.
                continue

            comment = None
            if self._sample_file_config.comment_field and self._sample_file_config.comment_field in row:
                comment = row[self._sample_file_config.comment_field]

            try:
                bottle_test(list(bottle_ids.keys()), bottle_id)
            except BottleError as ex:
                error = core_models.FileError(line=(row_index + 1), message=ex.message, code=ex.code,
                                              **base_error_attrs)
                errors.append(error)
                continue

            for var in vars:
                if var.value_field in row:
                    value = row[var.value_field]
                    if np.isnan(value):
                        continue

                    flag = None
                    if var.flag_field:
                        flag = row[var.flag_field] if var.flag_field in row else None
                        flag = None if np.isnan(flag) else flag

                    limit = None
                    if var.limit_field:
                        limit = row[var.limit_field] if var.limit_field in row else None
                        limit = None if not None and np.isnan(limit) else limit

                    mst = mission_sample_types[var.value_field]
                    bottle_pk = bottle_ids.get(bottle_id)
                    discrete_sample_value = None
                    if mst.id and (bottle_pk, mst.id, replicate_id) in existing_discrete_values:
                        discrete_sample_value = existing_discrete_values[(bottle_pk, mst.id, replicate_id)]
                        sample = discrete_sample_value.sample
                        sample.file = self.file_name
                        update_samples.append(sample)
                    elif (bottle_id, mst.name) not in create_samples:
                        sample = core_models.Sample(bottle_id=bottle_pk, type=mst, file=self.file_name)
                        create_samples[(bottle_id, mst.name)] = sample
                    else:
                        sample = create_samples[(bottle_id, mst.name)]

                    if discrete_sample_value:
                        def field_test(field_name, old_value, new_value):
                            if old_value != new_value:
                                update_discrete_fields.add(field_name)
                                return True
                            return False

                        modified = False or field_test("value", discrete_sample_value.value, value)
                        modified = modified or field_test("flag", discrete_sample_value.flag, flag)
                        modified = modified or field_test("limit", discrete_sample_value.limit, limit)
                        modified = modified or field_test("comment", discrete_sample_value.comment, comment)

                        if modified:
                            update_discrete_sample_values.append(discrete_sample_value)
                    else:
                        discrete_sample_value = core_models.DiscreteSampleValue(sample=sample, replicate=replicate_id)
                        create_discrete_sample_values.append(discrete_sample_value)

                    discrete_sample_value.value = value
                    discrete_sample_value.flag = flag
                    discrete_sample_value.limit = limit
                    discrete_sample_value.comment = comment

        if errors:
            core_models.FileError.objects.bulk_create(errors)

        if create_sample_type:
            core_models.MissionSampleType.objects.bulk_create(create_sample_type)

        if create_samples:
            core_models.Sample.objects.bulk_create(create_samples.values())

        if update_samples:
            core_models.Sample.objects.bulk_update(update_samples, ['file'])

        if create_discrete_sample_values:
            core_models.DiscreteSampleValue.objects.bulk_create(create_discrete_sample_values)

        if update_discrete_sample_values:
            core_models.DiscreteSampleValue.objects.bulk_update(update_discrete_sample_values, update_discrete_fields)
