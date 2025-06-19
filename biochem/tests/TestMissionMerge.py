import datetime

from django.test import TestCase, tag

from biochem.tests import BCFactoryFloor
from biochem import MergeTables
from biochem import models as biochem_models
from core.views_sample_type import new_sample_type

from user_settings.tests import utilities

import logging

logger = logging.getLogger('dart.debug')

# These models normally don't exist in the users' local database, they're unmanaged and therefore
# have to be created locally for testing
unmanaged_models = [
    biochem_models.Bcbatches, biochem_models.Bcdatacenters, biochem_models.Bcdatatypes,
    biochem_models.Bcmissions, biochem_models.Bcmissionedits,
    biochem_models.Bcevents, biochem_models.Bceventedits,
    biochem_models.Bcactivities, biochem_models.Bcactivityedits,
    biochem_models.Bcdiscretehedrs, biochem_models.Bcdiscretehedredits,
    biochem_models.Bcplanktnhedredits,
    biochem_models.Bcdiscretedtailedits, biochem_models.Bcdiscretedtails,
    biochem_models.Bcdisreplicatedits, biochem_models.Bcdiscretereplicteditsdel,
    biochem_models.Bcplanktngenerledits,
    biochem_models.Bccommentedits, biochem_models.Bccommenteditsdel
]


# this is a function that can be passed to the MergeTables object, merge tables will
# call this function to report status updates
def status_update(message: str, current: int = 0, max_count: int = 0):
    logger.debug(f"{message}: {current}/{max_count}")


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

    @staticmethod
    def merge_mission_test(mission_attribute, value1, value2, data_center:[biochem_models.Bcdatacenters]=None):
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
            self.merge_mission_test(*args, data_center=[data_center])
            self.fail("An exception should be raised, can't merge missions not from data center 20")
        except ValueError as ex:
            self.assertEqual(str(ex), "Can only merge missions with a data center of 20")

    @tag('test_mission_merge_copy', 'test_mission_merge_copy_fail_mission_descriptor')
    def test_merge_mission_copy_fail_mission_descriptor(self):
        # the mission descriptor between two missions must match or these missions cannot be merged
        args = ("descriptor", "AVA112024", "COM12022")
        try:
            self.merge_mission_test(*args)
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

    @tag('test_mission_merge_copy', 'test_merge_mission_comment_edits')
    def test_merge_mission_comment_edits(self):
        # if a mission being merged has a reference to the BcCommentEdits table, the comments
        # should be carried over to the mission we're updating
        descriptor = "MVP112024"
        data_center = BCFactoryFloor.BcDataCenterFactory(data_center_code=20, name="BIO")

        mission_0 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor, data_center=data_center)
        mission_1 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor, data_center=data_center)

        new_comment = BCFactoryFloor.BcMoreCommentEditsMissionFactory(mission_edit=mission_1)

        mission_merger = MergeTables.MergeMissions(mission_0, mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_missions()

        updated_mission = biochem_models.Bcmissionedits.objects.get(mission_edt_seq=mission_0.mission_edt_seq)
        self.assertEqual(updated_mission.comment_edits.count(), 1)
        self.assertTrue(updated_mission.comment_edits.filter(comment_edt_seq=new_comment.comment_edt_seq).exists())

    @tag('test_mission_merge_copy', 'test_merge_mission_existing_comment_edits')
    def test_merge_mission_existing_comment_edits(self):
        # if a mission being merged into has references to existing the BcCommentEdits,
        # the existing comments should be removed and replaced with comments from the mission being merged
        descriptor = "MVP112024"
        data_center = BCFactoryFloor.BcDataCenterFactory(data_center_code=20, name="BIO")

        mission_0 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor, data_center=data_center)
        mission_1 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor, data_center=data_center)

        old_comment = BCFactoryFloor.BcMoreCommentEditsMissionFactory(mission_edit=mission_0)
        BCFactoryFloor.BcMoreCommentEditsMissionFactory(mission_edit=mission_0)
        new_comment = BCFactoryFloor.BcMoreCommentEditsMissionFactory(mission_edit=mission_1)

        mission_merger = MergeTables.MergeMissions(mission_0, mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_missions()

        updated_mission = biochem_models.Bcmissionedits.objects.get(mission_edt_seq=mission_0.mission_edt_seq)
        self.assertEqual(updated_mission.comment_edits.count(), 1)
        self.assertTrue(updated_mission.comment_edits.filter(comment_edt_seq=new_comment.comment_edt_seq).exists())

        # The old comment shoul dhave been deleted
        self.assertFalse(biochem_models.Bccommentedits.objects.filter(comment_edt_seq=old_comment.comment_edt_seq).exists())


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

    def create_test_events(self, event_attribute, value1, value2, data_center:[biochem_models.Bcdatacenters]=None, additional_attributes=None):

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

        if additional_attributes:
            for attr in additional_attributes:
                kwargs0[attr[0]] = attr[1]
                kwargs1[attr[0]] = attr[2]

        event_0 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_0, **kwargs0)
        event_1 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1, **kwargs1)

        return event_0, event_1

    def merge_event_test(self, event_seq):
        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_update_objects(mission_merger.get_update_events())

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

        BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1)
        try:
            mission_merger.merge_update_objects(mission_merger.get_update_events())
            self.fail("An exception should be raised, Can only merge missions with a data center of 20")
        except ValueError as ex:
            self.assertEqual(str(ex), "Can only merge missions with a data center of 20")

    @tag('test_event_merge_fail_mission_descriptor')
    def test_event_merge_fail_mission_descriptor(self):
        # the mission descriptor between two missions must match or these missions cannot be merged
        # mission_1 contains a Bceventedits object that doesn't exist in mission_0
        # the object should be reassigned to mission_0 and removed from mission_1
        BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1)
        bad_descriptor = "MVP112025_1"
        self.mission_0.descriptor = bad_descriptor
        self.mission_0.save()
        self.assertEqual(self.mission_0.descriptor, bad_descriptor)

        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        try:
            mission_merger.merge_update_objects(mission_merger.get_update_events())
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
        mission_merger.merge_update_objects(mission_merger.get_update_events())

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

    @tag('test_event_merge_event_exist_copy_data_last_update_by')
    def test_event_merge_event_exist_copy_data_last_update_by(self):
        additional = [("data_manager_comment", "TedF", "Upsonp")]
        args = ('last_update_by', "BugdonJ", "UpsonP")
        event_0, event_1 = self.create_test_events(*args, additional_attributes=additional)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2])

    @tag('test_event_merge_event_exist_copy_data_last_update_date')
    def test_event_merge_event_exist_copy_data_last_update_date(self):
        additional = [("data_manager_comment", "TedF", "Upsonp")]
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ('last_update_date', date0, date1)
        event_0, event_1 = self.create_test_events(*args, additional_attributes=additional)
        event = self.merge_event_test(event_0.event_edt_seq)
        self.assertEqual(getattr(event, args[0]), args[2].date())

    @tag('test_event_merge_event_exist_copy_data_process_flag')
    def test_event_merge_event_exist_copy_data_process_flag(self):
        additional = [("data_manager_comment", "TedF", "Upsonp")]
        args = ('process_flag', "EAR", "ECN")
        event_0, event_1 = self.create_test_events(*args, additional_attributes=additional)
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

    # We don't need to worry about merging Event Activities. If an event exists and we're merging the existing
    # event activity will be used and doesn't change. If we're adding an event, when the event.mission_event is updated
    # the event activity created by the Biochem Stored Procedure will will go along with the event
    #
    # @tag('test_event_merge_event_exist_activities_batch')
    # def test_event_merge_event_exist_activities_batch(self):
    #     args = (None, None, None)
    #     event_0, event_1 = self.create_test_events(*args)
    #     activity = BCFactoryFloor.BcActivityEditsFactory(event_edit=event_1)
    #     self.assertEqual(getattr(activity, "batch"), self.mission_1.batch)
    #
    #     event = self.merge_event_test(event_0.event_edt_seq)
    #     activity = biochem_models.Bcactivityedits.objects.get(activity_edt_seq=activity.activity_edt_seq)
    #     self.assertEqual(event.activity_edits.count(), 1)
    #     self.assertEqual(getattr(activity, "batch"), self.mission_0.batch)

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

    @tag('test_event_merge_event_exist_delete_more_comments_batch')
    def test_event_merge_event_exist_delete_more_comments_batch(self):
        args = (None, None, None)
        event_0, event_1 = self.create_test_events(*args)
        old_comment = BCFactoryFloor.BcMoreCommentEditsEventFactory(event_edit=event_0)
        new_comment = BCFactoryFloor.BcMoreCommentEditsEventFactory(event_edit=event_1)
        self.assertEqual(getattr(new_comment, "batch"), self.mission_1.batch)

        event = self.merge_event_test(event_0.event_edt_seq)
        more_comments = biochem_models.Bccommentedits.objects.get(comment_edt_seq=new_comment.comment_edt_seq)
        self.assertEqual(event.comment_edits.count(), 1)
        self.assertEqual(getattr(more_comments, "batch"), self.mission_0.batch)

        old_comments = biochem_models.Bccommentedits.objects.filter(comment_edt_seq=old_comment.comment_edt_seq)
        self.assertFalse(old_comments.exists())

@tag('test_merge_bio_tables', 'test_discrete_header_merge')
class TestDiscreteHeaderMerge(TestCase):

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
        collector_event_id = "001"
        self.bad_data_center = BCFactoryFloor.BcDataCenterFactory(data_center_code=23, name="BIO_INREVIEW")
        self.mission_0 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.event_0 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_0, collector_event_id=collector_event_id)

        self.mission_1 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.event_1 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1, collector_event_id=collector_event_id)

    def merge_discrete_header_test(self, dis_header_seq):
        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_update_objects(mission_merger.get_update_discrete_headers())

        event = biochem_models.Bcdiscretehedredits.objects.get(dis_headr_edt_seq=dis_header_seq)

        return event

    def create_test_discrete_header(self, header_attribute, value1, value2, data_center:[biochem_models.Bcdatacenters]=None, additional_attributes=None):

        kwargs0 = {}
        kwargs1 = {}
        if header_attribute is not None:
            # provided two events, values from event 1 should be copied into event 0
            kwargs0[header_attribute] = value1
            kwargs1[header_attribute] = value2

        if not data_center:
            data_center = [BCFactoryFloor.BcDataCenterFactory(data_center_code=20, name="BIO")]

        if header_attribute != 'collector_sample_id':
            collector_event_id = "450000"
            kwargs0['collector_sample_id'] = collector_event_id
            kwargs1['collector_sample_id'] = collector_event_id

        kwargs0['data_center'] = data_center[0]
        kwargs1['data_center'] = data_center[1] if len(data_center) > 1 else data_center[0]

        if additional_attributes:
            for attr in additional_attributes:
                kwargs0[attr[0]] = attr[1]
                kwargs1[attr[0]] = attr[2]

        discrete_header_0 = BCFactoryFloor.BcDiscreteHeaderEditsFactory(event_edit=self.event_0, **kwargs0)
        discrete_header_1 = BCFactoryFloor.BcDiscreteHeaderEditsFactory(event_edit=self.event_1, **kwargs1)

        return discrete_header_0, discrete_header_1

    # Collector Sample Id is being used as a natural primary key to match discrete headers
    # across events per mission. No two events should use the same collector sample ID
    # collector_sample_id = models.CharField(max_length=50, blank=True, null=True)

    # If a discrete header didn't previously belong to an event then update the event_edt_seq to point to the
    # event the header is getting attached to. Everything else can remain the same.
    #
    # event_edit = models.ForeignKey(Bceventedits, related_name='discrete_header_edits', blank=True, null=True,
    #                                db_column='event_edt_seq', on_delete=models.CASCADE)
    @tag('test_discrete_header_merge_does_not_exist_batch')
    def test_discrete_header_merge_does_not_exist_batch(self):
        # event_1 contains a Bcdiscreteedits object that doesn't exist in event_0
        # the object should be reassigned to event_0 and removed from event_1
        discrete_header = BCFactoryFloor.BcDiscreteHeaderEditsFactory(event_edit=self.event_1)

        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_update_objects(mission_merger.get_update_discrete_headers())

        event = biochem_models.Bceventedits.objects.get(event_edt_seq=self.event_0.event_edt_seq)
        updated_discrete_header = biochem_models.Bcdiscretehedredits.objects.get(dis_headr_edt_seq=discrete_header.dis_headr_edt_seq)

        self.assertEqual(event.discrete_header_edits.count(), 1)
        self.assertEqual(updated_discrete_header.batch.pk, event.batch.pk)

    # gear_seq = models.IntegerField(blank=True, null=True)
    @tag('test_event_merge_discrete_header_gear_seq')
    def test_event_merge_discrete_header_gear_seq(self):
        args = ("gear_seq", 100, 101)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # sdate = models.DateField(blank=True, null=True)
    @tag('test_event_merge_discrete_header_sdate')
    def test_event_merge_discrete_header_sdate(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ("sdate", date0, date1)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2].date())

    # edate = models.DateField(blank=True, null=True)
    @tag('test_event_merge_discrete_header_edate')
    def test_event_merge_discrete_header_edate(self):
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ("edate", date0, date1)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2].date())

    # stime = models.IntegerField(blank=True, null=True)
    @tag('test_event_merge_discrete_header_stime')
    def test_event_merge_discrete_header_stime(self):
        args = ("stime", 1100, 1200)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # etime = models.IntegerField(blank=True, null=True)
    @tag('test_event_merge_discrete_header_etime')
    def test_event_merge_discrete_header_etime(self):
        args = ("etime", 1100, 1200)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # time_qc_code = models.CharField(max_length=2, blank=True, null=True)
    @tag('test_event_merge_discrete_header_time_qc_code')
    def test_event_merge_discrete_header_time_qc_code(self):
        args = ("time_qc_code", "UN", "NU")
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # slat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    @tag('test_event_merge_discrete_header_slat')
    def test_event_merge_discrete_header_slat(self):
        args = ("slat", 41.2, 43.5)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # elat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    @tag('test_event_merge_discrete_header_elat')
    def test_event_merge_discrete_header_elat(self):
        args = ("elat", 41.2, 43.5)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # slon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    @tag('test_event_merge_discrete_header_slon')
    def test_event_merge_discrete_header_slon(self):
        args = ("slon", 41.2, 43.5)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # elon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    @tag('test_event_merge_discrete_header_elon')
    def test_event_merge_discrete_header_elon(self):
        args = ("elon", 41.2, 43.5)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # position_qc_code = models.CharField(max_length=2, blank=True, null=True)
    @tag('test_event_merge_discrete_header_position_qc_code')
    def test_event_merge_discrete_header_position_qc_code(self):
        args = ("position_qc_code", "UN", "NU")
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # start_depth = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    @tag('test_event_merge_discrete_header_start_depth')
    def test_event_merge_discrete_header_start_depth(self):
        args = ("start_depth", 20.5, 100.5)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # end_depth = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    @tag('test_event_merge_discrete_header_end_depth')
    def test_event_merge_discrete_header_end_depth(self):
        args = ("end_depth", 10.5, 100.5)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # sounding = models.IntegerField(blank=True, null=True)
    @tag('test_event_merge_discrete_header_sounding')
    def test_event_merge_discrete_header_sounding(self):
        args = ("sounding", 10, 20)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # collector_deployment_id = models.CharField(max_length=50, blank=True, null=True)
    @tag('test_event_merge_discrete_header_collector_deployment_id')
    def test_event_merge_discrete_header_collector_deployment_id(self):
        args = ("collector_deployment_id", "Test_0", "Test_1")
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # collector = models.CharField(max_length=50, blank=True, null=True)
    @tag('test_event_merge_discrete_header_collector')
    def test_event_merge_discrete_header_collector(self):
        args = ("collector", "Ted", "Patrick")
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # collector_comment = models.CharField(max_length=2000, blank=True, null=True)
    @tag('test_event_merge_discrete_header_collector_comment')
    def test_event_merge_discrete_header_collector_comment(self):
        args = ("collector_comment", "Some Comment", "Another Comment")
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)
    @tag('test_event_merge_discrete_header_data_manager_comment')
    def test_event_merge_discrete_header_data_manager_comment(self):
        args = ("data_manager_comment", "Some Comment", "Another Comment")
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # responsible_group = models.CharField(max_length=50, blank=True, null=True)
    @tag('test_event_merge_discrete_header_responsible_group')
    def test_event_merge_discrete_header_responsible_group(self):
        args = ("responsible_group", "Some Comment", "Another Comment")
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # shared_data = models.CharField(max_length=50, blank=True, null=True)
    @tag('test_event_merge_discrete_header_shared_data')
    def test_event_merge_discrete_header_shared_data(self):
        args = ("shared_data", "Some Comment", "Another Comment")
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # prod_created_date is handled by the biochem stored procedures
    # prod_created_date = models.DateField(blank=True, null=True)

    # keep the created by, only update last_updated and last_updated_by if an update occured
    # created_by = models.CharField(max_length=30, blank=True, null=True)

    # keep the created date, only update last_updated and last_updated_by if an update occured
    # created_date = models.DateField(blank=True, null=True)

    # last_update_by = models.CharField(max_length=30, blank=True, null=True)
    @tag('test_event_merge_discrete_header_last_update_by')
    def test_event_merge_discrete_header_last_update_by(self):
        additional = [("shared_data", "TedF", "Upsonp")]
        args = ("last_update_by", "ROBARF", "UPSONP")
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args, additional_attributes=additional)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # last_update_date = models.DateField(blank=True, null=True)
    @tag('test_event_merge_discrete_header_last_update_date')
    def test_event_merge_discrete_header_last_update_date(self):
        additional = [("shared_data", "TedF", "Upsonp")]
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ("last_update_date", date0, date1)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args, additional_attributes=additional)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2].date())

    # process_flag = models.CharField(max_length=3)
    @tag('test_event_merge_discrete_header_process_flag')
    def test_event_merge_discrete_header_process_flag(self):
        additional = [("shared_data", "TedF", "Upsonp")]
        args = ("process_flag", "EAR", "ECN")
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args, additional_attributes=additional)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertEqual(getattr(dis_header, args[0]), args[2])

    # batch = models.ForeignKey(Bcbatches, related_name='discrete_header_edits', db_column='batch_seq',
    #                           blank=True, null=True, on_delete=models.CASCADE)
    @tag('test_event_merge_discrete_header_batch')
    def test_event_merge_discrete_header_batch(self):
        # in the case of batches, the merged event should share the batch id with self.mission_0 as that would be the
        # mission that was checked out from the archive that we're merging new data into.
        args = (None, None, None)
        dis_header_0, dis_header_1 = self.create_test_discrete_header(*args)
        dis_header = self.merge_discrete_header_test(dis_header_0.dis_headr_edt_seq)
        self.assertNotEqual(getattr(dis_header_1, "batch"), self.mission_0.batch)
        self.assertEqual(getattr(dis_header, "batch"), self.mission_0.batch)


@tag('test_merge_bio_tables', 'test_merge_discrete_details')
class TestDiscreteDetailMerge(TestCase):

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
        collector_event_id = "001"
        discrete_header_sample_id = 450000
        self.bad_data_center = BCFactoryFloor.BcDataCenterFactory(data_center_code=23, name="BIO_INREVIEW")
        self.data_type = BCFactoryFloor.BcDataTypeFactory()

        self.mission_0 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.event_0 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_0, collector_event_id=collector_event_id)
        self.discrete_header_0 = BCFactoryFloor.BcDiscreteHeaderEditsFactory(event_edit=self.event_0, collector_sample_id=discrete_header_sample_id)

        self.mission_1 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.event_1 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1, collector_event_id=collector_event_id)
        self.discrete_header_1 = BCFactoryFloor.BcDiscreteHeaderEditsFactory(event_edit=self.event_1, collector_sample_id=discrete_header_sample_id)

    def merge_discrete_details_test(self, dis_detail_seq):
        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_update_objects(mission_merger.get_update_discrete_details())

        dis_detail = biochem_models.Bcdiscretedtailedits.objects.get(dis_detail_edt_seq=dis_detail_seq)

        return dis_detail

    def create_test_discrete_details(self, detail_attribute, value1, value2, data_center:[biochem_models.Bcdatacenters]=None, additional_attributes:list=None):

        kwargs0 = {}
        kwargs1 = {}
        if detail_attribute is not None:
            # provided two events, values from event 1 should be copied into event 0
            kwargs0[detail_attribute] = value1
            kwargs1[detail_attribute] = value2

        if not data_center:
            data_center = [BCFactoryFloor.BcDataCenterFactory(data_center_code=20, name="BIO")]

        if detail_attribute != 'collector_sample_id':
            collector_event_id = "450000"
            kwargs0['collector_sample_id'] = collector_event_id
            kwargs1['collector_sample_id'] = collector_event_id

        kwargs0['data_center'] = data_center[0]
        kwargs1['data_center'] = data_center[1] if len(data_center) > 1 else data_center[0]

        if additional_attributes:
            for attr in additional_attributes:
                kwargs0[attr[0]] = attr[1]
                kwargs0[attr[0]] = attr[2]

        discrete_detail_0 = BCFactoryFloor.BcDiscreteDetailEditsFactory(dis_header_edit=self.discrete_header_0, **kwargs0)
        discrete_detail_1 = BCFactoryFloor.BcDiscreteDetailEditsFactory(dis_header_edit=self.discrete_header_1, **kwargs1)

        return discrete_detail_0, discrete_detail_1

    @tag('test_merge_discrete_details_does_not_exist_batch')
    def test_discrete_detail_merge_does_not_exist_batch(self):
        # event_1 contains a Bcdiscreteedits object that doesn't exist in event_0
        # the object should be reassigned to event_0 and removed from event_1
        discrete_detail = BCFactoryFloor.BcDiscreteDetailEditsFactory(dis_header_edit=self.discrete_header_1)

        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_update_objects(mission_merger.get_update_discrete_details())

        header = biochem_models.Bcdiscretehedredits.objects.get(dis_headr_edt_seq=self.discrete_header_0.dis_headr_edt_seq)
        updated_discrete_detail = biochem_models.Bcdiscretedtailedits.objects.get(dis_detail_edt_seq=discrete_detail.dis_detail_edt_seq)

        self.assertEqual(header.discrete_detail_edits.count(), 1)
        self.assertEqual(updated_discrete_detail.batch.pk, header.batch.pk)

    # data_type = models.ForeignKey(Bcdatatypes, related_name='discrete_detail_edits', db_column='data_type_seq',
    #                               blank=True, null=True, on_delete=models.DO_NOTHING)
    @tag('test_merge_discrete_details_data_type')
    def test_merge_discrete_details_data_type(self):
        # if a detail object shares a sample ID, but has a different data type, these should be
        # different entries.
        data_type_0 = BCFactoryFloor.BcDataTypeFactory(data_type_seq=10001)
        data_type_1 = BCFactoryFloor.BcDataTypeFactory(data_type_seq=10002)

        discrete_detail_0 = BCFactoryFloor.BcDiscreteDetailEditsFactory(dis_header_edit=self.discrete_header_0, collector_sample_id=450001, data_type=data_type_0)
        discrete_detail_1 = BCFactoryFloor.BcDiscreteDetailEditsFactory(dis_header_edit=self.discrete_header_1, collector_sample_id=450001, data_type=data_type_1)

        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_update_objects(mission_merger.get_update_discrete_details())

        header = biochem_models.Bcdiscretehedredits.objects.get(dis_headr_edt_seq=self.discrete_header_0.dis_headr_edt_seq)
        updated_discrete_detail = biochem_models.Bcdiscretedtailedits.objects.get(dis_detail_edt_seq=discrete_detail_1.dis_detail_edt_seq)

        self.assertEqual(header.discrete_detail_edits.count(), 2)
        self.assertEqual(updated_discrete_detail.batch.pk, header.batch.pk)

   # data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    @tag('test_merge_discrete_details_data_value')
    def test_merge_discrete_details_data_value(self):
        args = ("data_value", 19.6, 25.5)
        dis_detail_0, dis_detail_1 = self.create_test_discrete_details(*args)
        dis_detail = self.merge_discrete_details_test(dis_detail_0.dis_detail_edt_seq)
        self.assertEqual(getattr(dis_detail, args[0]), args[2])

    # data_flag = models.CharField(max_length=3, blank=True, null=True)
    @tag('test_merge_discrete_details_data_flag')
    def test_merge_discrete_details_data_flag(self):
        args = ("data_flag", "yes", "no")
        dis_detail_0, dis_detail_1 = self.create_test_discrete_details(*args)
        dis_detail = self.merge_discrete_details_test(dis_detail_0.dis_detail_edt_seq)
        self.assertEqual(getattr(dis_detail, args[0]), args[2])

    # Data is averaged by the Stage 2 validation procedure, it's not something that
    # gets set by the application so should be left alone.
    # averaged_data = models.CharField(max_length=1, blank=True, null=True)

    # data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    @tag('test_merge_discrete_details_data_qc_code')
    def test_merge_discrete_details_data_qc_code(self):
        args = ("data_qc_code", "4", "1")
        dis_detail_0, dis_detail_1 = self.create_test_discrete_details(*args)
        dis_detail = self.merge_discrete_details_test(dis_detail_0.dis_detail_edt_seq)
        self.assertEqual(getattr(dis_detail, args[0]), args[2])

    # qc_flag = models.CharField(max_length=3, blank=True, null=True)
    @tag('test_merge_discrete_details_qc_flag')
    def test_merge_discrete_details_qc_flag(self):
        args = ("qc_flag", "Yes", "No")
        dis_detail_0, dis_detail_1 = self.create_test_discrete_details(*args)
        dis_detail = self.merge_discrete_details_test(dis_detail_0.dis_detail_edt_seq)
        self.assertEqual(getattr(dis_detail, args[0]), args[2])

    # detection_limit = models.DecimalField(max_digits=11, decimal_places=5, blank=True, null=True)
    @tag('test_merge_discrete_details_detection_limit')
    def test_merge_discrete_details_detection_limit(self):
        args = ("detection_limit", 0.1, 2.5)
        dis_detail_0, dis_detail_1 = self.create_test_discrete_details(*args)
        dis_detail = self.merge_discrete_details_test(dis_detail_0.dis_detail_edt_seq)
        self.assertEqual(getattr(dis_detail, args[0]), args[2])

    # detail_collector = models.CharField(max_length=50, blank=True, null=True)
    @tag('test_merge_discrete_details_detail_collector')
    def test_merge_discrete_details_detail_collector(self):
        args = ("detail_collector", "TedF", "Upsonp")
        dis_detail_0, dis_detail_1 = self.create_test_discrete_details(*args)
        dis_detail = self.merge_discrete_details_test(dis_detail_0.dis_detail_edt_seq)
        self.assertEqual(getattr(dis_detail, args[0]), args[2])

    # The collector sample ID is used as a combined natural key with the data type
    # collector_sample_id = models.CharField(max_length=50, blank=True, null=True)

    # prod_created_date is handled by the BIO chem Store Procedures
    # prod_created_date = models.DateField(blank=True, null=True)

    # keep the created by, only update last_updated and last_updated_by if an update occured
    # created_by = models.CharField(max_length=30, blank=True, null=True)

    # keep the created date, only update last_updated and last_updated_by if an update occured
    # created_date = models.DateField(blank=True, null=True)

    # last_update_by = models.CharField(max_length=30, blank=True, null=True)
    @tag('test_merge_discrete_details_last_update_by')
    def test_merge_discrete_details_last_update_by(self):
        # last updated, last updated by and process flag only get updated if some other update happens
        additional = [("detail_collector", "TedF", "Upsonp")]
        args = ("last_update_by", "TedF", "Upsonp")
        dis_detail_0, dis_detail_1 = self.create_test_discrete_details(*args, additional_attributes=additional)
        dis_detail = self.merge_discrete_details_test(dis_detail_0.dis_detail_edt_seq)
        self.assertEqual(getattr(dis_detail, args[0]), args[2])

    # last_update_date = models.DateField(blank=True, null=True)
    @tag('test_merge_discrete_details_last_update_date')
    def test_merge_discrete_details_last_update_date(self):
        # last updated, last updated by and process flag only get updated if some other update happens
        additional = [("detail_collector", "TedF", "Upsonp")]
        date0 = datetime.datetime.strptime('2009/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        date1 = datetime.datetime.strptime('2010/02/02 00:00:00', "%Y/%m/%d %H:%M:%S")
        args = ("last_update_date", date0, date1)
        dis_detail_0, dis_detail_1 = self.create_test_discrete_details(*args, additional_attributes=additional)
        dis_detail = self.merge_discrete_details_test(dis_detail_0.dis_detail_edt_seq)
        self.assertEqual(getattr(dis_detail, args[0]), args[2].date())

    # process_flag = models.CharField(max_length=3)
    @tag('test_merge_discrete_details_process_flag')
    def test_merge_discrete_details_process_flag(self):
        # last updated, last updated by and process flag only get updated if some other update happens
        additional = [("detail_collector", "TedF", "Upsonp")]
        args = ("process_flag", "EAR", "ECN")
        dis_detail_0, dis_detail_1 = self.create_test_discrete_details(*args, additional_attributes=additional)
        dis_detail = self.merge_discrete_details_test(dis_detail_0.dis_detail_edt_seq)
        self.assertEqual(getattr(dis_detail, args[0]), args[2])


# Replicates work differently than other Biochem discrete objects.
# There's no natural or combined primary key uniquely identifying an individual
# replicate all you have to go on is the order they appear in, which isn't ideal
# for merging.
#
# To Handle replicates we'll check the incoming details object, if the detail object didn't
# already exist then when it gets reassigned in the "Does Not Exist" exception, it's replicates
# automatically go with it. If the details object does already exist, we'll delete any replicates
# it already has, and then reassign the replicates from the incoming detail object.
# This makes the assumption that replicates will always be uploaded together and never just as
# a means to update an existing replicate, which I assume they have to be anyway because if
# they're not uploaded together, then the Biochem Stage 2 validation won't know how to
# or even that it's supposed to average them in the user edit tables.
@tag('test_merge_bio_tables', 'test_merge_discrete_replicates')
class TestDiscreteReplicatesMerge(TestCase):

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
        collector_event_id = "001"
        discrete_header_sample_id = 450000
        self.bad_data_center = BCFactoryFloor.BcDataCenterFactory(data_center_code=23, name="BIO_INREVIEW")
        self.data_type = BCFactoryFloor.BcDataTypeFactory()

        self.mission_0 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.event_0 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_0, collector_event_id=collector_event_id)
        self.discrete_header_0 = BCFactoryFloor.BcDiscreteHeaderEditsFactory(event_edit=self.event_0, collector_sample_id=discrete_header_sample_id)
        self.discrete_details_0 = BCFactoryFloor.BcDiscreteDetailEditsFactory(dis_header_edit=self.discrete_header_0, collector_sample_id=discrete_header_sample_id)

        self.mission_1 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.event_1 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1, collector_event_id=collector_event_id)
        self.discrete_header_1 = BCFactoryFloor.BcDiscreteHeaderEditsFactory(event_edit=self.event_1, collector_sample_id=discrete_header_sample_id)
        self.discrete_details_1 = BCFactoryFloor.BcDiscreteDetailEditsFactory(dis_header_edit=self.discrete_header_1, collector_sample_id=discrete_header_sample_id)

    def merge_discrete_details_test(self, dis_detail_seq):
        mission_merger = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        mission_merger.add_status_listener(status_update)
        mission_merger.merge_update_objects(mission_merger.get_update_discrete_details())

        dis_detail = biochem_models.Bcdiscretedtailedits.objects.get(dis_detail_edt_seq=dis_detail_seq)

        return dis_detail

    @tag('test_merge_discrete_replicates_does_not_exist_batch')
    def test_merge_discrete_replicates_does_not_exist_batch(self):
        # test that replicates attached to an incoming details object are reassigned to the details object that already
        # existed, but didn't contain any replicates before a merge
        discrete_replicate_1 = BCFactoryFloor.BcDiscreteReplicateEditsFactory(dis_detail_edit=self.discrete_details_1)
        discrete_replicate_2 = BCFactoryFloor.BcDiscreteReplicateEditsFactory(dis_detail_edit=self.discrete_details_1)

        detail = self.merge_discrete_details_test(self.discrete_details_0.dis_detail_edt_seq)
        updated_discrete_replicate_1 = biochem_models.Bcdisreplicatedits.objects.get(dis_repl_edt_seq=discrete_replicate_1.dis_repl_edt_seq)
        updated_discrete_replicate_2 = biochem_models.Bcdisreplicatedits.objects.get(dis_repl_edt_seq=discrete_replicate_2.dis_repl_edt_seq)

        self.assertEqual(detail.discrete_replicate_edits.count(), 2)
        self.assertEqual(updated_discrete_replicate_1.batch.pk, detail.batch.pk)
        self.assertEqual(updated_discrete_replicate_2.batch.pk, detail.batch.pk)

    @tag('test_merge_discrete_replicates_does_exist_batch')
    def test_merge_discrete_replicates_does_exist_batch(self):
        # if the Discrete Detail object the replicates are being attached to already has replicates, the
        # existing replicates should be removed and replaced by the new replicates
        old_replicate_1 = BCFactoryFloor.BcDiscreteReplicateEditsFactory(discrete_replicate_seq=101, dis_detail_edit=self.discrete_details_0)
        old_replicate_2 = BCFactoryFloor.BcDiscreteReplicateEditsFactory(discrete_replicate_seq=102,dis_detail_edit=self.discrete_details_0)

        discrete_replicate_1 = BCFactoryFloor.BcDiscreteReplicateEditsFactory(dis_detail_edit=self.discrete_details_1)
        discrete_replicate_2 = BCFactoryFloor.BcDiscreteReplicateEditsFactory(dis_detail_edit=self.discrete_details_1)

        detail = biochem_models.Bcdiscretedtailedits.objects.get(dis_detail_edt_seq=self.discrete_details_0.dis_detail_edt_seq)

        self.assertEqual(detail.discrete_replicate_edits.count(), 2)
        self.assertEqual(old_replicate_1.batch.pk, detail.batch.pk)
        self.assertEqual(old_replicate_2.batch.pk, detail.batch.pk)

        detail = self.merge_discrete_details_test(self.discrete_details_0.dis_detail_edt_seq)
        updated_discrete_replicate_1 = biochem_models.Bcdisreplicatedits.objects.get(dis_repl_edt_seq=discrete_replicate_1.dis_repl_edt_seq)
        updated_discrete_replicate_2 = biochem_models.Bcdisreplicatedits.objects.get(dis_repl_edt_seq=discrete_replicate_2.dis_repl_edt_seq)

        self.assertEqual(detail.discrete_replicate_edits.count(), 2)
        self.assertEqual(updated_discrete_replicate_1.batch.pk, detail.batch.pk)
        self.assertEqual(updated_discrete_replicate_2.batch.pk, detail.batch.pk)


@tag('test_merge_bio_tables', 'test_merge_plankton')
class TestPlanktonHeaderMerge(TestCase):
    # we won't be merging plankton. It's not a bunch of separate variables like Discrete data is, when it gets uploaded
    # it's typically all or none. We'll keep the same process for merging mission and event data, but we'll remove old
    # plankton headers and point the new plankton headers at the existing mission events that was just updated

    @classmethod
    def setUpClass(cls):
        utilities.create_model_table(unmanaged_models)

    @classmethod
    def tearDownClass(cls):
        utilities.delete_model_table(unmanaged_models)

    def setUp(self):
        descriptor = "MVP112025"
        collector_event_id = "001"
        discrete_header_sample_id = 450000
        self.bad_data_center = BCFactoryFloor.BcDataCenterFactory(data_center_code=23, name="BIO_INREVIEW")
        self.data_type = BCFactoryFloor.BcDataTypeFactory()

        self.mission_0 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.event_0 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_0,
                                                          collector_event_id=collector_event_id)
        self.activity_0 = BCFactoryFloor.BcActivityEditsFactory(event_edit=self.event_0, data_pointer_code="PL")
        self.mission_1 = BCFactoryFloor.BcMissionEditsFactory(descriptor=descriptor)
        self.event_1 = BCFactoryFloor.BcEventEditsFactory(mission_edit=self.mission_1,
                                                          collector_event_id=collector_event_id)

    @tag('test_merge_plankton_header_does_not_exist')
    def test_merge_plankton_header_does_not_exist(self):
        plankton_header = BCFactoryFloor.BcPlanktonHeaderEditsFactory(event_edit=self.event_1)

        merge = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        plankton_headers = merge.get_update_events()
        merge.merge_update_objects(plankton_headers)

        updated_header = biochem_models.Bcplanktnhedredits.objects.using("default").get(pl_headr_edt_seq=plankton_header.pl_headr_edt_seq)
        self.assertEqual(updated_header.batch.pk, self.mission_0.batch.pk)


    @tag('test_merge_plankton_header_does_not_exist')
    def test_merge_plankton_header_remove_existing(self):
        old_plankton_header = BCFactoryFloor.BcPlanktonHeaderEditsFactory(event_edit=self.event_0)
        new_plankton_header = BCFactoryFloor.BcPlanktonHeaderEditsFactory(event_edit=self.event_1)

        merge = MergeTables.MergeMissions(self.mission_0, self.mission_1, database='default')
        plankton_headers = merge.get_update_events()
        merge.merge_update_objects(plankton_headers)

        updated_header = biochem_models.Bcplanktnhedredits.objects.using("default").get(pl_headr_edt_seq=new_plankton_header.pl_headr_edt_seq)
        old_header = biochem_models.Bcplanktnhedredits.objects.using("default").filter(pl_headr_edt_seq=old_plankton_header.pl_headr_edt_seq)
        self.assertEqual(updated_header.batch.pk, self.mission_0.batch.pk)
        self.assertFalse(old_header.exists())