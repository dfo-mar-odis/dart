import os

import numpy as np
import pandas as pd
import io
import ctd

from django.core.files.uploadedfile import SimpleUploadedFile

from django.test import tag

import bio_tables.models
from dart2.tests.DartTestCase import DartTestCase
from dart2 import settings

from core import models as core_models
from core.parsers import elog
from core.parsers import ctd as ctd_parser
from core.parsers import SampleParser, PlanktonParser
from core.tests import CoreFactoryFloor as core_factory

import logging

logger = logging.getLogger('dart.test')


@tag('parsers', 'parsers_plankton', 'parsers_plankton_phyto')
class TestPhytoplanktonParser(DartTestCase):

    def setUp(self) -> None:
        self.file_name = "sample_phyto.xlsx"
        self.dataframe = pd.read_excel(os.path.join('core', 'tests', 'sample_data', self.file_name))

        # test that a PlanktonSample is created from a dataframe.
        # this also means that the mission, event, station and bottle id must exist
        # phytoplankton are taken from CTD events
        self.mission = core_factory.MissionFactory(name="HUD2021185")
        self.station = core_factory.StationFactory(name="HL_02")
        self.event_mission_start = core_factory.CTDEventFactory(mission=self.mission, station=self.station,
                                                                sample_id=488275, end_sample_id=488285, event_id=7)
        self.event_mission_end = core_factory.CTDEventFactory(mission=self.mission, station=self.station,
                                                              sample_id=488685, end_sample_id=488695, event_id=92)
        self.bottle_mission_start = core_factory.BottleFactory(event=self.event_mission_start, bottle_id=488275)
        self.bottle_mission_end = core_factory.BottleFactory(event=self.event_mission_end, bottle_id=488685)

    def test_parser(self):

        # this should create 32 plankton samples
        PlanktonParser.parse_phytoplankton(mission_id=self.mission.pk, filename=self.file_name,
                                           dataframe=self.dataframe)
        samples = core_models.PlanktonSample.objects.all()
        self.assertEquals(len(samples), 32)

    def test_update(self):
        # if a plankton sample already exists then it should be updated.
        taxa = bio_tables.models.BCNatnlTaxonCode.objects.get(aphiaid=148912, taxonomic_name__iexact="Thalassiosira")
        core_factory.PhytoplanktonSampleFactory(bottle=self.bottle_mission_start, file=self.file_name, taxa=taxa,
                                                count=1000)

        expected_plankton = core_models.PlanktonSample.objects.get(bottle=self.bottle_mission_start, taxa=taxa)
        self.assertEquals(expected_plankton.count, 1000)

        PlanktonParser.parse_phytoplankton(mission_id=self.mission.pk, filename=self.file_name,
                                           dataframe=self.dataframe)

        expected_plankton = core_models.PlanktonSample.objects.get(bottle=self.bottle_mission_start, taxa=taxa)
        self.assertEquals(expected_plankton.count, 200)


@tag('parsers', 'parsers_plankton', 'parsers_plankton_zoo')
class TestZooplanktonParser(DartTestCase):

    def setUp(self) -> None:
        self.file_name = "sample_zoo.xlsx"
        self.dataframe = pd.read_excel(os.path.join('core', 'tests', 'sample_data', self.file_name))

        # this mission/event load-out matches the events described in the sample_zoo.xlsx file

        # zooplankton needs the mission, event, station and bottle id must exist
        # zooplankton are taken from ringnet events
        self.mission = core_factory.MissionFactory(name="HUD2021185")
        self.station = core_factory.StationFactory(name="HL_02")

        self.event_mission_start = core_factory.NetEventFactory(mission=self.mission, station=self.station,
                                                                sample_id=488275, event_id=2)
        self.event_mission_end = core_factory.NetEventFactory(mission=self.mission, station=self.station,
                                                                sample_id=488685, event_id=88)

    def test_create_zooplankton(self):
        # test that a Zooplankton is created from a dataframe.
        dataframe = pd.DataFrame(data={
            'MISSION': ["HUD2021_185"],
            'DATE': ["2021-09-16"],
            'STN': ["HL_02"],
            'TOW#': ["1-1"],
            'GEAR': [202],
            'EVENT': [2],
            'SAMPLEID': [self.event_mission_start.sample_id],
            'DEPTH': [132],
            'ANALYSIS': [2],
            'SPLIT': [2],
            'ALIQUOT': [0.1],
            'SPLIT_FRACTION': [0.025],
            'TAXA': ["Calanus finmarchicus"],
            'NCODE': [58],
            'STAGE': [30],
            'SEX': [2],
            'DATA_VALUE': [15],
            'PROC_CODE': [20],
            'WHAT_WAS_IT': [1]
        })

        PlanktonParser.parse_zooplankton(mission_id=1, filename=self.file_name, dataframe=dataframe)

        # the taxa key is 90000000000000 plus whatever the ncode is
        taxa_key = 90000000000000 + 58
        taxa = bio_tables.models.BCNatnlTaxonCode.objects.get(pk=taxa_key)

        bottle = core_models.Bottle.objects.get(bottle_id=self.event_mission_start.sample_id)
        plankton = core_models.PlanktonSample.objects.filter(bottle=bottle, taxa=taxa)

        self.assertTrue(plankton.exists())

        plankton = plankton.first()
        self.assertEquals(plankton.taxa.pk, taxa_key)
        self.assertEquals(plankton.stage.pk, 90000030)
        self.assertEquals(plankton.sex.pk, 90000002)

        # this is a 202 net so it should use a 90000102 gear_type
        self.assertEquals(plankton.gear_type.pk, 90000102)

        # proc_code is 20 so the min_sieve should be mesh_size/1000
        self.assertEquals(plankton.min_sieve, 202/1000)

        # proc_code is 20 so the max_sieve should be 10
        self.assertEquals(plankton.max_sieve, 10)

        # proc_code is 20 so the split_fraction should be rounded to 4 decimal places
        self.assertEquals(plankton.split_fraction, 0.025)

        # what_was_it is 1 so this is a count
        self.assertEquals(plankton.count, 15)

    def test_parser_with_data(self):
        # The first parser test is to create a PlanktonSample object, but it doesn't take a lot
        # of things into account when dealing with the real data. like having a row that has the
        # same NCODE and SampleID, but different Sex or Stage

        # the sample data frame should have 28 samples for id 488275 and 42 samples for id 488685
        PlanktonParser.parse_zooplankton(self.mission.pk, self.file_name, self.dataframe)

        samples = core_models.PlanktonSample.objects.filter(bottle__bottle_id=488275)
        self.assertEquals(len(samples), 28)

    def test_get_min_sieve(self):
        self.assertEquals(PlanktonParser.get_min_sieve(proc_code=21, mesh_size=202), 10)

        expected = 202/1000
        self.assertEquals(PlanktonParser.get_min_sieve(proc_code=20, mesh_size=202), expected)
        self.assertEquals(PlanktonParser.get_min_sieve(proc_code=22, mesh_size=202), expected)
        self.assertEquals(PlanktonParser.get_min_sieve(proc_code=23, mesh_size=202), expected)
        self.assertEquals(PlanktonParser.get_min_sieve(proc_code=50, mesh_size=202), expected)
        self.assertEquals(PlanktonParser.get_min_sieve(proc_code=99, mesh_size=202), expected)

    def test_get_max_sieve(self):
        self.assertEquals(PlanktonParser.get_max_sieve(proc_code=20), 10)
        self.assertEquals(PlanktonParser.get_max_sieve(proc_code=22), 10)
        self.assertEquals(PlanktonParser.get_max_sieve(proc_code=50), 10)
        self.assertEquals(PlanktonParser.get_max_sieve(proc_code=99), 10)

        self.assertEquals(PlanktonParser.get_max_sieve(proc_code=21), None)
        self.assertEquals(PlanktonParser.get_max_sieve(proc_code=23), None)

    def test_get_split_fraction(self):
        split = 0.02349
        self.assertEquals(PlanktonParser.get_split_fraction(proc_code=20, split=split), 0.0235)
        self.assertEquals(PlanktonParser.get_split_fraction(proc_code=21, split=split), 1)
        self.assertEquals(PlanktonParser.get_split_fraction(proc_code=22, split=split), 1)
        self.assertEquals(PlanktonParser.get_split_fraction(proc_code=23, split=split), 1)
        self.assertEquals(PlanktonParser.get_split_fraction(proc_code=50, split=split), 0.5)
        self.assertEquals(PlanktonParser.get_split_fraction(proc_code=99, split=split), split)

    def test_get_gear_size_202(self):
        gear_type = PlanktonParser.get_gear_type(202)
        self.assertEquals(gear_type.pk, 90000102)

    def test_get_gear_size_76(self):
        gear_type = PlanktonParser.get_gear_type(76)
        self.assertEquals(gear_type.pk, 90000105)


@tag('parsers', 'parsers_xls')
class TestSampleXLSParser(DartTestCase):
    def test_open_file_oxygen(self):
        expected_oxy_columns = ["Sample", "Bottle#", "O2_Concentration(ml/l)", "O2_Uncertainty(ml/l)",
                                "Titrant_volume(ml)", "Titrant_uncertainty(ml)", "Analysis_date", "Data_file",
                                "Standards(ml)", "Blanks(ml)", "Bottle_volume(ml)", "Initial_transmittance(%%)",
                                "Standard_transmittance0(%%)", "Comments"]

        upload_file = open('core/tests/sample_data/sample_oxy.xlsx', 'rb')
        file_name = upload_file.name
        file = SimpleUploadedFile(file_name, upload_file.read())

        df = SampleParser.get_excel_dataframe(file, 0)
        self.assertEquals(df.index.start, 9)
        self.assertEquals([c for c in df.columns], expected_oxy_columns)

    def test_open_file_oxygen_with_header_row(self):
        # when provided a header row get_excel_dataframe should just skip to that row, even if it's not the real header
        expected_oxy_columns = ["488275_1", "141", "3.804", "0.01", "1.856", "0.002", "2021-09-17 09:31:43",
                                "488275_1.tod", "2.012 2.014 2.010", "0.007 0.003 0.003", "137.06",
                                "0", "0.1", 'Unnamed: 13']

        upload_file = open('core/tests/sample_data/sample_oxy.xlsx', 'rb')
        file_name = upload_file.name
        file = SimpleUploadedFile(file_name, upload_file.read())

        expected_header_row = 10
        df = SampleParser.get_excel_dataframe(file, 0, expected_header_row)
        self.assertEquals(df.shape[0], 414)  # there are 424 rows in this file -expected_header_row gives 414
        self.assertEquals([str(c) for c in df.columns], expected_oxy_columns)


@tag('parsers', 'parsers_ctd')
class TestCTDParser(DartTestCase):

    def setUp(self) -> None:
        self.test_file_location = os.path.join(settings.BASE_DIR, 'core/tests/sample_data/')
        self.test_file_001 = 'JC243a001.BTL'
        self.ctd_data_frame_001 = ctd.from_btl(os.path.join(self.test_file_location, self.test_file_001))

        self.test_file_006 = 'JC243a006.BTL'
        self.ctd_data_frame_006 = ctd.from_btl(os.path.join(self.test_file_location, self.test_file_006))

    def test_process_bottles(self):
        # given a pandas dataframe loaded from the 3rd-part ctd package, and an core.models.Event,
        # process bottles should create core.models.Bottle objects and return validation errors for invalid
        # bottles

        # our sample file is for event 1, it should create 19 bottles with no errors
        event = core_factory.CTDEventFactory(event_id=1, sample_id=495271, end_sample_id=495289)
        ctd_parser.process_bottles(event=event, data_frame=self.ctd_data_frame_001)

        errors = core_models.ValidationError.objects.filter(type=core_models.ErrorType.bottle)

        self.assertEquals(len(errors), 0)

        bottles = core_models.Bottle.objects.filter(event=event)
        self.assertTrue(bottles.exists())
        self.assertEquals(len(bottles), 19)
        self.assertEquals(bottles.first().bottle_id, event.sample_id)
        self.assertEquals(bottles.last().bottle_id, event.end_sample_id)

    def test_process_bottles_update(self):
        # given a pandas dataframe loaded from the 3rd-part ctd package, and an core.models.Event,
        # process bottles should create core.models.Bottle objects and return validation errors for invalid
        # bottles

        # If a bottle already exists, it should be updated with the new data
        bottle_id = 495271
        initial_pressure = 143
        updated_pressure = 145.155

        # our sample file is for event 1, it should create 19 bottles with no errors
        event = core_factory.CTDEventFactory(event_id=1, sample_id=495271, end_sample_id=495289)
        core_factory.BottleFactory(event=event, bottle_number=1, bottle_id=bottle_id, pressure=initial_pressure)

        bottle = core_models.Bottle.objects.get(event=event, bottle_id=bottle_id)
        self.assertEquals(bottle.pressure, initial_pressure)

        ctd_parser.process_bottles(event=event, data_frame=self.ctd_data_frame_001)
        errors = core_models.ValidationError.objects.filter(type=core_models.ErrorType.bottle)

        self.assertEquals(len(errors), 0)

        bottle = core_models.Bottle.objects.get(event=event, bottle_id=bottle_id)
        self.assertEquals(bottle.pressure, updated_pressure)

    def test_process_bottles_validation(self):
        # given a pandas dataframe loaded from the 3rd-part ctd package, and an core.models.Event,
        # process bottles should create core.models.Bottle objects and return validation errors for invalid
        # bottles

        # For CTD event 6 of the JC24301 mission, as an after though, there were 10 extra bottle fired at the surface
        # for calibration reasons. This meant that there were 10 bottles outside the intended sample ID range.
        # Those errors should be reported as Validation errors to let someone know the bottle file has more bottles
        # than are expected. There will also be a bottle mismatch validation error to make the error count 11

        # our sample file is for event 6, it should contain 10 errors
        event = core_factory.CTDEventFactory(event_id=6, sample_id=495290, end_sample_id=495303)

        ctd_parser.process_bottles(event=event, data_frame=self.ctd_data_frame_006)
        errors = core_models.ValidationError.objects.filter(type=core_models.ErrorType.bottle)

        self.assertEquals(len(errors), 11)
        for error in errors:
            self.assertIsInstance(error, core_models.ValidationError)

        # 14 bottles should have been created even though there are 24 bottles in the BTL file
        bottles = core_models.Bottle.objects.filter(event=event)
        self.assertEquals(len(bottles), 14)

    # The number of bottles loaded from a dataframe should match (event.end_sample_id - event.sample_id)
    def test_bottle_count_match_event_validation(self):
        # Given an event with a end_sample_id and a sample_id, and a dataframe an error should be returned if
        # there is a mismatch in the number of bottles in the bottle file compared to the (end_sample_id-sample_id)

        event = core_factory.CTDEventFactory(event_id=1, sample_id=495200, end_sample_id=495300)

        # There are only 19 bottles in ctd_data_frame_001
        ctd_parser.process_bottles(event=event, data_frame=self.ctd_data_frame_001)
        errors = core_models.ValidationError.objects.filter(type=core_models.ErrorType.bottle)

        self.assertEquals(len(errors), 1)

    def test_process_sensors(self):
        # Todo:
        #  test sensor names can be retrieved from ROS files
        #  test sensors can be created from BTL column names
        pass

    def test_process_data(self):
        # Todo:
        #  test that bottles are created provided a datafarme
        #  and that discrete data is added to those bottles
        pass

    def test_read_btl(self):
        # this tests the overall result
        event = core_factory.CTDEventFactory(event_id=1, sample_id=495271, end_sample_id=495289)
        ctd_parser.read_btl(mission=event.mission, btl_file=os.path.join(self.test_file_location, self.test_file_001))

        sample_types = core_models.GlobalSampleType.objects.all()
        samples = core_models.Sample.objects.all()

        self.assertTrue(sample_types.exists())
        self.assertTrue(samples.exists())


@tag('parsers', 'parsers_sample')
class TestSampleCSVParser(DartTestCase):

    def setUp(self) -> None:
        # by the time we get to the parser the mission should exist and the CTD Bottle file should have already
        # been loaded so mission, events and bottles should already exist.

        # this is a setup for the James Cook 2022 mission JC24301,
        # all bottles are attached to one ctd event for simplicity
        self.mission = core_factory.MissionFactory(name='JC24301')
        self.ctd_event = core_factory.CTDEventFactory(mission=self.mission)

        self.file_name = "sample_oxy.csv"
        self.upload_file = os.path.join(settings.BASE_DIR, 'core/tests/sample_data/', self.file_name)

        self.oxy_sample_type = core_models.GlobalSampleType = core_factory.SampleTypeFactory(short_name='oxy',
                                                                                             long_name="Oxygen")

        self.oxy_file_settings: core_models.SampleTypeConfig = core_factory.SampleTypeConfigFactory(
            sample_type=self.oxy_sample_type, file_type='csv', skip=9, tab=0,
            sample_field="sample", value_field="o2_concentration(ml/l)", comment_field="comments",
            allow_blank=False, allow_replicate=True
        )
        self.mission_oxy_file_settings = core_models.MissionSampleConfig = core_factory.MissionSampleConfig(
            mission=self.mission, config=self.oxy_file_settings
        )
        self.salt_sample_type = core_models.GlobalSampleType = core_factory.SampleTypeFactory(short_name='salts',
                                                                                              long_name="Salinity")

        self.salt_file_settings: core_models.SampleTypeConfig = core_factory.SampleTypeConfigFactory(
            sample_type=self.salt_sample_type, file_type='xlsx', skip=1, tab=0,
            sample_field="bottle label", value_field="calculated salinity", comment_field="comments",
            allow_blank=False, allow_replicate=True
        )

    def test_no_duplicate_samples(self):
        # if a sample already exists the parser should update the discrete value, but not create a new sample
        bottle = core_factory.BottleFactory(event__mission=self.mission, bottle_id=495271)
        self.assertIsNotNone(core_models.Bottle.objects.get(pk=bottle.pk))

        sample_type = self.oxy_file_settings.sample_type

        core_factory.SampleFactory(bottle=bottle, type=sample_type, file=self.file_name)

        sample = core_models.Sample.objects.filter(bottle=bottle)
        self.assertEquals(len(sample), 1)

        data = {
            self.oxy_file_settings.sample_field: ['495271_1', '495271_2'],
            self.oxy_file_settings.value_field: [3.932, 3.835],
            self.oxy_file_settings.comment_field: [np.nan, 'hello?']
        }
        df = pd.DataFrame(data)

        different_file = 'some_other_file.csv'
        SampleParser.parse_data_frame(self.mission_oxy_file_settings, different_file, df)

        sample = core_models.Sample.objects.filter(bottle=bottle)
        self.assertEquals(len(sample), 1)
        self.assertEquals(sample.first().file, different_file)

    def test_no_duplicate_discrete(self):
        # if a discrete value for a sample already exists the parser should update the discrete value,
        # but not create a new one
        bottle = core_factory.BottleFactory(event=self.ctd_event, bottle_id=495271)
        self.assertIsNotNone(core_models.Bottle.objects.get(pk=bottle.pk))

        sample_type = self.oxy_sample_type

        sample = core_factory.SampleFactory(bottle=bottle, type=sample_type, file=self.file_name)
        core_factory.DiscreteValueFactory(sample=sample, replicate=1, value=0.001, comment="some comment")

        discrete = core_models.DiscreteSampleValue.objects.filter(sample=sample)
        self.assertEquals(len(discrete), 1)

        # this should update one discrete value and attach a second to the sample
        data = {
            self.oxy_file_settings.sample_field: ['495271_1', '495271_2'],
            self.oxy_file_settings.value_field: [3.932, 3.835],
            self.oxy_file_settings.comment_field: [np.nan, 'hello?']
        }
        df = pd.DataFrame(data)

        SampleParser.parse_data_frame(self.mission_oxy_file_settings, self.file_name, df)

        discrete = core_models.DiscreteSampleValue.objects.filter(sample=sample)
        self.assertEquals(len(discrete), 2)
        self.assertEquals(discrete[0].replicate, 1)
        self.assertEquals(discrete[0].value, 3.932)
        self.assertEquals(discrete[0].comment, None)

        self.assertEquals(discrete[1].replicate, 2)
        self.assertEquals(discrete[1].value, 3.835)
        self.assertEquals(discrete[1].comment, 'hello?')

    def test_missing_bottle_validation(self):
        # no bottles were created for this test we should get a bunch of validation errors

        file_name = "fake_file.csv"

        bottle_id = 495600
        bottle = core_factory.BottleFactory(bottle_id=bottle_id)
        sample = core_factory.SampleFactory(bottle=bottle, type=self.oxy_file_settings.sample_type)
        core_factory.DiscreteValueFactory(sample=sample)

        data = {
            self.oxy_file_settings.sample_field: [f"{bottle_id}_1"],
            self.oxy_file_settings.value_field: [0.38]
        }
        df = pd.DataFrame(data)
        SampleParser.parse_data_frame(self.mission_oxy_file_settings, file_name=file_name, dataframe=df)

        samples = core_models.Sample.objects.filter(bottle__bottle_id=bottle_id)
        self.assertEquals(len(samples), 1)

    @tag('parsers_sample_split')
    def test_data_frame_split_sample(self):
        # some sample files, like oxygen, use a sample_id with an underscore to delimit replicates
        # (i.e 495600_1, 495600_2). I want to split the sample column up into sid and rid before parsing

        data = {
            self.oxy_file_settings.sample_field: ["495600_1", "495600_2", "495601_1", "495601_2", "495602_1",
                                                  "495602_2"],
            self.oxy_file_settings.value_field: [1.01, 1.02, 2.01, 2.02, 3.01, 3.02]
        }
        dataframe = pd.DataFrame(data)
        logger.debug(dataframe)

        df = SampleParser.split_sample(dataframe, self.oxy_file_settings)
        self.assertIn('sid', df)
        self.assertIn('rid', df)
        logger.debug(dataframe)

    @tag('parsers_sample_split')
    def test_data_frame_split_allow_blank(self):
        # some sample files, like CHL, have every other sample id blank where the blank column is a replicate
        # of the last id

        expected_sample_ids = [495600, 495600, 495601, 495601, 495602, 495602]
        expected_replicates = [1, 2, 1, 2, 1, 2]
        expected_values = [1.01, 1.02, 2.01, 2.02, 3.01, 3.02]
        self.oxy_file_settings.allow_blank = True
        data = {
            self.oxy_file_settings.sample_field: [495600, np.nan, 495601, np.nan, 495602, np.nan],
            self.oxy_file_settings.value_field: expected_values
        }
        dataframe = pd.DataFrame(data)
        logger.debug(dataframe)

        df = SampleParser.split_sample(dataframe, self.oxy_file_settings)
        logger.debug(df)
        self.assertIn('sid', df)
        self.assertIn('rid', df)

        for i in range(len(expected_sample_ids)):
            row = df.iloc[i, :]
            self.assertEquals(row[self.oxy_file_settings.value_field], expected_values[i])
            self.assertEquals(row['sid'], expected_sample_ids[i])
            self.assertEquals(row['rid'], expected_replicates[i])

    @tag('parsers_sample_split')
    def test_data_frame_split_remove_calibration(self):
        # some sample files, like salts, have calibration samples mixed in with bottle samples
        # The calibration samples, and values where the sample id is none, should be removed

        expected_sample_ids = [495600, 495601, 495602, 495602]
        expected_replicates = [1, 1, 1, 2]
        expected_values = [1.01, 2.01, 3.01, 3.02]
        file_settings = self.salt_file_settings

        data = {
            file_settings.sample_field: ["p_012", np.nan, "495600", np.nan, "495601", np.nan, "495602", "495602"],
            file_settings.value_field: [np.nan, np.nan, 1.01, 1.02, 2.01, 2.02, 3.01, 3.02]
        }

        dataframe = pd.DataFrame(data)
        logger.debug(dataframe)

        df = SampleParser.split_sample(dataframe, file_settings)
        logger.debug(df)
        self.assertIn('sid', df)
        self.assertIn('rid', df)

        for i in range(len(expected_sample_ids)):
            row = df.iloc[i, :]
            self.assertEquals(row[file_settings.value_field], expected_values[i])
            self.assertEquals(row['sid'], expected_sample_ids[i])
            self.assertEquals(row['rid'], expected_replicates[i])

    @tag('parsers_sample_split')
    def test_data_frame_split_no_blanks(self):
        # some sample files, like salts, have lots of blanks in the sample column. If a replicate is present
        # the sample ID will appear twice, but if a row has no sample id it shouldn't be kept

        expected_sample_ids = [495600, 495600, 495601, 495602]
        expected_replicates = [1, 2, 1, 1]
        expected_values = [1.011, 1.01, 2.01, 3.01]
        file_settings = self.salt_file_settings
        data = {
            file_settings.sample_field: ["p_012", "495600", "495600", np.nan, "495601", np.nan, "495602", np.nan],
            file_settings.value_field: [np.nan, 1.011, 1.01, 1.02, 2.01, 2.02, 3.01, 3.02]
        }

        dataframe = pd.DataFrame(data)
        logger.debug(dataframe)

        df = SampleParser.split_sample(dataframe, file_settings)
        logger.debug(df)
        self.assertIn('sid', df)
        self.assertIn('rid', df)

        for i in range(len(expected_sample_ids)):
            row = df.iloc[i, :]
            self.assertEquals(row[file_settings.value_field], expected_values[i])
            self.assertEquals(row['sid'], expected_sample_ids[i])
            self.assertEquals(row['rid'], expected_replicates[i])

    def test_data_frame_column_convert(self):
        # it's expected that the file_settings fields will be lower case fields so the columns of the dataframe
        # should also be all lowercase
        data = {
            'Sample ID': ["495600_1", "495600_2", "495601_1", "495601_2", "495602_1", "495602_2"],
            'Value': [1.01, 1.02, 2.01, 2.02, 3.01, 3.02]
        }
        dataframe = pd.DataFrame(data)

        logger.debug(dataframe)
        df: pd.DataFrame = dataframe.columns.str.lower()

        self.assertIn('sample id', df)
        self.assertIn('value', df)

        logger.debug(dataframe)

    def test_parser_oxygen(self):
        # bottles start with 495271

        core_factory.BottleFactory(event=self.ctd_event, bottle_id=495271)
        core_factory.BottleFactory(event=self.ctd_event, bottle_id=495600)

        data = {
            self.oxy_file_settings.sample_field: ['495271_1', '495271_2', '495600_1'],
            self.oxy_file_settings.value_field: [3.932, 3.835, 3.135],
            self.oxy_file_settings.comment_field: [np.nan, np.nan, 'Dropped magnet in before H2SO4; sorry']
        }
        df = pd.DataFrame(data)

        SampleParser.parse_data_frame(self.mission_oxy_file_settings, file_name=self.file_name, dataframe=df)

        errors = core_models.FileError.objects.filter(file_name=self.file_name)
        self.assertEquals(len(errors), 0)
        bottles = core_models.Bottle.objects.filter(event=self.ctd_event)

        # check that a replicate was created for the first sample
        bottle_with_replicate = bottles.get(bottle_id=495271)
        self.assertIsNotNone(bottle_with_replicate)

        sample = bottle_with_replicate.samples.get(type=self.oxy_file_settings.sample_type)
        self.assertIsNotNone(sample)

        dv_value = sample.discrete_values.get(replicate=1).value
        self.assertEquals(dv_value, 3.932)

        dv_value = sample.discrete_values.get(replicate=2).value
        self.assertEquals(dv_value, 3.835)

        # check that the comment for bottle 495600 was captured
        bottle_with_comment = bottles.get(bottle_id=495600)
        self.assertIsNotNone(bottle_with_comment)

        sample = bottle_with_comment.samples.get(type=self.oxy_file_settings.sample_type)
        self.assertIsNotNone(sample)

        dv_value = sample.discrete_values.get(replicate=1).value
        self.assertEquals(dv_value, 3.135)

        dv_comment = sample.discrete_values.get(replicate=1).comment
        self.assertEquals(dv_comment, "Dropped magnet in before H2SO4; sorry")

    def test_duplicate_error(self):
        # if there are multiple samples with the same replicate id there should be a 'duplicate' error.
        # this will normally occur in a file like Oxygen where the sample ID column is formatted as
        # 495294_1, where the 1 is the replicate value. In samples like salts the sample column doesn't
        # contain a replicate, we just add a new replicate if an ID is found more than once.

        core_factory.BottleFactory(event=self.ctd_event, bottle_id=491)
        data = {
            self.oxy_file_settings.sample_field: ['491_1', '491_1'],
            self.oxy_file_settings.value_field: [3.9, 3.88],
        }

        df = pd.DataFrame(data)
        SampleParser.parse_data_frame(self.mission_oxy_file_settings, self.file_name, df)

        errors = core_models.FileError.objects.filter(file_name=self.file_name)
        self.assertEquals(len(errors), 1)
        self.assertIsInstance(errors[0], core_models.FileError)
        self.assertEquals(errors[0].message, 'Duplicate replicate id found for sample 491')


@tag('parsers', 'parsers_elog')
class TestElogParser(DartTestCase):

    def setUp(self) -> None:
        self.mission = core_factory.MissionFactory(name='test')

        logger.info("getting the elog configuration")
        self.config = core_models.ElogConfig.get_default_config(self.mission)

    # The parser should take a file and return a dictionary of mid objects, stations and instruments,
    # each MID object is a dictionary of key value pairs,
    # the stations and instruments are sets so unique stations and instruments to this log file will be returned.

    @tag('parsers_elog_parse')
    def test_parse_elog(self):
        logger.info("Running test_parse_elog")
        sample_file_pointer = open(r'core/tests/sample_data/good.log', mode='r')

        logger.info("Parsing sample file")
        stream = io.StringIO(sample_file_pointer.read())
        mid_dictionary = elog.parse(stream, self.config)

        # returned dictionary should not be empty
        self.assertIsNotNone(mid_dictionary)

        # Returned dictionary should contain 9 elements
        self.assertEquals(len(mid_dictionary[elog.ParserType.MID]), 9)

        logger.debug(f"Stations: {mid_dictionary[elog.ParserType.STATIONS]}")
        logger.debug(f"Instruments: {mid_dictionary[elog.ParserType.INSTRUMENTS]}")

        sample_file_pointer.close()

    @tag('parsers_elog_parse')
    def test_missing_mid(self):
        logger.info("Running test_missing_mid")
        sample_file_pointer = open(r'core/tests/sample_data/missing_mid_bad.log', mode='r')

        logger.info("Parsing sample file")
        stream = io.StringIO(sample_file_pointer.read())
        try:
            elog.parse(stream, self.config)
            self.fail("A lookup error should have been thrown")
        except LookupError as e:
            logger.info("Received the expected exception")
            self.assertIn('message', e.args[0])  # This is what happened
            logger.info(f"Exception Message: {e.args[0]['message']}")
            self.assertIn('paragraph', e.args[0])  # This is to help figure out where it happened
            logger.info(f"Exception Paragraph:\n{e.args[0]['paragraph']}")
        except Exception as e:
            logger.exception(e)
            raise e

        sample_file_pointer.close()

    @tag('parsers_elog_parse')
    def test_parser_validation(self):
        logger.info("Running test_validate_message_object")
        sample_file_pointer = open(r'core/tests/sample_data/bad.log', mode='r')

        stream = io.StringIO(sample_file_pointer.read())
        mid_dictionary = elog.parse(stream, self.config)

        self.assertIn(elog.ParserType.ERRORS, mid_dictionary)
        self.assertIn('1', mid_dictionary[elog.ParserType.ERRORS])
        self.assertIn('2', mid_dictionary[elog.ParserType.ERRORS])
        self.assertIn('3', mid_dictionary[elog.ParserType.ERRORS])

        # There should be ValueErrors in the array for message object 1 describing what keys are missing
        for i in range(0, len(mid_dictionary[elog.ParserType.ERRORS]['1'])):
            self.assertIsInstance(mid_dictionary[elog.ParserType.ERRORS]['1'][i], KeyError)
            logger.info(f"Error {i}: {mid_dictionary[elog.ParserType.ERRORS]['1'][i]}")

        # There should be ValueErrors in the array for message object 1 describing what keys are missing
        for i in range(0, len(mid_dictionary[elog.ParserType.ERRORS]['2'])):
            self.assertIsInstance(mid_dictionary[elog.ParserType.ERRORS]['2'][i], KeyError)
            logger.info(f"Error {i}: {mid_dictionary[elog.ParserType.ERRORS]['2'][i]}")

        # There should be ValueErrors in the array for message object 1 describing what keys are missing
        for i in range(0, len(mid_dictionary[elog.ParserType.ERRORS]['3'])):
            self.assertIsInstance(mid_dictionary[elog.ParserType.ERRORS]['3'][i], KeyError)
            logger.info(f"Error {i}: {mid_dictionary[elog.ParserType.ERRORS]['3'][i]}")

        sample_file_pointer.close()

    @tag('parsers_elog_validate_message_object')
    def test_validate_message_object(self):
        elog_config = core_models.ElogConfig.get_default_config(self.mission)
        buffer = {}
        # load all but the station field into the buffer for testing a field is missing
        for field in elog_config.mappings.all():
            if field.field == 'station':
                continue

            buffer[field.mapped_to] = "some value"

        response = elog.validate_message_object(elog_config, buffer)
        self.assertEquals(len(response), 1)
        self.assertIsInstance(response[0], KeyError)
        self.assertEquals(response[0].args[0]['key'], 'station')
        self.assertEquals(response[0].args[0]['expected'], 'Station')
        self.assertEquals(response[0].args[0]['message'], 'Message object missing key')

    def test_process_stations(self):
        stations = ['HL_01', 'HL_02', 'hl_02']

        # make sure the stations don't currently exist
        for station in stations:
            self.assertFalse(core_models.Station.objects.filter(name__iexact=station).exists())

        elog.process_stations(stations)

        for station in stations:
            self.assertTrue(core_models.Station.objects.filter(name__iexact=station).exists())

        # HL_02 should have only been added once
        self.assertEquals(len(core_models.Station.objects.filter(name__iexact='HL_02')), 1)

    def test_get_instrument_type(self):
        instruments = [
            ('ctd', core_models.InstrumentType.ctd),
            ('RingNet', core_models.InstrumentType.net),
            ('Viking Buoy', core_models.InstrumentType.buoy),
        ]

        for instrument in instruments:
            instrument_type = elog.get_instrument_type(instrument[0])
            self.assertEquals(instrument_type, instrument[1], f'{instrument[0]} should be of type {instrument[1].name}')

    def test_get_instrument(self):
        instruments = [
            ('ctd', core_models.InstrumentType.ctd),
            ('RingNet', core_models.InstrumentType.net),
            ('Viking Buoy', core_models.InstrumentType.buoy),
        ]

        for instrument in instruments:
            # instrument shouldn't exist
            self.assertFalse(core_models.Instrument.objects.filter(name__iexact=instrument[0]).exists())

            db_instrument = elog.get_instrument(instrument[0])
            self.assertEquals(db_instrument.name, instrument[0])
            self.assertEquals(db_instrument.type, instrument[1])

            # instrument should exist
            self.assertTrue(core_models.Instrument.objects.filter(name__iexact=instrument[0]).exists())

            # and it should be of type xxx
            self.assertEquals(core_models.Instrument.objects.get(name__iexact=instrument[0]).type, instrument[1])

    def test_process_instruments(self):
        instruments = [
            ('ctd', core_models.InstrumentType.ctd),
            ('RingNet', core_models.InstrumentType.net),
            ('Viking Buoy', core_models.InstrumentType.buoy),
            ('ctd', core_models.InstrumentType.ctd),
        ]

        # make sure the stations don't currently exist
        for instrument in instruments:
            self.assertFalse(core_models.Instrument.objects.filter(name__iexact=instrument[0]).exists())

        elog.process_instruments([instrument[0] for instrument in instruments])

        for instrument in instruments:
            self.assertTrue(core_models.Instrument.objects.filter(name__iexact=instrument[0]).exists())

        # HL_02 should have only been added once
        self.assertEquals(len(core_models.Instrument.objects.filter(name__iexact='ctd')), 1)

    def test_process_events(self):
        expected_event_id = 1
        expected_station = "HL_02"
        expected_instrument = "CTD"
        expected_instrument_type = core_models.InstrumentType.ctd
        expected_sample_id = 490000
        expected_end_sample_id = 490012
        buffer = {
            '1': {
                "Event": str(expected_event_id),
                "Station": expected_station,
                "Instrument": expected_instrument,
                "Sample ID": str(expected_sample_id),
                "End_Sample_ID": str(expected_end_sample_id)
            }
        }
        core_factory.StationFactory(name=expected_station)
        core_factory.InstrumentFactory(name=expected_instrument, type=expected_instrument_type)

        events = core_models.Event.objects.filter(mission=self.mission)
        self.assertFalse(events.exists())
        errors = elog.process_events(buffer, self.mission)

        self.assertEquals(len(errors), 0)

        events = core_models.Event.objects.filter(mission=self.mission)
        self.assertTrue(events.exists())
        self.assertEquals(len(events), 1)

        event: core_models.Event = events[0]
        self.assertEquals(event.event_id, expected_event_id)
        self.assertEquals(event.instrument.name, expected_instrument)
        self.assertEquals(event.instrument.type, expected_instrument_type)
        self.assertEquals(event.sample_id, expected_sample_id)
        self.assertEquals(event.end_sample_id, expected_end_sample_id)

    def test_process_events_no_station(self):
        buffer = {
            '1': {
                "Event": 1,
                "Station": 'XX_01',
                "Instrument": "CTD",
                "Sample ID": '',
                "End_Sample_ID": ''
            }
        }

        errors = elog.process_events(buffer, self.mission)
        self.assertEquals(len(errors), 1)

        error = errors[0]
        # The message id the error occurred during
        self.assertEquals(error[0], '1')

        # The message
        self.assertEquals(error[1], 'Error processing events, see error.log for details')

        # The actual exception that occurred
        self.assertIsInstance(error[2], core_models.Station.DoesNotExist)
        logger.info(error)

    def test_process_events_no_instrument(self):
        expected_event_id = 1
        expected_station = "HL_02"
        expected_instrument = "xxx"
        expected_sample_id = 490000
        expected_end_sample_id = 490012
        buffer = {
            '1': {
                "Event": str(expected_event_id),
                "Station": expected_station,
                "Instrument": expected_instrument,
                "Sample ID": str(expected_sample_id),
                "End_Sample_ID": str(expected_end_sample_id)
            }
        }

        core_factory.StationFactory(name=expected_station)

        errors = elog.process_events(buffer, self.mission)
        self.assertEquals(len(errors), 1)

        error = errors[0]
        # The message id the error occurred during
        self.assertEquals(error[0], '1')

        # The message
        self.assertEquals(error[1], 'Error processing events, see error.log for details')

        # The actual exception that occurred
        self.assertIsInstance(error[2], core_models.Instrument.DoesNotExist)
        logger.info(error)

    def test_process_attachments_actions(self):
        expected_file_name = "2020020a.log"
        expected_event_id = 1
        expected_station = "HL_02"
        expected_instrument = "CTD"
        expected_sounding = 181
        expected_sample_id = 490000
        expected_end_sample_id = 490012
        expected_attached_field = "SBE34 | pH"
        expected_time_position_field = "2022-10-02 | 142135.242 | 44 16.04264 N | 63 19.03938 W"
        expected_comment_field = "No Comment"
        expected_data_collector_field = "Patrick Upson"
        buffer = {
            '1': {
                "Event": str(expected_event_id),
                "Station": expected_station,
                "Instrument": expected_instrument,
                "Sample ID": str(expected_sample_id),
                "End_Sample_ID": str(expected_end_sample_id),
                "Sounding": expected_sounding,
                "Action": core_models.ActionType.deployed.label,
                "Attached": expected_attached_field,
                "Time|Position": expected_time_position_field,
                "Author": expected_data_collector_field,
                "Comment": expected_comment_field
            },
            '2': {
                "Event": str(expected_event_id),
                "Station": expected_station,
                "Instrument": expected_instrument,
                "Sample ID": str(expected_sample_id),
                "End_Sample_ID": str(expected_end_sample_id),
                "Sounding": expected_sounding,
                "Action": core_models.ActionType.bottom.label,
                "Attached": expected_attached_field,
                "Time|Position": expected_time_position_field,
                "Author": expected_data_collector_field,
                "Comment": expected_comment_field
            },
            '3': {
                "Event": str(expected_event_id),
                "Station": expected_station,
                "Instrument": expected_instrument,
                "Sample ID": str(expected_sample_id),
                "End_Sample_ID": str(expected_end_sample_id),
                "Sounding": expected_sounding,
                "Action": core_models.ActionType.recovered.label,
                "Attached": expected_attached_field,
                "Time|Position": expected_time_position_field,
                "Author": expected_data_collector_field,
                "Comment": expected_comment_field
            }
        }

        station = core_factory.StationFactory(name=expected_station)
        core_factory.CTDEventFactory(mission=self.mission, event_id=expected_event_id, station=station)

        errors = elog.process_attachments_actions(buffer, self.mission, expected_file_name)
        self.assertEquals(len(errors), 0)

        event = core_models.Event.objects.get(event_id=expected_event_id)
        self.assertEquals(len(event.attachments.all()), 2)
        self.assertEquals(len(event.actions.all()), 3)
