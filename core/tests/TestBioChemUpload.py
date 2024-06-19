import datetime

from django.test import tag
from django.urls import reverse

from dart.tests.DartTestCase import DartTestCase

from core.tests import CoreFactoryFloor as core_factory
from core import models as core_models

from biochem import upload
from biochem import models as bio_models

import logging

logger = logging.getLogger("dart.test")


class MockObjects:

    def using(self, database):
        return self

    def all(self):
        return []

    def filter(self, *args, **kwargs):
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
        bottle = core_factory.BottleFactory(event=core_factory.NetEventFactory(mission=mission))
        core_factory.PhytoplanktonSampleFactory.create_batch(
            10, bottle=bottle, gear_type_id=90000102
        )

        bottles = core_models.Bottle.objects.all()
        bcs_model = MockBCSP()

        creat_rows, update_rows, update_fields = upload.get_bcs_p_rows("test_user", bottles, mission.get_batch_name,
                                                                       bcs_model)

        self.assertEquals(len(creat_rows), 1)
        self.assertEquals(len(update_rows), 0)
        self.assertEquals(len(update_fields), 0)


@tag('biochem', 'biochem_upload')
class TestBioChemUpload(DartTestCase):

    checkbox_url = 'core:mission_samples_add_sensor_to_upload'

    def setUp(self):
        pass

    def test_add_mission_data_type(self):
        # calling the checkbox url with a database, mission ID, and sensor_id should add the sensor/sample
        # to the BioChemUpload table with a modified date of 'now' and the status set to
        # 'BiochemUploadStatus.upload'
        sensor_id = 1
        self.mission = core_factory.MissionFactory(mission_descriptor="test_db")
        self.mission_sample_type = core_factory.MissionSampleTypeFactory(mission=self.mission)

        url = reverse(self.checkbox_url, args=('default', self.mission.pk, self.mission_sample_type.pk,))

        response = self.client.post(url, {'add_sensor': 'true'})

        bcu = core_models.BioChemUpload.objects.using('default').filter(type_id=sensor_id)
        self.assertTrue(bcu.exists())

        bcu_entry = bcu.first()
        self.assertIsNotNone(bcu_entry.modified_date)
        logger.debug(bcu_entry.modified_date)

        self.assertEquals(core_models.BioChemUploadStatus.upload, bcu_entry.status)

    def test_remove_non_uploaded_mission_data_type(self):
        # calling the checkbox url with a database, mission ID, and sensor_id should remove the sensor/sample
        # from the BioChemUpload table if the no upload_date is set and the status is 'BiochemUploadStatus.upload'
        sensor_id = 1
        self.mission = core_factory.MissionFactory(mission_descriptor="test_db")
        self.mission_sample_type = core_factory.MissionSampleTypeFactory(mission=self.mission)
        core_models.BioChemUpload.objects.using('default').create(type_id=self.mission_sample_type.pk,
                                                                  status=core_models.BioChemUploadStatus.upload)

        url = reverse(self.checkbox_url, args=('default', self.mission.pk, self.mission_sample_type.pk,))

        response = self.client.post(url)

        bcu = core_models.BioChemUpload.objects.using('default').filter(type_id=sensor_id)
        self.assertFalse(bcu.exists())

    def test_remove_uploaded_mission_data_type(self):
        # calling the checkbox url with a database, mission ID, and sensor_id should mark the sensor/sample
        # in the BioChemUpload table as 'BiochemUploadStatus.delete' if the status is 'BiochemUploadStatus.uploaded'
        sensor_id = 1
        self.mission = core_factory.MissionFactory(mission_descriptor="test_db")
        self.mission_sample_type = core_factory.MissionSampleTypeFactory(mission=self.mission)
        upload_date = datetime.datetime.strptime("2024-06-19 2:23:00+00:00", "%Y-%m-%d %H:%M:%S%z")
        core_models.BioChemUpload.objects.using('default').create(type_id=self.mission_sample_type.pk,
                                                                  status=core_models.BioChemUploadStatus.uploaded,
                                                                  upload_date=upload_date)

        url = reverse(self.checkbox_url, args=('default', self.mission.pk, self.mission_sample_type.pk,))

        response = self.client.post(url)

        bcu = core_models.BioChemUpload.objects.using('default').filter(type_id=sensor_id)
        self.assertTrue(bcu.exists())

        self.assertEquals(core_models.BioChemUploadStatus.delete, bcu.first().status)

    def test_remove_upload_with_date_mission_data_type(self):
        # calling the checkbox url with a database, mission ID, and sensor_id should mark the sensor/sample
        # in the BioChemUpload table as 'BiochemUploadStatus.delete' if the status is 'BiochemUploadStatus.uploaded'
        sensor_id = 1
        self.mission = core_factory.MissionFactory(mission_descriptor="test_db")
        self.mission_sample_type = core_factory.MissionSampleTypeFactory(mission=self.mission)
        upload_date = datetime.datetime.strptime("2024-06-19 2:23:00+00:00", "%Y-%m-%d %H:%M:%S%z")
        core_models.BioChemUpload.objects.using('default').create(type_id=self.mission_sample_type.pk,
                                                                  status=core_models.BioChemUploadStatus.upload,
                                                                  upload_date=upload_date)

        url = reverse(self.checkbox_url, args=('default', self.mission.pk, self.mission_sample_type.pk,))

        response = self.client.post(url)

        bcu = core_models.BioChemUpload.objects.using('default').filter(type_id=sensor_id)
        self.assertTrue(bcu.exists())

        self.assertEquals(core_models.BioChemUploadStatus.delete, bcu.first().status)