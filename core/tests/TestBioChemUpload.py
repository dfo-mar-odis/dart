import datetime
import time
import os
import shutil

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.test import tag
from django.urls import reverse

from dart.tests.DartTestCase import DartTestCase

from core import models as core_models
from core import form_biochem_database
from core.tests import CoreFactoryFloor as core_factory

from biochem import upload
from biochem import models as bio_models
from biochem.tests import BCFactoryFloor as biochem_factory

from bio_tables import models as bio_tables_models

import logging

from settingsdb import utils

logger = logging.getLogger(f'dart.{__name__}')


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


fake_db_location = r'./test_db'
biochem_db = 'biochem'
default_db = 'default'
fake_mission = 'TM15502'

oxy_seq = 90000203
salt_seq = 90000105


@tag('biochem', 'fake_biochem')
class TestFakeBioChemDB(DartTestCase):
    database_bcd_table_name = "tm15502"

    @classmethod
    def setUpClass(cls):

        call_command('migrate', database=default_db, app_label="core")
        utils.load_biochem_fixtures(default_db)

    @classmethod
    def tearDownClass(cls):
        # The in-memory 'default' database will disappear when the test class is done with it.
        pass

    def setUp(self):
        if not os.path.exists(fake_db_location):
            os.makedirs(fake_db_location)

        databases = settings.DATABASES
        databases[biochem_db] = databases['default'].copy()
        databases[biochem_db]['NAME'] = 'file:memorydb_biochem?mode=memory&cache=shared'

        self.mission = core_factory.MissionFactory(mission_descriptor="TM15502",
                                                   biochem_table=self.database_bcd_table_name)
        bcd_factory = biochem_factory.BcdDFactory
        self.model = upload.get_bcd_d_model(self.database_bcd_table_name)
        upload.create_model('biochem', self.model)

        bcd_factory._meta.model = self.model
        bcd_factory.create_batch(10,
                                dis_detail_data_type_seq=oxy_seq,
                                data_type_method='O2_Winkler_Auto',
                                batch_seq=self.mission.get_batch_name)
        bcd_factory.create_batch(10,
                                dis_detail_data_type_seq=oxy_seq,
                                data_type_method='O2_Winkler_Auto',
                                batch_seq=2)  # simulate data created from another source
        bcd_factory.create_batch(10,
                                dis_detail_data_type_seq=salt_seq,
                                data_type_method='Salinity_Sal_PSS',
                                batch_seq=self.mission.get_batch_name)

    def tearDown(self):
        delete_db = True
        if delete_db:
            self.delete_model('biochem', self.model)

    def delete_model(self, database_name: str, model):
        with connections[database_name].schema_editor() as editor:
            editor.delete_model(model)

    def test_db_creation(self):
        # This is just to test that the biochem DB was created and data added to the specified
        # model to establish a baseline for further testing.
        logger.info("Print Data:")
        db_data = self.model.objects.using(biochem_db).order_by('dis_data_num')

        self.assertEquals(30, db_data.count())
        for d in db_data:
            logger.info(d)

    def test_delete_bcupload(self):
        # given a mission sample type, if a BioChemUpload entry exists where the sample
        # type is marked as delete entries should be removed from the biochem DB
        bc_oxy = bio_tables_models.BCDataType.objects.using(default_db).get(data_type_seq=oxy_seq)
        sample_type = core_models.MissionSampleType.objects.using(default_db).create(
            mission=self.mission,
            name="oxygen",
            datatype=bc_oxy
        )
        core_models.BioChemUpload.objects.using(default_db).create(
            status=core_models.BioChemUploadStatus.delete,
            type=sample_type
        )

        self.assertTrue(self.model.objects.using(biochem_db).filter(
            dis_detail_data_type_seq=oxy_seq, batch_seq=self.mission.get_batch_name).exists())

        form_biochem_database.remove_bcd_d_data(self.mission)

        # Oxygen should be deleted
        self.assertFalse(self.model.objects.using(biochem_db).filter(
            dis_detail_data_type_seq=oxy_seq, batch_seq=self.mission.get_batch_name).exists())

        # Salt should not be deleted
        self.assertTrue(self.model.objects.using(biochem_db).filter(
            dis_detail_data_type_seq=salt_seq, batch_seq=self.mission.get_batch_name).exists())

        # Oxygen from batch 2 should not be deleted
        self.assertTrue(self.model.objects.using(biochem_db).filter(
            dis_detail_data_type_seq=oxy_seq, batch_seq=2).exists())
