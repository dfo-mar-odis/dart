import io
import os
import numpy as np

from datetime import datetime

from django.test import tag
from django.conf import settings

from core import models as core_models
from settingsdb import models as settings_models

from core.parsers import elog, andes, event_csv
from core.tests import CoreFactoryFloor as core_factory
from core.tests.TestParsers import logger
from config.tests.DartTestCase import DartTestCase


@tag('parsers', 'event_parsers', 'parsers_elog')
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

    def test_get_instrument_name(self):
        instruments = [
            ('ctd', core_models.InstrumentType.ctd),
            ('RingNet', core_models.InstrumentType.net),
            ('Viking Buoy', core_models.InstrumentType.buoy),
        ]

        for instrument in instruments:
            instrument_name = elog.get_instrument_name(instrument[0])
            self.assertEqual(instrument_name, instrument[1], f'{instrument[0]} should be of type {instrument[1].name}')

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
        expected_instrument_name = core_models.InstrumentType.ctd
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
        core_factory.InstrumentFactory(name=expected_instrument, type=expected_instrument_name)

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
        self.assertEqual(event.instrument.type, expected_instrument_name)
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


@tag('parsers', 'event_parsers', 'andes_parser')
class TestAndesParser(DartTestCase):
    test_file_name = "CAR-2024-924 DART Export (2024-06-10).json"
    test_file_location = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
    test_file = os.path.join(test_file_location, test_file_name)

    def setUp(self):
        andes.logger = logger
        self.mission = core_factory.MissionFactory(
            name='CAR-2024-924',
            start_date=datetime.strptime("2024-05-23 09:00:00", '%Y-%m-%d %H:%M:%S'),
            end_date=datetime.strptime("2024-06-18 18:00:00", '%Y-%m-%d %H:%M:%S')
        )

    @tag('andes_parser_test_andeis_parser_init')
    def test_andeis_parser_init(self):
        with open(self.test_file, 'r') as f:
            stream = io.StringIO(f.read())
            andes.parse(self.mission, self.test_file_name, stream)

        instruments = core_models.Instrument.objects.all()
        self.assertEqual(5, instruments.count())  # the test file has 5 instruments in it

    @tag('andes_parser_test_andeis_parser_instruments')
    def test_andeis_parser_instruments(self):
        instruments = [
            {
                'name': "CTD AZOMP 2024",
                'instrument_type': "CTD"
            },
            {
                'name': "Plankton net (202um)",
                'instrument_type': "Plankton net",
            },
            {
                'name': "Plankton net (76um)",
                'instrument_type': "Plankton Net",  # made "Net" uppercase to test case sensitivity
            },
            {
                "id": 8,
                "name": "Argo (BIO AZOMP)",
                "instrument_type": "ARGO",
                "components": []
            }
        ]

        andes.parse_instruments(self.mission, self.test_file_name, instruments)

        mission_instruments = core_models.Instrument.objects.using('default').all()
        self.assertIsNotNone(mission_instruments.get(name__iexact='CTD AZOMP 2024'))
        ctd = mission_instruments.get(name__iexact='CTD AZOMP 2024')
        self.assertEqual(core_models.InstrumentType.ctd, ctd.type)

        self.assertIsNotNone(mission_instruments.get(name__iexact='Plankton net (202um)'))
        net = mission_instruments.get(name__iexact='Plankton net (202um)')
        self.assertEqual(core_models.InstrumentType.net, net.type)

        self.assertIsNotNone(mission_instruments.get(name__iexact='Plankton net (76um)'))
        net = mission_instruments.get(name__iexact='Plankton net (76um)')
        self.assertEqual(core_models.InstrumentType.net, net.type)

        self.assertIsNotNone(mission_instruments.get(name__iexact='Argo (BIO AZOMP)'))
        beacon = mission_instruments.get(name__iexact='Argo (BIO AZOMP)')
        self.assertEqual(core_models.InstrumentType.other, beacon.type)

    @tag('andes_parser_test_andeis_parser_stations')
    def test_andeis_parser_stations(self):
        # give a list of 'samples', which is really a list of stations, but the Andes report referes to them
        # as samples, stations from each sample should be added to the mission station table
        samples = [
            {
                "station": "AR7W_13",
            },
            {
                "station": "AR7W_13.5",
            }
        ]

        andes.parse_stations(self.mission, self.test_file_name, samples)

        stations = core_models.Station.objects.all()
        self.assertEqual(len(samples), stations.count())
        station = stations.get(name__iexact='AR7W_13')
        self.assertIsNotNone(station)

    @tag('andes_parser_test_andeis_parser_events')
    def test_andeis_parser_events(self):
        station = core_factory.StationFactory(name='AR7W_13')
        ctd_instrument = core_factory.CTDInstrumentFactory(name='CTD AZOMP 2024')
        net_instrument = core_factory.InstrumentFactory(name='Plankton net (202μm)',
                                                        type=core_models.InstrumentType.net)
        expected_bottles = [
            {"id": 76, "uid": 505561},
            {"id": 77, "uid": 505562},
            {"id": 78, "uid": 505563},
            {"id": 79, "uid": 505564},
            {"id": 80, "uid": 505565},
            {"id": 81, "uid": 505566},
            {"id": 82, "uid": 505567},
            {"id": 83, "uid": 505568},
            {"id": 84, "uid": 505569},
            {"id": 85, "uid": 505570},
            {"id": 86, "uid": 505571},
            {"id": 87, "uid": 505572},
            {"id": 88, "uid": 505573},
            {"id": 89, "uid": 505574},
            {"id": 90, "uid": 505575},
            {"id": 91, "uid": 505576},
            {"id": 92, "uid": 505577},
            {"id": 93, "uid": 505578},
            {"id": 94, "uid": 505579},
            {"id": 95, "uid": 505580},
            {"id": 96, "uid": 505581},
            {"id": 97, "uid": 505582},
            {"id": 98, "uid": 505583},
            {"id": 99, "uid": 505584}
        ]
        samples = [{
            "station": "AR7W_13",
            "comment": "- HPU motor reset on descent at 500m. Paused and resumed without issue. \r\n- Bottle 18 misfire.\r\n- Spigot on bottle 21 broke allowing air into bottle. Did not sample gases / TIC / pH from this bottle. \r\n- Winds 35+ did not perform second net",
            "operator": "Chris Gordon",
            "events": [
                {
                    "event_number": 10.0,
                    "instrument": "CTD AZOMP 2024",
                    "instrument_type": "CTD",
                    "wire_out": "3312 m",
                    "wire_angle": None,
                    "flow_meter_start": None,
                    "flow_meter_end": None,
                    'bottles': expected_bottles
                },
                {
                    "event_number": 11.0,
                    "instrument": "Plankton net (202μm)",
                    "instrument_type": "Net",
                    "wire_out": "1000 m",
                    "wire_angle": "45 degrees",
                    "flow_meter_start": 2068,
                    "flow_meter_end": 2554,
                    "plankton_samples": [
                        {"id": 25, "uid": "505584"}
                    ]
                },
            ]
        }]

        andes.parse_events(self.mission, self.test_file_name, samples)

        events = core_models.Event.objects.all()
        event = events.get(event_id=10)
        self.assertIsNotNone(event)
        self.assertEqual(station, event.station)
        self.assertEqual(ctd_instrument, event.instrument)
        self.assertEqual(3312, event.wire_out)
        self.assertEqual(505561, event.sample_id)
        self.assertEqual(505584, event.end_sample_id)

        event = events.get(event_id=11)
        self.assertIsNotNone(event)
        self.assertEqual(station, event.station)
        self.assertEqual(net_instrument, event.instrument)
        self.assertEqual(1000, event.wire_out)
        self.assertEqual(45, event.wire_angle)
        self.assertEqual(2068, event.flow_start)
        self.assertEqual(2554, event.flow_end)
        self.assertEqual(505584, event.sample_id)

    @tag('andes_parser_test_andeis_parser_actions')
    def test_andeis_parser_actions(self):
        instrument = core_factory.CTDInstrumentFactory(name='CTD AZOMP 2024')
        station = core_factory.StationFactory(name='AR7W_13')
        event = core_factory.CTDEventFactoryBlank(mission=self.mission, event_id=10,
                                                  instrument=instrument, station=station)
        expected_actions = [
            {
                "id": 67,
                "action_type": "Deploy",
                "latitude": 56.111916666666666,
                "longitude": -53.1224,
                "created_at": "2024-05-29 23:00:13.876404+00:00",
                "created_by": "chris"
            },
            {
                "id": 68,
                "action_type": "Bottom",
                "latitude": 56.11613333333333,
                "longitude": -53.13786666666667,
                "created_at": "2024-05-30 00:11:00.167013+00:00",
                "created_by": "chris"
            },
            {
                "id": 70,
                "action_type": "Recovery",
                "latitude": 56.125566666666664,
                "longitude": -53.18175,
                "created_at": "2024-05-30 02:09:29.361907+00:00",
                "created_by": "chris"
            }
        ]
        expected_operator = "Chris Gordon"
        expected_comment = "- HPU motor reset on descent at 500m. Paused and resumed without issue. \r\n- Bottle 18 misfire.\r\n- Spigot on bottle 21 broke allowing air into bottle. Did not sample gases / TIC / pH from this bottle. \r\n- Winds 35+ did not perform second net"
        expected_sounding = 3321.0
        samples = [{
            "station": "AR7W_13",
            "sounding": "3321.0 m",
            "comment": expected_comment,
            "operator": expected_operator,
            "events": [
                {
                    "id": 30,
                    "event_number": 10.0,
                    "instrument": "CTD AZOMP 2024",
                    "actions": expected_actions
                }
            ]
        }]

        andes.parse_actions(self.mission, self.test_file_name, samples)

        actions = event.actions.all()
        self.assertEqual(3, actions.count())

        deployed = actions.get(type=core_models.ActionType.deployed)
        self.assertEqual(datetime.strptime(expected_actions[0]['created_at'], '%Y-%m-%d %H:%M:%S.%f%z'),
                         deployed.date_time)
        self.assertEqual(np.around(expected_actions[0]['latitude'], 6), float(deployed.latitude))
        self.assertEqual(np.around(expected_actions[0]['longitude'], 6), float(deployed.longitude))
        self.assertEqual(expected_operator, deployed.data_collector)
        self.assertEqual(expected_comment, deployed.comment)
        self.assertEqual(expected_sounding, deployed.sounding)
        self.assertEqual(self.test_file_name, deployed.file)


@tag('parsers', 'event_parsers', 'csv_parser')
class TestCSVParser(DartTestCase):
    test_file_name = "LAT2025146_DART_Input.csv"
    test_file_location = os.path.join(settings.BASE_DIR, 'core', 'tests', 'sample_data')
    test_file = os.path.join(test_file_location, test_file_name)

    def setUp(self):
        andes.logger = logger
        self.mission = core_factory.MissionFactory(
            name='LAT2025146',
            start_date=datetime.strptime("2024-04-25 00:00:01", '%Y-%m-%d %H:%M:%S'),
            end_date=datetime.strptime("2024-05-27 23:59:59", '%Y-%m-%d %H:%M:%S')
        )

    def test_parse_csv_creates_objects(self):
        """Test that parsing a CSV file creates the expected objects"""
        csv_content = """event_id,station,instrument_name,instrument_type,starting_id,ending_id,flow_deploy,flow_recover,wire_out,wire_angle,ACTION,DATE_TIME,LATITUDE,LONGITUDE,SOUNDING,COMMENT,DATA_COLLECTOR
   1,TEST1,SBE911,CTD,1,24,,,100,2,DEPLOYED,2024-05-01 10:15:30,44.25678,-63.45678,150.5,CTD deployed successfully,John Smith
   1,TEST1,SBE911,CTD,1,24,,,100,2,BOTTOM,2024-05-01 10:30:45,44.25680,-63.45682,150.8,At bottom,John Smith
   1,TEST1,SBE911,CTD,1,24,,,100,2,RECOVERED,2024-05-01 10:45:20,44.25683,-63.45685,151.0,All samples collected,John Smith
   2,TEST2,Bongo,NET,25,48,225,522,150,3,DEPLOYED,2024-05-01 12:10:15,44.36789,-63.56789,200.3,Net deployed,Jane Doe
   2,TEST2,Bongo,NET,25,48,225,522,150,3,RECOVERED,2024-05-01 12:45:30,44.36795,-63.56795,201.1,Recovery complete,Jane Doe
   """
        stream = io.StringIO(csv_content)
        event_csv.parse(self.mission, self.test_file_name, stream)

        # Verify objects were created
        self.assertEqual(core_models.Event.objects.count(), 2)
        self.assertEqual(core_models.Station.objects.count(), 2)
        self.assertEqual(core_models.Instrument.objects.count(), 2)

        # Verify first event details
        event1 = core_models.Event.objects.get(event_id=1)
        self.assertEqual(event1.station.name, "TEST1")
        self.assertEqual(event1.instrument.name, "SBE911")
        self.assertEqual(event1.instrument.type, core_models.InstrumentType.ctd)
        self.assertEqual(event1.sample_id, 1)
        self.assertEqual(event1.end_sample_id, 24)

        event2 = core_models.Event.objects.get(event_id=2)
        self.assertEqual(event2.flow_start, 225)
        self.assertEqual(event2.flow_end, 522)
        self.assertEqual(event2.wire_out, 150)
        self.assertEqual(event2.wire_angle, 3)

    @tag('csv_parser_test_process_stations')
    def test_process_stations(self):
        """Test that process_stations creates stations that don't exist and handles case insensitivity correctly"""
        # List of station names with some variations in case
        stations = ['STATION1', 'station2', 'Station2', 'STATION3']

        # Make sure the stations don't exist initially in both models
        for station in stations:
            self.assertFalse(core_models.Station.objects.filter(name__iexact=station).exists())
            self.assertFalse(settings_models.GlobalStation.objects.filter(name__iexact=station).exists())

        # Process the stations
        event_csv.process_stations(stations)

        # Check that all stations exist now in both models
        self.assertTrue(core_models.Station.objects.filter(name__iexact='STATION1').exists())
        self.assertTrue(core_models.Station.objects.filter(name__iexact='station2').exists())
        self.assertTrue(core_models.Station.objects.filter(name__iexact='STATION3').exists())

        # Check stations were added to GlobalStation model too
        self.assertTrue(settings_models.GlobalStation.objects.filter(name__iexact='STATION1').exists())
        self.assertTrue(settings_models.GlobalStation.objects.filter(name__iexact='station2').exists())
        self.assertTrue(settings_models.GlobalStation.objects.filter(name__iexact='STATION3').exists())

        # Check that 'station2' and 'Station2' were treated as the same station (case insensitive)
        # Only one station should exist with this name (case-insensitive) in both models
        self.assertEqual(core_models.Station.objects.filter(name__iexact='station2').count(), 1)
        self.assertEqual(settings_models.GlobalStation.objects.filter(name__iexact='station2').count(), 1)


    @tag('csv_parser_test_process_instruments')
    def test_process_instruments(self):
        """Test that process_instruments creates instruments correctly based on their names and types."""
        # List of instrument names with different cases
        instruments = [('Blue Molly', 'CTD'), ('Ring Net', 'net'), ('MultiNet', 'MultiNet'), ('Argo', 'other_instrument')]

        # Make sure the instruments don't exist initially
        for name, type in instruments:
            self.assertFalse(core_models.Instrument.objects.filter(name=name).exists())

        # Process the instruments
        event_csv.process_instruments(instruments)

        # Check that CTD is created with the correct type
        ctd = core_models.Instrument.objects.get(name='Blue Molly')
        self.assertEqual(ctd.type, core_models.InstrumentType.ctd)

        # Check that net is created with the correct type (and uppercase)
        net = core_models.Instrument.objects.get(name='Ring Net')
        self.assertEqual(net.type, core_models.InstrumentType.net)

        # Check that MultiNet is created with the correct type (and uppercase)
        multinet = core_models.Instrument.objects.get(name='MultiNet')
        self.assertEqual(multinet.type, core_models.InstrumentType.net)

        # Check that other instruments are created with the 'other' type
        other = core_models.Instrument.objects.get(name='Argo')
        self.assertEqual(other.type, core_models.InstrumentType.other)

        # Check total number of instruments created (should be 4)
        self.assertEqual(core_models.Instrument.objects.count(), 4)

        # Process the instruments again (with different case)
        event_csv.process_instruments([('Blue molly', 'ctd'), ('Ring net', 'NET')])

        # Check that no new instruments were created (get_or_create should find existing ones)
        self.assertEqual(core_models.Instrument.objects.count(), 4)