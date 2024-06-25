from datetime import datetime

from dart.tests.DartTestCase import DartTestCase
from django.test import tag

from core.models import ActionType as action_types
from core.validation import validate_event, validate_ctd_event, validate_net_event

from . import CoreFactoryFloor as core_factory

import logging

logger = logging.getLogger('dart.test')


@tag('validation', 'validation_general')
class TestGeneralEventValidation(DartTestCase):
    def setUp(self) -> None:
        self.start_date = datetime.strptime("2020-01-01 14:30:00", '%Y-%m-%d %H:%M:%S')
        self.end_date = datetime.strptime("2020-02-01 14:30:00", '%Y-%m-%d %H:%M:%S')
        self.mission = core_factory.MissionFactory(
            start_date=self.start_date.date(),
            end_date=self.end_date.date()
        )

    def test_validate_actions(self):
        # Events may not contain actions of the same type, this test has an event with two bottom actions
        # unless the action type is 'other'

        event = core_factory.CTDEventFactory(mission=self.mission, sample_id=501100, end_sample_id=501112)
        # events from the CTDEventFactory come with their own actions because a CTD event isn't valid without actions
        event.actions.all().delete()

        expected_file = 'test.log'
        core_factory.ActionFactory(event=event, mid=1, type=action_types.deployed, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=2, type=action_types.bottom, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=3, type=action_types.bottom, file=expected_file,
                                   date_time=self.start_date)

        errors = validate_event(event)
        logger.debug(errors)
        self.assertEquals(len(errors), 1)

    def test_validate_actions_other(self):
        # Events may not contain actions of the same type, this test has an event with two bottom actions
        # unless the action type is 'other'

        event = core_factory.CTDEventFactory(mission=self.mission, sample_id=501100, end_sample_id=501112)
        # events from the CTDEventFactory come with their own actions because a CTD event isn't valid without actions
        event.actions.all().delete()

        expected_file = 'test.log'
        core_factory.ActionFactory(event=event, mid=1, type=action_types.other, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=2, type=action_types.other, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=3, type=action_types.bottom, file=expected_file,
                                   date_time=self.start_date)

        errors = validate_event(event)
        logger.debug(errors)
        self.assertEquals(len(errors), 0)

    def test_valid_location(self):
        # events must have a valid start location, the start location is determined by an action, but actions
        # are allowed to have blank lat/lon so during the validation we should check that the lat/lon is valid
        event = core_factory.CTDEventFactoryBlank(mission=self.mission, sample_id=1, end_sample_id=10)
        bad_action = core_factory.ActionFactory(event=event, latitude=None, longitude=None, type=action_types.bottom,
                                                date_time=datetime.strptime("2020-01-02 14:30:00", '%Y-%m-%d %H:%M:%S'))

        # start_location will return an array [lat, lon] if the action's lat/lon is blank the pair will be [None, None]
        self.assertIsNone(event.start_location[0])
        self.assertIsNone(event.start_location[1])

        errors = validate_event(event)
        logger.debug(errors)
        self.assertEquals(len(errors), 1)


@tag('validation', 'validation_ctd')
class TestCTDEventValidation(DartTestCase):

    def setUp(self) -> None:
        self.start_date = datetime.strptime("2020-01-01 14:30:00", '%Y-%m-%d %H:%M:%S')
        self.end_date = datetime.strptime("2020-02-01 14:30:00", '%Y-%m-%d %H:%M:%S')
        self.mission = core_factory.MissionFactory(
            start_date=self.start_date.date(),
            end_date=self.end_date.date()
        )

    def test_validation_sample_ids(self):
        event = core_factory.CTDEventFactory(mission=self.mission, sample_id=None, end_sample_id=None)

        # we're testing with the assumption the event was loaded from a log file so we need to create
        # the expected actions with their message object ids and files they came from
        expected_file = 'test.log'
        core_factory.ActionFactory(event=event, mid=1, type=action_types.deployed, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=2, type=action_types.bottom, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=3, type=action_types.recovered, file=expected_file,
                                   date_time=self.start_date)

        errors = validate_ctd_event(event)
        logger.debug(errors)
        self.assertEquals(len(errors), 2)

    def test_validation_end_sample_ids(self):
        event = core_factory.CTDEventFactory(mission=self.mission, sample_id=1000, end_sample_id=None)

        # we're testing with the assumption the event was loaded from a log file so we need to create
        # the expected actions with their message object ids and files they came from
        expected_file = 'test.log'
        core_factory.ActionFactory(event=event, mid=1, type=action_types.deployed, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=2, type=action_types.bottom, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=3, type=action_types.recovered, file=expected_file,
                                   date_time=self.start_date)

        errors = validate_ctd_event(event)
        logger.debug(errors)
        self.assertEquals(len(errors), 1)

    # Don't validate aborted events
    def test_aborted_validation_sample_ids(self):
        event = core_factory.CTDEventFactory(sample_id=None, end_sample_id=None)

        # we're testing with the assumption the event was loaded from a log file so we need to create
        # the expected actions with their message object ids and files they came from
        expected_file = 'test.log'
        core_factory.ActionFactory(event=event, mid=1, type=action_types.deployed, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=2, type=action_types.bottom, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=3, type=action_types.aborted, file=expected_file,
                                   date_time=self.start_date)

        errors = validate_ctd_event(event)
        logger.debug(errors)
        self.assertEquals(len(errors), 0)

    def test_validate_net_event_missing_sample_id(self):
        expected_file = 'test.log'

        core_factory.CTDEventFactory(mission=self.mission, sample_id=40000, end_sample_id=40012)
        event = core_factory.NetEventFactory(mission=self.mission, sample_id=None)
        core_factory.AttachmentFactory(event=event, name='76um')

        core_factory.ActionFactory(event=event, mid=1, type=action_types.deployed, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=2, type=action_types.bottom, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=3, type=action_types.recovered, file=expected_file,
                                   date_time=self.start_date)

        errors = validate_net_event(event)
        logger.debug(errors)
        self.assertTrue(errors)

    def test_validate_net_missing_attachment(self):
        expected_file = 'test.log'

        core_factory.CTDEventFactory(mission=self.mission, sample_id=40000, end_sample_id=40012)
        event = core_factory.NetEventFactory(mission=self.mission, sample_id=30000)

        core_factory.ActionFactory(event=event, mid=1, type=action_types.deployed, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=2, type=action_types.bottom, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=3, type=action_types.recovered, file=expected_file,
                                   date_time=self.start_date)

        errors = validate_net_event(event)
        logger.debug(errors)
        self.assertTrue(errors)

    def test_validate_net_76_event_no_ctd_match(self):
        expected_file = 'test.log'

        core_factory.CTDEventFactory(mission=self.mission, sample_id=40000, end_sample_id=40012)
        event = core_factory.NetEventFactory(mission=self.mission, sample_id=40011)
        core_factory.AttachmentFactory(event=event, name='76um')

        core_factory.ActionFactory(event=event, mid=1, type=action_types.deployed, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=2, type=action_types.bottom, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=3, type=action_types.recovered, file=expected_file,
                                   date_time=self.start_date)

        errors = validate_net_event(event)
        logger.debug(errors)
        self.assertTrue(errors)

    def test_validate_net_202_event_no_ctd_match(self):
        expected_file = 'test.log'

        core_factory.CTDEventFactory(mission=self.mission, sample_id=40000, end_sample_id=40012)
        event = core_factory.NetEventFactory(mission=self.mission, sample_id=40001)
        core_factory.AttachmentFactory(event=event, name='202um')

        core_factory.ActionFactory(event=event, mid=1, type=action_types.deployed, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=2, type=action_types.bottom, file=expected_file,
                                   date_time=self.start_date)
        core_factory.ActionFactory(event=event, mid=3, type=action_types.recovered, file=expected_file,
                                   date_time=self.start_date)

        errors = validate_net_event(event)
        logger.debug(errors)
        self.assertTrue(errors)
