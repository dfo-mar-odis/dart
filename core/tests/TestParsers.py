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

    def test_validate_message_object(self):
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
            self.assertIsInstance(mid_dictionary[elog.ParserType.ERRORS]['1'][i], ValueError)
            logger.info(f"Error {i}: {mid_dictionary[elog.ParserType.ERRORS]['1'][i]}")

        # There should be ValueErrors in the array for message object 1 describing what keys are missing
        for i in range(0, len(mid_dictionary[elog.ParserType.ERRORS]['2'])):
            self.assertIsInstance(mid_dictionary[elog.ParserType.ERRORS]['2'][i], ValueError)
            logger.info(f"Error {i}: {mid_dictionary[elog.ParserType.ERRORS]['2'][i]}")

        # There should be ValueErrors in the array for message object 1 describing what keys are missing
        for i in range(0, len(mid_dictionary[elog.ParserType.ERRORS]['3'])):
            self.assertIsInstance(mid_dictionary[elog.ParserType.ERRORS]['3'][i], ValueError)
            logger.info(f"Error {i}: {mid_dictionary[elog.ParserType.ERRORS]['3'][i]}")

        sample_file_pointer.close()

