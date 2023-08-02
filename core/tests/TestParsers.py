import io

from django.test import tag
from dart2.tests.DartTestCase import DartTestCase

from core import models as core_models
from core.parsers import elog
from core.tests import CoreFactoryFloor as core_factory

import logging

logger = logging.getLogger('dart.test')


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