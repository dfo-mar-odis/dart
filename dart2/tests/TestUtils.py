import pandas as pd
import io

from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.test import tag

import core.tests.CoreFactoryFloor
from .DartTestCase import DartTestCase

from dart2 import utils
from core import models as core_models

import logging

logger = logging.getLogger('dart.test')


class TestUtils(DartTestCase):

    def test_load_svg(self):
        icon = utils.load_svg('bell')

        self.assertIsNotNone(icon)


@tag('test_parser')
class TestSampleCSVParser(DartTestCase):

    def test_parser(self):
        upload_file = open('dart2/tests/sample_data/JC24301_oxy.csv', 'rb')
        file = SimpleUploadedFile(upload_file.name, upload_file.read())

        file_data = file.read().decode('utf-8')
        skip_lines = 9
        sample_column = 0
        value_column = 2
        mission = core.tests.CoreFactoryFloor.MissionFactory()
        oxy_sample_type = core.tests.CoreFactoryFloor.OxygenSampleTypeFactory()
        core.tests.CoreFactoryFloor.BottleFactory.start_bottle_seq = 495271
        ctd_event = core.tests.CoreFactoryFloor.CTDEventFactory(mission=mission)
        bottles = core.tests.CoreFactoryFloor.BottleFactory.create_batch(2000, event=ctd_event)

        stream = io.StringIO(file_data)
        df = pd.read_csv(filepath_or_buffer=stream, header=skip_lines)
        utils.parse_csv_sample_file(mission, oxy_sample_type, df, sample_column, value_column)

        pass
