import datetime
import time
import os
import shutil

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.test import tag
from django.urls import reverse

import core.models
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

fake_db_location = r'./test_db'
biochem_db = 'biochem'
default_db = 'default'
fake_mission = 'TM15502'

oxy_seq = 90000203
salt_seq = 90000105


def delete_model(database_name: str, model):
    with connections[database_name].schema_editor() as editor:
        editor.delete_model(model)


class AbstractTestDatabase(DartTestCase):
    @classmethod
    def setUpClass(cls):
        databases = settings.DATABASES
        databases[biochem_db] = databases['default'].copy()
        databases[biochem_db]['NAME'] = 'file:memorydb_biochem?mode=memory&cache=shared'

        utils.load_biochem_fixtures(default_db)

    @classmethod
    def tearDownClass(cls):
        pass


@tag('biochem', 'biochem_plankton')
class TestGetBCSPRows(AbstractTestDatabase):

    def setUp(self):
        self.mission = core_factory.MissionFactory(mission_descriptor="test_db")

        self.bio_model = upload.get_bcs_p_model(self.mission.get_biochem_table_name)
        upload.create_model(biochem_db, self.bio_model)

    def tearDown(self):
        delete_db = True
        if delete_db:
            delete_model(biochem_db, self.bio_model)

    def test_get_bcs_p_rows(self):
        core_factory.BottleFactory.start_bottle_seq = 400000
        bottle = core_factory.BottleFactory(event=core_factory.NetEventFactory(mission=self.mission))
        core_factory.PhytoplanktonSampleFactory.create_batch(
            10, bottle=bottle, gear_type_id=90000102
        )

        bottles = core_models.Bottle.objects.all()
        bcs_model = self.bio_model

        create_rows, update_rows, update_fields = upload.get_bcs_p_rows("test_user", bottles,
                                                                        self.mission.get_batch_name,
                                                                        bcs_model)

        self.assertEquals(len(create_rows), 1)
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


@tag('biochem', 'fake_biochem_upload')
class TestFakeBioChemDBUpload(AbstractTestDatabase):

    def setUp(self):
        self.mission = core_factory.MissionFactory(mission_descriptor="test_db")

    def test_data_marked_for_upload(self):
        # provided a mission with data marked for Biochem upload the data should be pushed to the BioChem tables
        core_factory.BottleFactory.start_bottle_seq = 400000
        bottles = core_factory.BottleFactory.create_batch(10, event=core_factory.CTDEventFactory(mission=self.mission))

        oxygen_datatype = bio_tables_models.BCDataType.objects.get(data_type_seq=oxy_seq)
        oxy_sample_type = core_factory.MissionSampleTypeFactory(mission=self.mission, datatype=oxygen_datatype)

        salt_datatype = bio_tables_models.BCDataType.objects.get(data_type_seq=salt_seq)
        sal_sample_type = core_factory.MissionSampleTypeFactory(mission=self.mission, datatype=salt_datatype)

        for bottle in bottles:
            oxy_sample = core_factory.SampleFactory(bottle=bottle, type=oxy_sample_type)
            core_factory.DiscreteValueFactory(sample=oxy_sample, value=3.9)

            oxy_sample = core_factory.SampleFactory(bottle=bottle, type=sal_sample_type)
            core_factory.DiscreteValueFactory(sample=oxy_sample, value=3.9)

        core_models.BioChemUpload.objects.using(default_db).create(
            status=core_models.BioChemUploadStatus.upload,
            type=oxy_sample_type
        )

        form_biochem_database.upload_bcd_d_data(self.mission, 'upsonp')

        model = upload.get_bcd_d_model(self.mission.get_biochem_table_name)
        # oxygen samples should have been added to the biochem db
        self.assertTrue(model.objects.using(biochem_db).filter(dis_detail_data_type_seq=oxy_seq))

        # salt samples should not have been added to the biochem db
        self.assertFalse(model.objects.using(biochem_db).filter(dis_detail_data_type_seq=salt_seq))

        # When uploaded the BioChemUpload entry should be marked as 'uploaded' and the uploaded date
        # should be set
        oxy_upload = core_models.BioChemUpload.objects.using(default_db).get(type=oxy_sample_type)
        self.assertEquals(core_models.BioChemUploadStatus.uploaded, oxy_upload.status)
        self.assertTrue(oxy_upload.upload_date < oxy_upload.modified_date)


@tag('biochem', 'fake_biochem_delete_update')
class TestFakeBioChemDBDeleteUpdate(AbstractTestDatabase):
    database_bcd_table_name = "tm15502"

    def setUp(self):
        # I know it's a complicated setup, but to test BioChem deletion and updating existing samples
        # we need to load a fake Biochem database with data and it has to sync with data that Dart will
        # supposedly have.
        #
        # The Biochem Database connection is created by the AbstractTestDatabase class

        # create a mission so we'll have a database table name and batch sequence
        self.mission = core_factory.MissionFactory(mission_descriptor="TM15502",
                                                   biochem_table=self.database_bcd_table_name)

        # Setup factoryboy to use the model we linked to the in-memory biochem db BCD table
        bcd_factory = biochem_factory.BcdDFactory

        self.model = upload.get_bcd_d_model(self.database_bcd_table_name)
        upload.create_model(biochem_db, self.model)
        bcd_factory._meta.model = self.model

        # create some Oxygen sensor values for the Mission (self.mission)
        self.oxy_data_type = bio_tables_models.BCDataType.objects.get(data_type_seq=oxy_seq)
        self.oxy_sample_type = core_factory.MissionSampleTypeFactory(mission=self.mission, datatype=self.oxy_data_type)

        # bottles are attached to an event
        event = core_factory.CTDEventFactory(mission=self.mission)
        bottles = core_factory.BottleFactory.create_batch(10, event=event)

        # create the rows in the biochem in-memory DB and add the sensor values to the bottles for the mission db
        for index, bottle in enumerate(bottles):
            sample = core_factory.SampleFactory(bottle=bottle, type=self.oxy_sample_type)
            core_factory.DiscreteValueFactory(sample=sample, value=3.9)
            bcd_factory.create(dis_detail_data_type_seq=oxy_seq, data_type_method='O2_Winkler_Auto',
                               dis_detail_collector_samp_id=bottle.bottle_id, batch_seq=self.mission.get_batch_name)
            if index == 0:
                # we need to make sure there's at least one replicate.
                sample = core_factory.SampleFactory(bottle=bottle, type=self.oxy_sample_type)
                core_factory.DiscreteValueFactory(sample=sample, value=3.9, replicate=2)
                bcd_factory.create(dis_detail_data_type_seq=oxy_seq, data_type_method='O2_Winkler_Auto',
                                   dis_detail_collector_samp_id=bottle.bottle_id, batch_seq=self.mission.get_batch_name)

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
            delete_model(biochem_db, self.model)

    def test_db_creation(self):
        # This is just to test that the biochem DB was created and data added to the specified
        # model to establish a baseline for further testing.
        logger.info("Print Data:")
        db_data = self.model.objects.using(biochem_db).order_by('dis_data_num')

        self.assertEquals(31, db_data.count())
        for d in db_data:
            logger.info(d)

    def test_delete_bcupload(self):
        # given a mission sample type, if a BioChemUpload entry exists where the sample
        # type is marked as delete entries should be removed from the biochem DB
        sample_type = core_models.MissionSampleType.objects.using(default_db).create(
            mission=self.mission,
            name="oxygen",
            datatype=self.oxy_data_type
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

    def test_update_existing(self):
        # given the mission DB has some existing rows that also exist in the biochem DB
        # if we mark the self.oxy_sample_type as 'update' in the BioChemUpload table
        # the upload.get_bcd_d_rows() function should return zero rows to create and 10 rows to update

        # have to mark the self.oxy_sample_type in the BioChemUpload table
        core.models.BioChemUpload.objects.using(default_db).create(type=self.oxy_sample_type,
                                                                   status=core_models.BioChemUploadStatus.upload)
        samples = core_models.DiscreteSampleValue.objects.using(default_db).filter(sample__type=self.oxy_sample_type)
        create_rows, update_rows, fields = upload.get_bcd_d_rows(default_db,
                                                                 uploader='upsonp',
                                                                 samples=samples,
                                                                 batch_name=self.mission.get_batch_name,
                                                                 bcd_d_model=self.model)

        self.assertEquals(0, len(create_rows))
        self.assertEquals(core_models.DiscreteSampleValue.objects.using(default_db).filter(
            sample__type=self.oxy_sample_type).count(), len(update_rows))
