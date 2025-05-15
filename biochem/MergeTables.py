import time

from biochem import models

import logging

logger = logging.getLogger('dart.debug')


# _merge_dictionaries takes a left and right dictionary, they're assumed to be in the same format and that the
# right dictionary is being merged *into* the left dictionary.
#
# The dictionary formats are expected to be:
# dict = {
#   biochem_model: {
#       'objects': set([objects that will be bulk updated later]),
#       'fields': set([fields passed to the bulk update function])
#   }
# }
#
# The right dictionary should have no more than one field and contain objects
# where only that one field has been modified.
def _merge_dictionaries(update_dict: dict, new_dict: dict) -> None:
    if new_dict is None:
        return

    for new_key in new_dict.keys():
        if new_key not in update_dict:
            update_dict[new_key] = new_dict[new_key]
        else:
            # start by merging the fields we'll be updating, that's an easy win
            new_field = new_dict[new_key]['fields'].pop()
            update_dict[new_key]['fields'].update([new_field])

            # if an object in the new dictionary already exists in the update_dict then we have to merge the
            # fields that are different in the new object into the update_dict object, otherwise we just override
            # whatever changes were already made to the object in the update_dict
            for primary_key, new_object in new_dict[new_key]['update_objects'].items():
                if primary_key not in update_dict[new_key]['update_objects'].keys():
                    update_dict[new_key]['update_objects'][primary_key] = new_object
                elif hasattr(new_object, new_field):
                    update_object = update_dict[new_key]['update_objects'][primary_key]
                    setattr(update_object, new_field, getattr(new_object, new_field))


# _merge_objects is used to update an object only if the field on the current object and new object is different
# if the current object is modified it is added to the update_dict that is expected to follow the format:
# dict = {
#   biochem_model: {
#       'objects': set([objects that will be bulk updated later]),
#       'fields': set([fields passed to the bulk update function])
#   }
# }
def _merge_objects(update_dict, current_object, new_object, field):
    setattr(current_object, field, getattr(new_object, field))
    update_dict[current_object._meta.model]['update_objects'][current_object.pk] = current_object
    update_dict[current_object._meta.model]['fields'].update([field])


class MergeMissions:
    status_listeners: [] = None

    database = None

    mission_0: models.Bcmissionedits = None
    mission_1: models.Bcmissionedits = None

    status = None

    def __init__(self, mission_0: models.Bcmissionedits, mission_1: models.Bcmissionedits, database='biochem'):
        self.database = database
        self.mission_0 = mission_0
        self.mission_1 = mission_1
        self.status_listeners = list()

    def add_status_listener(self, status_update):
        self.status_listeners.append(status_update)

    def update_status(self, message: str, current: int = 0, max: int = 0):
        for listener in self.status_listeners:
            listener(message, current, max)

    def safety_check(self):
        # Do not merge missions that have different mission_descriptors
        if self.mission_0.descriptor != self.mission_1.descriptor:
            self.update_status("Failed to merge missions")
            raise ValueError("Cannot merge missions with different mission descriptors")

        # Only merge missions part of Data Center 20 "BIO"
        if (self.mission_0.data_center.data_center_code != 20 or
                self.mission_1.data_center.data_center_code != 20):
            self.update_status("Failed to merge missions")
            raise ValueError("Can only merge missions with a data center of 20")

    def get_update_reference_field(self, field, bc_object, new_value) -> None | dict:

        # if the object does not have a reference to field, do nothing with it, but we will check to see if it
        # has children that have references to the reference field
        if not hasattr(bc_object, field):
            update_dict = {}
            for key, field_map in bc_object._meta.fields_map.items():
                if hasattr(field_map.related_model, field):
                    for sub_obj in getattr(bc_object, key).all():
                        n_dict = self.get_update_reference_field(field, sub_obj, new_value)
                        if update_dict == {}:
                            update_dict = n_dict
                        else:
                            _merge_dictionaries(update_dict, n_dict)

            return None if update_dict == {} else update_dict

        # if the object does have an event_edit field, update it to the new event_edit field and add it to the
        # dictionary to be returned and merged with other objects
        setattr(bc_object, field, new_value)
        update_dict: dict = {
            bc_object._meta.model: {
                'update_objects': {bc_object.pk: bc_object},
                'fields': {field},
            },
        }

        # check related models that reference this bc_object, if they have the field we're modifying, then we'll
        # modify their fields as well and merge the returned dictionary into this update_dict to be saved later
        for key, field_map in bc_object._meta.fields_map.items():
            if hasattr(field_map.related_model, field):
                for sub_obj in getattr(bc_object, key).all():
                    n_dict = self.get_update_reference_field(field, sub_obj, new_value)
                    _merge_dictionaries(update_dict, n_dict)

        return update_dict

    def merge_update_objects(self, updated_objects: dict):
        self.update_status("Merging Discrete Headers")

        self.safety_check()

        for key, update in updated_objects.items():
            if 'delete_objects' in update:
                update['delete_objects'].delete()

            if len(update['update_objects']) > 0:
                key.objects.using(self.database).bulk_update(list(update['update_objects'].values()),
                                                             fields=update['fields'])

    def get_update_discrete_details(self) -> dict:
        update_dict: dict = {
            models.Bcdiscretedtailedits: {
                'update_objects': dict(),
                'fields': set(),
            },
            models.Bcdisreplicatedits: {
                'update_objects': dict(),
                'fields': set(),
            }
        }

        exclude_fields = ['dis_detail_edt_seq', 'discrete_detail', 'data_center', 'data_type', 'discrete', 'collector_sample_id', 'dis_header_edit', 'batch', 'last_update_by', 'last_update_date', 'process_flag', 'prod_created_date']
        check_fields = [f.name for f in models.Bcdiscretedtailedits._meta.fields if f.name not in exclude_fields]

        details = models.Bcdiscretedtailedits.objects.using(self.database).filter(batch=self.mission_1.batch)
        mission_1_headers = [detail.dis_header_edit.collector_sample_id for detail in details]
        mission_0_headers = models.Bcdiscretehedredits.objects.using(self.database).filter(
            batch=self.mission_0.batch,
            collector_sample_id__in=mission_1_headers
        )
        max_details = details.count()
        delete_replicates = []
        for detail_index, detail in enumerate(details):
            self.update_status("Merging Discrete Details", detail_index, max_details)
            header = mission_0_headers.get(collector_sample_id=detail.dis_header_edit.collector_sample_id)
            try:
                existing_detail = header.discrete_detail_edits.get(
                    collector_sample_id=detail.collector_sample_id,
                    data_type=detail.data_type
                )
                updated = False
                fields = filter(lambda field: getattr(existing_detail, field, None) != getattr(detail, field, None), check_fields)
                for field in fields:
                    _merge_objects(update_dict, existing_detail, detail, field)
                    updated = True

                if updated:
                    _merge_objects(update_dict, existing_detail, detail, 'last_update_by')
                    _merge_objects(update_dict, existing_detail, detail, 'last_update_date')
                    _merge_objects(update_dict, existing_detail, detail, 'process_flag')

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
                if existing_detail.discrete_replicate_edits.exists():
                    delete_replicates += list(existing_detail.discrete_replicate_edits.values_list(
                        'discrete_replicate_seq', flat=True
                    ))

                if detail.discrete_replicate_edits.exists():

                    for replicate in detail.discrete_replicate_edits.all():
                        replicate.dis_detail_edit = existing_detail
                        update_dict[models.Bcdisreplicatedits]['fields'].update(['dis_detail_edit'])

                        # update batch ids for all related objects that reference the event being merged
                        n_dict = self.get_update_reference_field("batch", replicate, self.mission_0.batch)
                        _merge_dictionaries(update_dict, n_dict)

            except models.Bcdiscretedtailedits.DoesNotExist:
                # if the detail doesn't exist in the specified details list, then we'll update the dis_header_edit for
                # the detail and update the Batch_ID. We'll have to update the batch id for all things attached
                # to the detail as well.
                detail.dis_header_edit = header
                update_dict[models.Bcdiscretedtailedits]['fields'].update(['dis_header_edit'])

                # update batch ids for all related objects that reference the event being merged
                n_dict = self.get_update_reference_field("batch", detail, self.mission_0.batch)
                _merge_dictionaries(update_dict, n_dict)

        update_dict[models.Bcdisreplicatedits]['delete_objects'] = (
            models.Bcdisreplicatedits.objects.using(self.database).filter(discrete_replicate_seq__in=delete_replicates))
        return update_dict

    def get_update_discrete_headers(self) -> dict:
        update_dict: dict = {
            models.Bcdiscretehedredits: {
                'update_objects': dict(),
                'fields': set(),
            },
        }

        exclude_fields = ['dis_headr_edt_seq', 'discrete', 'data_center', 'event', 'activity', 'collector_sample_id', 'event_edit', 'activity_edit', 'batch', 'last_update_by', 'last_update_date', 'process_flag', 'prod_created_date']
        check_fields = [f.name for f in models.Bcdiscretehedredits._meta.fields if f.name not in exclude_fields]

        headers = models.Bcdiscretehedredits.objects.using(self.database).filter(batch=self.mission_1.batch)
        mission_1_events = self.mission_1.event_edits.values_list('collector_event_id', flat=True)
        mission_0_events = {
            mission.collector_event_id: mission for mission in
            self.mission_0.event_edits.filter(collector_event_id__in=mission_1_events)
        }
        max_headers = headers.count()
        for header_index, header in enumerate(headers):
            self.update_status("Merging Discrete Header", header_index, max_headers)
            event = mission_0_events[header.event_edit.collector_event_id]
            try:
                existing_header = event.discrete_header_edits.get(collector_sample_id=header.collector_sample_id)
                fields = filter(lambda field: getattr(existing_header, field, None) != getattr(header, field, None), check_fields)
                updated = False
                for field in fields:
                    _merge_objects(update_dict, existing_header, header, field)
                    updated = True

                if updated:
                    _merge_objects(update_dict, existing_header, header, 'last_update_by')
                    _merge_objects(update_dict, existing_header, header, 'last_update_date')
                    _merge_objects(update_dict, existing_header, header, 'process_flag')
            except models.Bcdiscretehedredits.DoesNotExist:
                # if the header doesn't exist in the specified event, then we'll update the event_edits for the
                # header and update the Batch_ID. We'll have to update the batch id for all things attached
                # to the header as well.
                header.event_edit = event
                update_dict[models.Bcdiscretehedredits]['fields'].update(['event_edit'])

                # update batch ids for all related objects that reference the event being merged
                n_dict = self.get_update_reference_field("batch", header, self.mission_0.batch)
                _merge_dictionaries(update_dict, n_dict)

        return update_dict

    def get_update_events(self) -> dict:
        update_dict: dict = {
            models.Bceventedits: {
                'update_objects': dict(),
                'fields': set(),
            },
            models.Bccommentedits: {
                'update_objects': dict(),
                'fields': set(),
            },
            models.Bcplanktnhedredits: {
                'update_objects': dict(),
                'fields': set(),
            }
        }

        exclude_fields = ['event_edt_seq', 'event', 'data_center', 'mission', 'mission_edit', 'batch', 'collector_event_id', 'last_update_by', 'last_update_date', 'process_flag', 'prod_created_date']
        check_fields = [f.name for f in models.Bceventedits._meta.fields if f.name not in exclude_fields]

        events = self.mission_1.event_edits.all()
        existing_events = {event.collector_event_id: event for event in self.mission_0.event_edits.filter(
            collector_event_id__in=list(events.values_list('collector_event_id', flat=True)))}

        max_events = events.count()
        delete_comments = []
        delete_plankton = []
        for event_number, event in enumerate(events):
            self.update_status("Merging Events", event_number, max_events)

            if event.collector_event_id in existing_events:
                existing_event = existing_events[event.collector_event_id]
                fields = filter(lambda field: getattr(existing_event, field, None) != getattr(event, field, None), check_fields)
                updated = False
                for field in fields:
                    _merge_objects(update_dict, existing_event, event, field)
                    updated = True

                if updated:
                    _merge_objects(update_dict, existing_event, event, 'last_update_by')
                    _merge_objects(update_dict, existing_event, event, 'last_update_date')
                    _merge_objects(update_dict, existing_event, event, 'process_flag')

                if existing_event.plankton_header_edits.exists():
                    delete_plankton += list(existing_event.plankton_header_edits.values_list(
                        'plankton_seq', flat=True
                    ))

                if event.plankton_header_edits.exists():
                    for plankton in event.plankton_header_edits.all():
                        existing_activity = existing_event.activity_edits.get(batch=self.mission_0.batch, data_pointer_code='PL')
                        plankton.event_edit = existing_event
                        plankton.activity_edit = existing_activity
                        update_dict[models.Bcplanktnhedredits]['fields'].update(['event_edit', 'activity_edit'])

                        # update batch ids for all related objects that reference the event being merged
                        n_dict = self.get_update_reference_field("batch", plankton, self.mission_0.batch)
                        _merge_dictionaries(update_dict, n_dict)

                if existing_event.comment_edits.exists():
                    delete_comments += list(existing_event.comment_edits.values_list(
                        'comment_seq', flat=True
                    ))

                if event.comment_edits.exists():
                    for comment in event.comment_edits.all():
                        comment.event_edit = existing_event
                        update_dict[models.Bccommentedits]['fields'].update(['event_edit'])

                        # update batch ids for all related objects that reference the event being merged
                        n_dict = self.get_update_reference_field("batch", comment, self.mission_0.batch)
                        _merge_dictionaries(update_dict, n_dict)
            else:
                # if the event doesn't exist in the main mission, then we'll update the mission_edit for the
                # event and update the Batch_ID. We'll have to update the batch id for all things attached
                # to the mission as well.
                event.mission_edit = self.mission_0
                update_dict[models.Bceventedits]['fields'].update(['mission_edit'])

                # update batch ids for all related objects that reference the event being merged
                n_dict = self.get_update_reference_field("batch", event, self.mission_0.batch)
                _merge_dictionaries(update_dict, n_dict)

        update_dict[models.Bccommentedits]['delete_objects'] = (
            models.Bccommentedits.objects.using(self.database).filter(comment_seq__in=delete_comments))
        update_dict[models.Bcplanktnhedredits]['delete_objects'] = (
            models.Bcplanktnhedredits.objects.using(self.database).filter(plankton_seq__in=delete_plankton))
        return update_dict

    def merge_missions(self) -> None:
        self.update_status("Merging Missions")

        # Throw exceptions if the missions being merged don't meet specific qualifications
        self.safety_check()

        self.mission_0.name = self.mission_1.name
        self.mission_0.leader = self.mission_1.leader
        self.mission_0.sdate = self.mission_1.sdate
        self.mission_0.edate = self.mission_1.edate
        self.mission_0.institute = self.mission_1.institute
        self.mission_0.platform = self.mission_1.platform
        self.mission_0.protocol = self.mission_1.protocol
        self.mission_0.geographic_region = self.mission_1.geographic_region
        self.mission_0.collector_comment = self.mission_1.collector_comment
        self.mission_0.data_manager_comment = self.mission_1.data_manager_comment

        self.mission_0.more_comment = self.mission_1.more_comment

        # if additional comments exist in the BcCommentEdits table, they need to be deleted and replaced with
        # comments coming from the incoming mission. If the incoming mission has no comments, it's assumed the
        # additional comments are being deleted.
        self.mission_0.comment_edits.all().delete()
        if self.mission_1.comment_edits.exists():
            update_comments = []
            for comment in self.mission_1.comment_edits.all():
                comment.mission_edit = self.mission_0
                comment.batch = self.mission_0.batch
                update_comments.append(comment)

            models.Bccommentedits.objects.using(self.database).bulk_update(update_comments,
                                                                           fields=['mission_edit', 'batch'])

        self.mission_0.prod_created_date = self.mission_1.prod_created_date
        self.mission_0.created_by = self.mission_1.created_by
        self.mission_0.created_date = self.mission_1.created_date
        self.mission_0.last_update_by = self.mission_1.last_update_by
        self.mission_0.last_update_date = self.mission_1.last_update_date

        self.mission_0.save(using=self.database)

        self.update_status("Merging Events")
        self.merge_update_objects(self.get_update_events())

        self.update_status("Merging Discrete Headers")
        self.merge_update_objects(self.get_update_discrete_headers())

        self.update_status("Merging Discrete Details")
        self.merge_update_objects(self.get_update_discrete_details())
