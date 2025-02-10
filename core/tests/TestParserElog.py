import io

from django.test import tag

from core import models as core_models
from core.parsers import elog
from core.tests import CoreFactoryFloor as core_factory
from core.tests.TestParsers import logger
from dart.tests.DartTestCase import DartTestCase


@tag('parsers', 'parsers_elog')
class TestElogParser(DartTestCase):

    def setUp(self) -> None:
        self.mission = core_factory.MissionFactory(name='test')

    def assertElogField(self, queryset, required_field, mapped_field):
        self.assertTrue(queryset.filter(required_field=required_field).exists(),
                        f"Missing Required field {required_field}")

        field = queryset.get(required_field=required_field)
        self.assertEqual(mapped_field, field.mapped_field)

    @tag('parsers_elog_test_get_or_create_file_config')
    def test_get_or_create_file_config(self):
        queryset = elog.get_or_create_file_config()

        # the config should only include elog mappings
        values = queryset.values_list('file_type', flat=True).distinct()
        self.assertEqual(1, len(values))
        self.assertEqual(values[0], 'elog')

        self.assertElogField(queryset, 'event', 'Event')
        self.assertElogField(queryset, "time_position", "Time|Position")
        self.assertElogField(queryset, "station", "Station")
        self.assertElogField(queryset, "action", "Action")
        self.assertElogField(queryset, "instrument", "Instrument")
        self.assertElogField(queryset, 'lead_scientist', 'PI')
        self.assertElogField(queryset, 'protocol', "Protocol")
        self.assertElogField(queryset, 'cruise', "Cruise")
        self.assertElogField(queryset, "platform", "Platform")
        self.assertElogField(queryset, "attached", "Attached")
        self.assertElogField(queryset, "start_sample_id", "Sample ID")
        self.assertElogField(queryset, "end_sample_id", "End_Sample_ID")
        self.assertElogField(queryset, "comment", "Comment")
        self.assertElogField(queryset, "data_collector", "Author")
        self.assertElogField(queryset, "sounding", "Sounding")
        self.assertElogField(queryset, "wire_out", "Wire out")
        self.assertElogField(queryset, "flow_start", "Flowmeter Start")
        self.assertElogField(queryset, "flow_end", "Flowmeter End")

    @tag('parsers_elog_test_parse_elog')
    def test_parse_elog(self):
        logger.info("Running test_parse_elog")
        sample_file_pointer = open(r'core/tests/sample_data/good.log', mode='r')

        logger.info("Parsing sample file")
        stream = io.StringIO(sample_file_pointer.read())
        mid_dictionary = elog.parse("good.log", stream)

        # returned dictionary should not be empty
        self.assertIsNotNone(mid_dictionary)

        # Returned dictionary should contain 9 elements
        self.assertEqual(len(mid_dictionary[elog.ParserType.MID]), 9)

        logger.debug(f"Stations: {mid_dictionary[elog.ParserType.STATIONS]}")
        logger.debug(f"Instruments: {mid_dictionary[elog.ParserType.INSTRUMENTS]}")

        sample_file_pointer.close()

    @tag('parsers_elog_test_missing_mid')
    def test_missing_mid(self):
        logger.info("Running test_missing_mid")
        sample_file_pointer = open(r'core/tests/sample_data/missing_mid_bad.log', mode='r')

        logger.info("Parsing sample file")
        stream = io.StringIO(sample_file_pointer.read())
        try:
            elog.parse('missing_mid_bad.log', stream)
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

    @tag('parsers_elog_parse_test_parser_validation')
    def test_parser_validation(self):
        logger.info("Running test_validate_message_object")
        sample_file_pointer = open(r'core/tests/sample_data/bad.log', mode='r')

        stream = io.StringIO(sample_file_pointer.read())
        mid_dictionary = elog.parse("bad.log", stream)

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
        elog_config = elog.get_or_create_file_config()
        buffer = {}
        # load all but the station field into the buffer for testing a field is missing
        for field in elog_config:
            if field.required_field == 'station':
                continue

            buffer[field.mapped_field] = "some value"

        response = elog.validate_message_object(elog_config, buffer)
        self.assertEqual(len(response), 1)
        self.assertIsInstance(response[0], KeyError)
        self.assertEqual(response[0].args[0]['key'], 'station')
        self.assertEqual(response[0].args[0]['expected'], 'Station')
        self.assertEqual(response[0].args[0]['message'], 'Message object missing key')

    def test_process_stations(self):
        stations = ['HL_01', 'HL_02', 'hl_02']

        # make sure the stations don't currently exist
        for station in stations:
            self.assertFalse(core_models.Station.objects.filter(name__iexact=station).exists())

        elog.process_stations(self.mission, stations)

        for station in stations:
            self.assertTrue(core_models.Station.objects.filter(name__iexact=station).exists())

        # HL_02 should have only been added once
        self.assertEqual(len(core_models.Station.objects.filter(name__iexact='HL_02')), 1)

    def test_get_instrument_type(self):
        instruments = [
            ('ctd', core_models.InstrumentType.ctd),
            ('RingNet', core_models.InstrumentType.net),
            ('Viking Buoy', core_models.InstrumentType.buoy),
        ]

        for instrument in instruments:
            instrument_type = elog.get_instrument_type(instrument[0])
            self.assertEqual(instrument_type, instrument[1], f'{instrument[0]} should be of type {instrument[1].name}')

    def test_process_instruments(self):
        instruments = [
            (('ctd', ''), core_models.InstrumentType.ctd),
            (('RingNet', '202um'), core_models.InstrumentType.net),
            (('RingNet', '76um'), core_models.InstrumentType.net),
            (('Viking Buoy', ''), core_models.InstrumentType.buoy),
            (('ctd', ''), core_models.InstrumentType.ctd),
            (('RingNet', '76um'), core_models.InstrumentType.net),
            (('RingNet', '202um'), core_models.InstrumentType.net),
        ]

        # make sure the stations don't currently exist
        for instrument in instruments:
            self.assertFalse(core_models.Instrument.objects.filter(name__iexact=instrument[0]).exists())

        elog.process_instruments(self.mission, [instrument[0] for instrument in instruments])

        # ctd should have only been added once
        self.assertEqual(len(core_models.Instrument.objects.filter(type=core_models.InstrumentType.ctd)), 1)

        # there should be 2 nets
        self.assertEqual(len(core_models.Instrument.objects.filter(type=core_models.InstrumentType.net)), 2)
        # one named 202um
        self.assertEqual(len(core_models.Instrument.objects.filter(name__iexact='202')), 1)

        # one named 76um
        self.assertEqual(len(core_models.Instrument.objects.filter(name__iexact='76')), 1)

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
                "End_Sample_ID": str(expected_end_sample_id),
                "Wire out": "",
                "Flowmeter Start": "",
                "Flowmeter End": "",
                "Attached": ""
            }
        }
        core_factory.StationFactory(name=expected_station)
        core_factory.InstrumentFactory(name=expected_instrument, type=expected_instrument_type)

        events = core_models.Event.objects.using('default').filter(mission=self.mission)
        self.assertFalse(events.exists())
        errors = elog.process_events(self.mission, buffer)

        self.assertEqual(len(errors), 0)

        events = core_models.Event.objects.using('default').filter(mission=self.mission)
        self.assertTrue(events.exists())
        self.assertEqual(len(events), 1)

        event: core_models.Event = events[0]
        self.assertEqual(event.event_id, expected_event_id)
        self.assertEqual(event.instrument.name, expected_instrument)
        self.assertEqual(event.instrument.type, expected_instrument_type)
        self.assertEqual(event.sample_id, expected_sample_id)
        self.assertEqual(event.end_sample_id, expected_end_sample_id)

    def test_process_events_no_station(self):
        buffer = {
            '1': {
                "Event": 1,
                "Station": 'XX_01',
                "Instrument": "CTD",
                "Sample ID": '',
                "End_Sample_ID": '',
                "Wire out": "",
                "Flowmeter Start": "",
                "Flowmeter End": "",
                "Attached": ""
            }
        }

        errors = elog.process_events(self.mission, buffer)
        self.assertEqual(len(errors), 1)

        error = errors[0]
        # The message id the error occurred during
        self.assertEqual(error[0], '1')

        # The message
        self.assertEqual(error[1], 'Error processing events, see error.log for details')

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
                "End_Sample_ID": str(expected_end_sample_id),
                "Wire out": "",
                "Flowmeter Start": "",
                "Flowmeter End": "",
                "Attached": ""
            }
        }

        core_factory.StationFactory(name=expected_station)

        errors = elog.process_events(self.mission, buffer)
        self.assertEqual(len(errors), 1)

        error = errors[0]
        # The message id the error occurred during
        self.assertEqual(error[0], '1')

        # The message
        self.assertEqual(error[1], 'Error processing events, see error.log for details')

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
        event = core_factory.CTDEventFactory(mission=self.mission, event_id=expected_event_id, station=station)

        parse_buffer = {
            elog.ParserType.FILE: {expected_file_name: [1, 2, 3]},
            elog.ParserType.MID: buffer
        }
        errors = elog.process_attachments_actions(event.mission, parse_buffer)
        self.assertEqual(len(errors), 0)

        event = core_models.Event.objects.using('default').get(event_id=expected_event_id)
        self.assertEqual(len(event.attachments.all()), 2)
        self.assertEqual(len(event.actions.all()), 3)

    @tag('parsers_elog_test_get_instrument')
    def test_get_instrument(self):
        # provided an instrument like 'RingNet' or 'CTD' and an attachment list like 'ph | SBE34' or
        # 'flowmeter | 202um', the get_instrument function should return a mock instrument object
        instrument = elog.get_instrument('ctd', 'ph | SBE34')
        self.assertEqual(instrument.name, 'CTD')
        self.assertEqual(instrument.type, core_models.InstrumentType.ctd)

        instrument = elog.get_instrument('RingNet', '202')
        self.assertEqual(instrument.name, '202')
        self.assertEqual(instrument.type, core_models.InstrumentType.net)

        instrument = elog.get_instrument('net', 'flowmeter | 202')
        self.assertEqual(instrument.name, '202')
        self.assertEqual(instrument.type, core_models.InstrumentType.net)

        instrument = elog.get_instrument('net', '76um | flowmeter')
        self.assertEqual(instrument.name, '76')
        self.assertEqual(instrument.type, core_models.InstrumentType.net)
