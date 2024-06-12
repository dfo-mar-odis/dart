import logging
import os

import numpy as np

from datetime import datetime
from io import StringIO

from django.conf import settings
from django.test import tag

from core.tests import CoreFactoryFloor as core_factory
from dart.tests.DartTestCase import DartTestCase
from core.parsers import andes
from core import models as core_models

logger = logging.getLogger(f'dart.debug.{__name__}')


@tag('parsers', 'andes_parser')
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
            stream = StringIO(f.read())
            andes.parse(self.mission, self.test_file_name, stream)

        instruments = core_models.Instrument.objects.all()
        self.assertEquals(5, instruments.count())  # the test file has 5 instruments in it

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
        self.assertEquals(core_models.InstrumentType.ctd, ctd.type)

        self.assertIsNotNone(mission_instruments.get(name__iexact='Plankton net (202um)'))
        net = mission_instruments.get(name__iexact='Plankton net (202um)')
        self.assertEquals(core_models.InstrumentType.net, net.type)

        self.assertIsNotNone(mission_instruments.get(name__iexact='Plankton net (76um)'))
        net = mission_instruments.get(name__iexact='Plankton net (76um)')
        self.assertEquals(core_models.InstrumentType.net, net.type)

        self.assertIsNotNone(mission_instruments.get(name__iexact='Argo (BIO AZOMP)'))
        beacon = mission_instruments.get(name__iexact='Argo (BIO AZOMP)')
        self.assertEquals(core_models.InstrumentType.other, beacon.type)

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
        self.assertEquals(len(samples), stations.count())
        station = stations.get(name__iexact='AR7W_13')
        self.assertIsNotNone(station)

    @tag('andes_parser_test_andeis_parser_events')
    def test_andeis_parser_events(self):
        station = core_factory.StationFactory(name='AR7W_13')
        ctd_instrument = core_factory.CTDInstrumentFactory(name='CTD AZOMP 2024')
        net_instrument = core_factory.InstrumentFactory(name='Plankton net (202μm)', type=core_models.InstrumentType.net)
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
        self.assertEquals(station, event.station)
        self.assertEquals(ctd_instrument, event.instrument)
        self.assertEquals(3312, event.wire_out)
        self.assertEquals(505561, event.sample_id)
        self.assertEquals(505584, event.end_sample_id)

        event = events.get(event_id=11)
        self.assertIsNotNone(event)
        self.assertEquals(station, event.station)
        self.assertEquals(net_instrument, event.instrument)
        self.assertEquals(1000, event.wire_out)
        self.assertEquals(45, event.wire_angle)
        self.assertEquals(2068, event.flow_start)
        self.assertEquals(2554, event.flow_end)
        self.assertEquals(505584, event.sample_id)

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
        self.assertEquals(3, actions.count())

        deployed = actions.get(type=core_models.ActionType.deployed)
        self.assertEquals(datetime.strptime(expected_actions[0]['created_at'], '%Y-%m-%d %H:%M:%S.%f%z'),
                          deployed.date_time)
        self.assertEquals(np.around(expected_actions[0]['latitude'], 6), float(deployed.latitude))
        self.assertEquals(np.around(expected_actions[0]['longitude'], 6), float(deployed.longitude))
        self.assertEquals(expected_operator, deployed.data_collector)
        self.assertEquals(expected_comment, deployed.comment)
        self.assertEquals(expected_sounding, deployed.sounding)
        self.assertEquals(self.test_file_name, deployed.file)
