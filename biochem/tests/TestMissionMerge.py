import datetime

from django.test import TestCase, tag
from django.conf import settings

from biochem.tests import BCFactoryFloor
from biochem import MergeTables
from biochem import models as biochem_models

from settingsdb.tests import utilities

import logging

logger = logging.getLogger('dart.debug')

# These models normally don't exist in the users' local database, they're unmanaged and therefore
# have to be created locally for testing
unmanaged_models = [
    biochem_models.Bcbatches, biochem_models.Bcdatacenters,
    biochem_models.Bcmissions, biochem_models.Bcmissionedits,
    biochem_models.Bcevents, biochem_models.Bceventedits,
    biochem_models.Bcactivities, biochem_models.Bcactivityedits,
    biochem_models.Bcdiscretehedrs, biochem_models.Bcdiscretehedredits,
    biochem_models.Bcplanktnhedredits,
    biochem_models.Bcdiscretedtailedits,
    biochem_models.Bcplanktngenerledits,
    biochem_models.Bccommentedits,
]


# this is a function that can be passed to the MergeTables object, merge tables will
# call this function to report status updates
def status_update(message: str, current: int = 0, max: int = 0):
    logger.debug(f"{message}: {current}/{max}")


@tag('test_merge_bio_tables', 'test_mission_merge')
class TestMissionMerge(TestCase):

    @classmethod
    def setUpClass(cls):
        utilities.create_model_table(unmanaged_models)

    @classmethod
    def tearDownClass(cls):
        utilities.delete_model_table(unmanaged_models)

    def setUp(self):
        pass

    def merge_mission_test(self, mission_attribute, value1, value2, data_center:[biochem_models.Bcdatacenters]=None):
        # provided two missions, values from mission 1 should be copied into mission 0
        kwargs0 = {mission_attribute: value1}
        kwargs1 = {mission_attribute: value2}

        if mission_attribute != 'descriptor':
            descriptor = "MVP112024"
            kwargs0['descriptor'] = descriptor
            kwargs1['descriptor'] = descriptor

        if not data_center:
            data_center = [BCFactoryFloor.BcDataCenterFactory(data_center_code=20, name="BIO")]

        kwargs0['data_center'] = data_center[0]
        kwargs1['data_center'] = data_center[1] if len(data_center) > 1 else data_center[0]

        mission_0 = BCFactoryFloor.BcMissionEditsFactory(**kwargs0)
        mission_1 = BCFactoryFloor.BcMissionEditsFactory(**kwargs1)

        mission_merger = MergeTables.MergeMissions(mission_0, mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_missions()

        mission = biochem_models.Bcmissionedits.objects.get(mission_edt_seq=mission_0.mission_edt_seq)

        return mission, mission_0, mission_1

    #######################
    #   exception tests   #
    #######################
    @tag('test_mission_merge_copy', 'test_mission_merge_copy_fail_data_center_20')
    def test_merge_mission_copy_fail_mission_data_center_20(self):
        # Missions with a data center code of 23 belong to "BIO - Data in review" and breaks rules
        # that we'll have to depend on in order to merge missions, like having unique BcEventEdits.collector_event_id
        data_center = BCFactoryFloor.BcDataCenterFactory(data_center_code=23, name="BIO_INREVIEW")
        args = ("name", "DY18402", "DY18402")
        try:
            mission, mission_0, mission_1 = self.merge_mission_test(*args, data_center=[data_center])
            self.fail("An exception should be raised, can't merge missions not from data center 20")
        except ValueError as ex:
            self.assertEqual(str(ex), "Can only merge missions with a data center of 20")

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_fail_mission_descriptor')
    def test_merge_mission_copy_fail_mission_descriptor(self):
        # the mission descriptor between two missions must match or these missions cannot be merged
        args = ("descriptor", "AVA112024", "COM12022")
        try:
            mission, mission_0, mission_1 = self.merge_mission_test(*args)
            self.fail("An exception should be raised, can't merge missions with different descriptors")
        except ValueError as ex:
            self.assertEqual(str(ex), "Cannot merge missions with different mission descriptors")

    ###################
    #   merge tests   #
    ###################
    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_name')
    def test_merge_mission_copy_mission_name(self):
        args = ("name", "test1", "test2")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_leader')
    def test_merge_mission_copy_mission_leader(self):
        args = ("leader", "test1", "test2")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_sdate')
    def test_merge_mission_copy_mission_sdate(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ("sdate", date0, date1)
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2].date())

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_edate')
    def test_merge_mission_copy_mission_edate(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ("edate", date0, date1)
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2].date())

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_institute')
    def test_merge_mission_copy_mission_institute(self):
        args = ("institute", "BIO", "BIO1")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_platform')
    def test_merge_mission_copy_mission_platform(self):
        args = ("platform", "HRMS Ship", "HRMS Ship 2")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_protocol')
    def test_merge_mission_copy_mission_protocol(self):
        args = ("protocol", "AZMP", "AZOMP")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_geographic_region')
    def test_merge_mission_copy_mission_geographic_region(self):
        args = ("geographic_region", "Scotian Shelf", "Scotian Shelf, Bay of Fundy")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_collector_comment')
    def test_merge_mission_copy_mission_collector_comment(self):
        args = ("collector_comment", "Comments", "Comments 2")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_data_manager_comment')
    def test_merge_mission_copy_mission_data_manager_comment(self):
        args = ("data_manager_comment", "Comments", "Comments 2")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_prod_created_date')
    def test_merge_mission_copy_mission_prod_created_date(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ("prod_created_date", date0, date1)
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2].date())

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_created_by')
    def test_merge_mission_copy_mission_created_by(self):
        args = ("created_by", "upsonp", "bugdonj")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_created_date')
    def test_merge_mission_copy_mission_created_date(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ("created_date", date0, date1)
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2].date())

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_last_update_by')
    def test_merge_mission_copy_mission_last_update_by(self):
        args = ("last_update_by", "upsonp", "bugdonj")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_last_update_date')
    def test_merge_mission_copy_mission_last_update_date(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ("last_update_date", date0, date1)
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2].date())

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_mission_more_comment')
    def test_merge_mission_copy_mission_more_comment(self):
        args = ("more_comment", "N", "Y")
        mission, mission_0, mission_1 = self.merge_mission_test(*args)
        self.assertEqual(getattr(mission, args[0]), args[2])


@tag('test_merge_bio_tables', 'test_event_merge')
class TestEventMerge(TestCase):

    mission_0 = None
    mission_1 = None

    @classmethod
    def setUpClass(cls):
        utilities.create_model_table(unmanaged_models)

    @classmethod
    def tearDownClass(cls):
        utilities.delete_model_table(unmanaged_models)

    def setUp(self):
        descriptor = "MVP112025"
        self.bad_data_center = BCFactoryFloor.BcDataCenterFactory(data_center_code=23, name="BIO_INREVIEW")
        self.mission_0 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.mission_1 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)

    def create_test_events(self, event_attribute, value1, value2, data_center:[biochem_models.Bcdatacenters]=None):

        kwargs0 = {}
        kwargs1 = {}
        if event_attribute is not None:
            # provided two events, values from event 1 should be copied into event 0
            kwargs0[event_attribute] = value1
            kwargs1[event_attribute] = value2

        if not data_center:
            data_center = [BCFactoryFloor.BcDataCenterFactory(data_center_code=20, name="BIO")]

        if event_attribute != 'collector_event_id':
            collector_event_id = "MVP112024"
            kwargs0['collector_event_id'] = collector_event_id
            kwargs1['collector_event_id'] = collector_event_id

        kwargs0['data_center'] = data_center[0]
        kwargs1['data_center'] = data_center[1] if len(data_center) > 1 else data_center[0]

        event_0 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_0, **kwargs0)
        event_1 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1, **kwargs1)

        return event_0, event_1

    def merge_event_test(self, event_seq):
        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_events()

        event = biochem_models.Bceventedits.objects.get(event_edt_seq=event_seq)

        return event

    #####################
    # exception testing #
    #####################
    @tag('test_event_merge_fail_data_center_20')
    def test_event_merge_fail_data_center_20(self):
        # Missions with a data center code of 20 belong to "BIO". For the moment we shouldn't mess with
        # mission data outside of BIO because different regions or datacenters might have different rules for data

        self.mission_0.data_center = self.bad_data_center
        self.mission_0.save()
        self.mission_1.data_center = self.bad_data_center
        self.mission_1.save()

        self.assertEqual(self.mission_0.data_center, self.bad_data_center)
        self.assertEqual(self.mission_1.data_center, self.bad_data_center)

        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)

        event = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1)
        try:
            mission_merger.merge_events()
            self.fail("An exception should be raised, Can only merge missions with a data center of 20")
        except ValueError as ex:
            self.assertEqual(str(ex), "Can only merge missions with a data center of 20")

    @tag('test_event_merge_fail_mission_descriptor')
    def test_event_merge_fail_mission_descriptor(self):
        # the mission descriptor between two missions must match or these missions cannot be merged
        # mission_1 contains a Bceventedits object that doesn't exist in mission_0
        # the object should be reassigned to mission_0 and removed from mission_1
        event = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1)
        bad_descriptor = "MVP112025_1"
        self.mission_0.descriptor = bad_descriptor
        self.mission_0.save()
        self.assertEqual(self.mission_0.descriptor, bad_descriptor)

        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        try:
            mission_merger.merge_events()
            self.fail("An exception should be raised, can't merge missions with different descriptors")
        except ValueError as ex:
            self.assertEqual(str(ex), "Cannot merge missions with different mission descriptors")

    #####################
    #   merge testing   #
    #####################
    @tag('test_event_merge_event_does_not_exist')
    def test_event_merge_event_does_not_exist(self):
        # mission_1 contains a Bceventedits object that doesn't exist in mission_0
        # the object should be reassigned to mission_0 and removed from mission_1
        event = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1)

        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_events()

        mission = biochem_models.Bcmissionedits.objects.get(mission_edt_seq=self.mission_0.mission_edt_seq)
        updated_event = biochem_models.Bceventedits.objects.get(event_edt_seq=event.event_edt_seq)

        self.assertEqual(mission.event_edits.count(), 1)
        self.assertEqual(updated_event.batch.pk, mission.batch.pk)

    # If an event with the collector_event_id already exists in a mission then the details
    # of the existing event should be overridden and all related headers set to point to the
    # existing mission and batch ids updated
    @tag('test_event_merge_event_exist_copy_data_collector_event_id')
    def test_event_merge_event_exist_copy_data(self):
        # passing none will create 2 events with the same collector_event_id and attach them to
        # self.mission_0 and self.mission_1
        args = (None, None, None)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)

        # events 0 and 1 should belong to their respective missions
        # but the merged event should point to self.mission_0
        self.assertEqual(event_0.mission_edit, self.mission_0)
        self.assertEqual(event_1.mission_edit, self.mission_1)

        self.assertEqual(event.event_edt_seq, event_0.event_edt_seq)
        self.assertEqual(event.mission_edit, event_0.mission_edit)

    @tag('test_event_merge_event_exist_copy_data_sdate')
    def test_event_merge_event_exist_copy_data_sdate(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ('sdate', date0, date1)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2].date())

    @tag('test_event_merge_event_exist_copy_data_edate')
    def test_event_merge_event_exist_copy_data_edate(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ('edate', date0, date1)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2].date())

    @tag('test_event_merge_event_exist_copy_data_stime')
    def test_event_merge_event_exist_copy_data_stime(self):
        args = ('stime', 1422, 1555)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_etime')
    def test_event_merge_event_exist_copy_data_etime(self):
        args = ('etime', 1422, 1555)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_min_lat')
    def test_event_merge_event_exist_copy_data_min_lat(self):
        args = ('min_lat', 41.333, 45.5)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_max_lat')
    def test_event_merge_event_exist_copy_data_max_lat(self):
        args = ('max_lat', 41.333, 45.5)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_min_lon')
    def test_event_merge_event_exist_copy_data_min_lon(self):
        args = ('min_lon', 41.333, 45.5)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_max_lon')
    def test_event_merge_event_exist_copy_data_max_lon(self):
        args = ('max_lon', 41.333, 45.5)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_collector_station_name')
    def test_event_merge_event_exist_copy_data_collector_station_name(self):
        args = ('collector_station_name', 'test1', 'test2')
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_utc_offset')
    def test_event_merge_event_exist_copy_data_utc_offset(self):
        args = ('utc_offset', 3.0, 4.0)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_collector_comment')
    def test_event_merge_event_exist_copy_data_collector_comment(self):
        args = ('collector_comment', "Comment #1", "Comment #2")
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_data_manager_comment')
    def test_event_merge_event_exist_copy_data_data_manager_comment(self):
        args = ('data_manager_comment', "Comment #1", "Comment #2")
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_more_comment')
    def test_event_merge_event_exist_copy_data_more_comment(self):
        args = ('more_comment', "N", "Y")
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_prod_created_date')
    def test_event_merge_event_exist_copy_data_prod_created_date(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ('prod_created_date', date0, date1)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2].date())

    @tag('test_event_merge_event_exist_copy_data_created_by')
    def test_event_merge_event_exist_copy_data_created_by(self):
        args = ('created_by', "BugdonJ", "UpsonP")
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_created_date')
    def test_event_merge_event_exist_copy_data_created_date(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ('created_date', date0, date1)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2].date())

    @tag('test_event_merge_event_exist_copy_data_last_update_by')
    def test_event_merge_event_exist_copy_data_last_update_by(self):
        args = ('last_update_by', "BugdonJ", "UpsonP")
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_last_update_date')
    def test_event_merge_event_exist_copy_data_last_update_date(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ('last_update_date', date0, date1)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2].date())

    @tag('test_event_merge_event_exist_copy_data_process_flag')
    def test_event_merge_event_exist_copy_data_process_flag(self):
        args = ('process_flag', "EAR", "ECN")
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_batch')
    def test_event_merge_event_exist_copy_data_batch(self):
        # in the case of batches, the merged event should share the batch id with self.mission_0 as that would be the
        # mission that was checked out from the archive that we're merging new data into.
        args = (None, None, None)
        event_0, event_1 = self.create_test_events(*args)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertNotEqual(getattr(event_1, "batch"), self.mission_0.batch)
        self.assertEqual(getattr(event, "batch"), self.mission_0.batch)

    @tag('test_event_merge_event_exist_activities_batch')
    def test_event_merge_event_exist_activities_batch(self):
        args = (None, None, None)
        event_0, event_1 = self.create_test_events(*args)
        activity = BCFactoryFloor.BcActivityEditsFactory(event_edit=event_1)
        self.assertEqual(getattr(activity, "batch"), self.mission_1.batch)

        event = self.merge_event_test(event_0.event_edt_seq)
        activity = biochem_models.Bcactivityedits.objects.get(activity_edt_seq=activity.activity_edt_seq)
        self.assertEqual(event.activity_edits.count(), 1)
        self.assertEqual(getattr(activity, "batch"), self.mission_0.batch)

    @tag('test_event_merge_event_exist_discrete_header_batch')
    def test_event_merge_event_exist_discrete_header_batch(self):
        args = (None, None, None)
        event_0, event_1 = self.create_test_events(*args)
        discrete_header = BCFactoryFloor.BcDiscreteHeaderEditsFactory(event_edit=event_1)
        self.assertEqual(getattr(discrete_header, "batch"), self.mission_1.batch)

        event = self.merge_event_test(event_0.event_edt_seq)
        discrete_header = biochem_models.Bcdiscretehedredits.objects.get(dis_headr_edt_seq=discrete_header.dis_headr_edt_seq)
        self.assertEqual(event.discrete_header_edits.count(), 1)
        self.assertEqual(getattr(discrete_header, "batch"), self.mission_0.batch)

    @tag('test_event_merge_event_exist_plankton_header_batch')
    def test_event_merge_event_exist_plankton_header_batch(self):
        args = (None, None, None)
        event_0, event_1 = self.create_test_events(*args)
        plankton_header = BCFactoryFloor.BcPlanktonHeaderEditsFactory(event_edit=event_1)
        self.assertEqual(getattr(plankton_header, "batch"), self.mission_1.batch)

        event = self.merge_event_test(event_0.event_edt_seq)
        plankton_header = biochem_models.Bcplanktnhedredits.objects.get(pl_headr_edt_seq=plankton_header.pl_headr_edt_seq)
        self.assertEqual(event.plankton_header_edits.count(), 1)
        self.assertEqual(getattr(plankton_header, "batch"), self.mission_0.batch)

    @tag('test_event_merge_event_exist_more_comments_batch')
    def test_event_merge_event_exist_more_comments_batch(self):
        args = (None, None, None)
        event_0, event_1 = self.create_test_events(*args)
        more_comments = BCFactoryFloor.BcMoreCommentEditsEventFactory(event_edit=event_1)
        self.assertEqual(getattr(more_comments, "batch"), self.mission_1.batch)

        event = self.merge_event_test(event_0.event_edt_seq)
        more_comments = biochem_models.Bccommentedits.objects.get(comment_edt_seq=more_comments.comment_edt_seq)
        self.assertEqual(event.comment_edits.count(), 1)
        self.assertEqual(getattr(more_comments, "batch"), self.mission_0.batch)


@tag('test_merge_bio_tables', 'test_discrete_header_merge')
class TestEventMerge(TestCase):

    mission_0 = None
    mission_1 = None

    @classmethod
    def setUpClass(cls):
        utilities.create_model_table(unmanaged_models)

    @classmethod
    def tearDownClass(cls):
        utilities.delete_model_table(unmanaged_models)

    def setUp(self):
        descriptor = "MVP112025"
        collector_event_id = "2025"
        self.bad_data_center = BCFactoryFloor.BcDataCenterFactory(data_center_code=23, name="BIO_INREVIEW")

        # two missions with the same descriptor sharing an identical event
        self.mission_0 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.event_0 = BCFactoryFloor.BcEventEditsFactory(mission=self.mission_0, collector_event_id=collector_event_id)

        self.mission_1 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.event_1 = BCFactoryFloor.BcEventEditsFactory(mission=self.mission_1, collector_event_id=collector_event_id)
