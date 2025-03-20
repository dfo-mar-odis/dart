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
            for primary_key, new_object in new_dict[new_key]['objects'].items():
                if primary_key not in update_dict[new_key]['objects'].keys():
                    update_dict[new_key]['objects'][primary_key] = new_object
                elif hasattr(new_object, new_field):
                    update_object = update_dict[new_key]['objects'][primary_key]
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
    logger.debug(f"Start Merge Objects '{field}': {time.perf_counter()}")
    # if getattr(current_object, field) != getattr(new_object, field):
    setattr(current_object, field, getattr(new_object, field))
    update_dict[current_object._meta.model]['objects'][current_object.pk] = current_object
    update_dict[current_object._meta.model]['fields'].update([field])
    logger.debug(f"End Merge Objects '{field}': {time.perf_counter()}")


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
                'objects': {bc_object.pk: bc_object},
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

    def get_update_events(self):
        update_dict: dict = {
            models.Bceventedits: {
                'objects': dict(),
                'fields': set(),
            },
        }

        events = self.mission_1.event_edits.all()
        max_events = events.count()
        for event_number, event in enumerate(events):
            self.update_status("Merging Events", event_number, max_events)

            try:
                existing_event = self.mission_0.event_edits.get(collector_event_id=event.collector_event_id)
                _merge_objects(update_dict, existing_event, event, 'sdate')
                _merge_objects(update_dict, existing_event, event, 'edate')
                _merge_objects(update_dict, existing_event, event, 'stime')
                _merge_objects(update_dict, existing_event, event, 'etime')
                _merge_objects(update_dict, existing_event, event, 'min_lat')
                _merge_objects(update_dict, existing_event, event, 'max_lat')
                _merge_objects(update_dict, existing_event, event, 'min_lon')
                _merge_objects(update_dict, existing_event, event, 'max_lon')
                _merge_objects(update_dict, existing_event, event, 'collector_station_name')
                _merge_objects(update_dict, existing_event, event, 'utc_offset')
                _merge_objects(update_dict, existing_event, event, 'collector_comment')
                _merge_objects(update_dict, existing_event, event, 'data_manager_comment')
                _merge_objects(update_dict, existing_event, event, 'more_comment')
                _merge_objects(update_dict, existing_event, event, 'prod_created_date')
                _merge_objects(update_dict, existing_event, event, 'created_by')
                _merge_objects(update_dict, existing_event, event, 'created_date')
                _merge_objects(update_dict, existing_event, event, 'last_update_by')
                _merge_objects(update_dict, existing_event, event, 'last_update_date')
                _merge_objects(update_dict, existing_event, event, 'process_flag')

                # Todo: This type of merging doesn't take into account that a BCDiscreteHeaderEdit, BCPlanktonHeaderEdit,
                #       BCActivityEdit or BCCommentEdit might already exist in the mission we're merging this event into.
                #       If the object didn't already exist in the target mission, then this would be fine, but if it
                #       does exist we'll have to merge the details

                # update batch ids for all related objects that reference the event being merged
                # n_dict = self.get_update_reference_field("batch", event, self.mission_0.batch)
                # _merge_dictionaries(update_dict, n_dict)
                #
                # # update event_edit objects for related objects that reference the event being merged
                # n_dict = self.get_update_reference_field("event_edit", event, existing_event)
                # _merge_dictionaries(update_dict, n_dict)

            except models.Bceventedits.DoesNotExist:
                # if the event doesn't exist in the main mission, then we'll update the mission_edit for the
                # event and update the Batch_ID. We'll have to update the batch id for all things attached
                # to the mission as well.
                event.mission_edit = self.mission_0
                update_dict[models.Bceventedits]['fields'].update(['mission_edit'])

                # update batch ids for all related objects that reference the event being merged
                n_dict = self.get_update_reference_field("batch", event, self.mission_0.batch)
                _merge_dictionaries(update_dict, n_dict)

        return update_dict

    # Everything should be merged into mission_0, but the assumption I'm making is that
    # mission_0 was previously loaded to Biochem and/or had merges completed already so it
    # contains more data than mission_1.
    #
    # I'm assuming the user just uploaded mission_1 so it likely only contains a small subset
    # of events and/or data, therefore it will be faster to iterate over mission_1, add events
    # that don't exist in mission_0 or merge events that do exist in mission_0 rather than
    # iterating over events in mission_0 that don't exist in mission_1
    def merge_events(self):
        self.update_status("Merging Events")

        self.safety_check()

        updated_objects: dict = self.get_update_events()

        for key, update in updated_objects.items():
            if len(update['objects']) > 0:
                key.objects.using(self.database).bulk_update(list(update['objects'].values()), fields=update['fields'])

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

        # Todo: Additional comments stored in the more_comments table will have to be swapped to mission_0
        #       This is complicated because we'll have to figure out of comments are added, or overridden
        #       They won't have the same sequence numbers. My feeling right now is to assume more_comments
        #       from mission_1 should replace more_comments in mission_0.
        #
        self.mission_0.more_comment = self.mission_1.more_comment

        self.mission_0.prod_created_date = self.mission_1.prod_created_date
        self.mission_0.created_by = self.mission_1.created_by
        self.mission_0.created_date = self.mission_1.created_date
        self.mission_0.last_update_by = self.mission_1.last_update_by
        self.mission_0.last_update_date = self.mission_1.last_update_date

        self.mission_0.save(using=self.database)
        self.merge_events()
