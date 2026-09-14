from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from django.test import tag
import pprint

from config.tests.DartTestCase import DartTestCase
from core.tests import CoreFactoryFloor
from core.parsers.samples import samplefile_parser_file_config
from core.parsers.samples.samplefile_config import file_config_from_db
from settingsdb.models import SampleFileConfig, SampleFileConfigColumns

from core import models as core_models
from bio_tables import models as bio_tables_models

import logging
logger = logging.getLogger(__name__)

pp = pprint.PrettyPrinter(indent=2, sort_dicts=False)


@tag("samplefile_parser_file_config")
class TestSampleFileParserFileConfig(DartTestCase):

    def setUp(self):
        self.config = SampleFileConfig.objects.create(
            name="Sample Oxygen File Parser",
            description="Used for parsing oxygen",
            file_type=".csv",
            tab=0,
            header_line=8,
            sample_id_column_name="sample",
            comment_column_name="comments",
            allow_replicates=True,
            allow_blank_sample_ids=False)

        self.config_column = SampleFileConfigColumns.objects.create(
            file_config=self.config,
            column_alias="oxy",
            value_column_name="o2_concentration(ml/l)",
            detection_limit_column_name=None,
            quality_control_column_name=None,
            datatype_id=90000007
        )
        self.file_name = 'oxygen.csv'
        self.path = Path('core', 'tests', 'sample_data', 'sample_loader', self.file_name)
        with open(self.path, 'rb') as f:
            self.oxygen_stream = BytesIO(f.read())

    def test_read_csv_stream(self):
        # provided a BytesIO stream and a config object the _read_stream_to_df function should create
        # a dataframe with the expected columns (based on the config and the sample file) and not throw an error
        expected_columns = ["sample","bottle#","o2_concentration(ml/l)","qc","o2_uncertainty(ml/l)","titrant_volume(ml)",
                            "titrant_uncertainty(ml)","analysis_date","data_file","standards(ml)","blanks(ml)","bottle_volume(ml)",
                            "initial_transmittance(%%)","standard_transmittance0(%%)","comments"]

        f_config = file_config_from_db(self.config, self.file_name, self.oxygen_stream)
        df = samplefile_parser_file_config._read_stream_to_df(self.oxygen_stream, f_config)

        logger.debug(df.head())
        logger.debug(df.columns)

        assert df is not None, "Expected a DataFrame, got None"
        for c in expected_columns:
            assert c in df.columns, f"Column '{c}' was not found in df.columns"

    @tag("samplefile_parser_file_config_test_get_column_defs")
    def test_get_column_defs(self):
        # provided a list of column configurations (SampleFileConfigColumns objects) the
        # _get_column_definitions should return a dictionary of column definitions
        f_config = file_config_from_db(self.config, self.file_name, self.oxygen_stream)
        col_def = samplefile_parser_file_config._get_column_definitions_from_value_columns(f_config)
        assert col_def is not None, "Expected a column definition, got None"
        logger.debug(pp.pformat(col_def))

    @tag("samplefile_parser_file_config_test_get_sample_column")
    def test_get_sample_column(self):
        # This emulates the beginning of the samplefile_parser_file_config.parse_sample_file function
        # the point is to see that sample ids and replicates are being properly processed.
        sample_col_name = (self.config.sample_id_column_name or "").strip().lower()

        f_config = file_config_from_db(self.config, self.file_name, self.oxygen_stream)
        df = samplefile_parser_file_config._read_stream_to_df(self.oxygen_stream, f_config)
        for idx, row in df.iterrows():
            # extract sample id cell
            sample_cell = row.get(sample_col_name) if sample_col_name else None
            parsed = samplefile_parser_file_config._parse_sample_id(sample_cell)

            assert parsed is not None, "Expected a sample ID, got None"
            logger.debug(pp.pformat(parsed))
            if idx > 5:
                break

    def run_parser_create_bottles(self, sample_mission):
        # This runs the parser function, but creates Bottles as the function runs so that it won't fail
        # typically these bottles are created by other parts of the application before samples are added
        # to a mission so the function expects them to exists.

        # create an Event attached to the mission and a Bottle for that event
        event = CoreFactoryFloor.CTDEventFactory.create(mission=sample_mission)

        original_filter = samplefile_parser_file_config.core_models.Bottle.objects.filter

        def fake_filter(*f_args, **f_kwargs):
            qs = original_filter(*f_args, **f_kwargs)
            if not qs.exists():
                # extract bottle_id passed to filter (int or str)
                bid = f_kwargs.get('bottle_id')
                # create a Bottle attached to the event used in this test
                CoreFactoryFloor.BottleFactory.create(event=event, bottle_id=bid)
                qs = original_filter(*f_args, **f_kwargs)
            return qs

        f_config = file_config_from_db(self.config, self.file_name, self.oxygen_stream)

        # Patch the filter call inside the parser module so it returns a QS-like object whose .first() returns our bottle
        with patch('core.parsers.samples.samplefile_parser_file_config.core_models.Bottle.objects.filter', new=fake_filter) as mock_filter:
            # call the parser — it will receive the mocked filter result
            result = samplefile_parser_file_config.parse_sample_file(
                self.oxygen_stream, f_config, sample_mission, self.file_name
            )

        return  result

    @tag("samplefile_parser_file_config_test_full_parse")
    def test_full_parse(self):
        # provided a mission, config, BytesIO stream and a file name the parse_sample_file
        # function should parse the stream and return an array of errors, created samples and created values.
        sample_mission = CoreFactoryFloor.MissionFactory.create(name='TST25013')

        result = self.run_parser_create_bottles(sample_mission)

        logger.debug(pp.pformat(result.to_dict()))
        assert result is not None, "Expected a results dict, got None"


    @tag("samplefile_parser_file_config_test_full_parse_alias")
    def test_full_parse_no_alias(self):
        # If no alias is provided to the SampleFileConfig object the function should use the
        # datatype method as the alias if it exists.
        sample_mission = CoreFactoryFloor.MissionFactory.create(name='TST25013')

        datatype = bio_tables_models.BCDataType.objects.get(pk=self.config_column.datatype_id)
        self.config_column.column_alias = datatype.method
        self.config_column.save()

        result = self.run_parser_create_bottles(sample_mission)

        sample_types = sample_mission.mission_sample_types.all()
        assert len(sample_types) == 1, "Expected exactly one sample type, got {}".format(len(sample_types))
        assert sample_types.first().name == datatype.method, "sample type name doesn't match the expected datatype method"