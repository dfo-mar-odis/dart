from django.test import tag

from core import models, utils

from dart2.tests.DartTestCase import DartTestCase
from . import CoreFactoryFloor as core_factory


@tag('utils', 'utils_elog_upload')
class TestElogUpload(DartTestCase):

    def test_elog_uplaod(self):
        mission = core_factory.MissionFactory(name="TestMission")
