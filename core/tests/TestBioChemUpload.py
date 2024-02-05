import factory
from django.conf import settings
from django.db.models import QuerySet
from django.test import tag

from dart2.tests.DartTestCase import DartTestCase

from core.tests import CoreFactoryFloor as core_factory
from core import models as core_models

from biochem import upload
from biochem import models as bio_models

import logging

logger = logging.getLogger("dart.test")


class MockObjects:

    def all(self):
        return []


class MockBCSP(bio_models.BcsP):

    def __init__(self, *args, **kwargs):
        self.objects = MockObjects()
        super().__init__(*args, **kwargs)


@tag('biochem', 'biochem_plankton')
class TestGetBCSPRows(DartTestCase):

    def test_get_bcs_p_rows(self):
        core_factory.BottleFactory.start_bottle_seq = 400000
        mission = core_factory.MissionFactory(mission_descriptor="test_db")
        trip = core_factory.TripFactory(mission=mission)
        bottle = core_factory.BottleFactory(event=core_factory.NetEventFactory(trip=trip))
        core_factory.PhytoplanktonSampleFactory.create_batch(
            10, bottle=bottle, gear_type_id=90000102
        )

        bottles = core_models.Bottle.objects.all()
        bcs_model = MockBCSP()
        creat_rows, update_rows, update_fields = upload.get_bcs_p_rows("test_user", bottles, bcs_model)

        self.assertEquals(len(creat_rows), 1)
        self.assertEquals(len(update_rows), 0)
        self.assertEquals(len(update_fields), 0)


