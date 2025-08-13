import os
from io import StringIO

from core.tests import CoreFactoryFloor

from django.test import TestCase, tag
from core.parsers.sensor.qat import QATParser

sample_file_path = ['core', 'tests', 'sample_data']
sample_file_name = '25002102_Fake.QAT'
sample_file = os.path.join(*sample_file_path, sample_file_name)


@tag('qat_parser')
class TestQATParser(TestCase):

    def setUp(self):
        self.mission = CoreFactoryFloor.MissionFactory.create(name='QATMission')

    def test_init(self):
        file_data = None
        with open(sample_file, 'r') as file:
            file_data = StringIO(file.read())

        QatParser = QATParser(self.mission, sample_file_name, file_data)