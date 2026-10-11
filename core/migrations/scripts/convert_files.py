from typing import Callable

from django.utils import timezone

# Used in 0025_remove_filetype_extension_alter_file_type_description_and_more to convert files from
# Actions (event files), Sample (sensor and sample), PlanktonSample (plankton) to MissionFiles

def convert_files(apps, mission, files, file_type: Callable):
    MissionFile = apps.get_model('core', 'MissionFile')
    new_files = []
    file_name_set = set()

    for f in files:
        if f is None or f in file_name_set:
            continue

        mission_file = MissionFile(
            mission=mission, filename=f, type=file_type(f), last_loaded=timezone.now()
        )
        new_files.append(mission_file)
        file_name_set.add(f)

        if len(new_files) > 1000:
            MissionFile.objects.bulk_create(new_files)
            new_files = []

    MissionFile.objects.bulk_create(new_files)


def convert_action_files(mission, apps):
    Action = apps.get_model('core', 'Action')
    files = Action.objects.values_list("file", flat=True).distinct()
    convert_files(apps, mission, files, lambda f: 1)


def convert_sensor_sample_files(mission, apps):
    Sample = apps.get_model('core', 'Sample')

    files = Sample.objects.values_list("file", flat=True).distinct()
    convert_files(apps, mission, files, lambda f: 2 if f.upper().endswith(('.BTL', '.ROS')) else 3)


def convert_plankton_files(mission, apps):
    PlanktonSample = apps.get_model('core', 'PlanktonSample')

    files = PlanktonSample.objects.values_list("file", flat=True).distinct()
    convert_files(apps, mission, files, lambda f: 4)


def migrate_event_file_to_mission_file(apps, schema_editor):
    mission = apps.get_model('core', 'Mission').objects.first()
    convert_action_files(mission, apps)
    convert_sensor_sample_files(mission, apps)
    convert_plankton_files(mission, apps)

# for migration 0026
# a FileObject must have a filename field with a file in the MissionFile table, and a file field intended to
# be linked to the FileObject
def link_files(apps, FileObject, file_filter: list, get_file_name: Callable = lambda a: a.filename):
    MissionFile = apps.get_model('core', 'MissionFile')

    event_files = { ef.filename: ef for ef in MissionFile.objects.filter(type__in=file_filter) }
    updated = []
    for a in FileObject.objects.all():
        file_name = get_file_name(a)
        if file_name is None:
            continue

        a.file = event_files[file_name]
        updated.append(a)

        if len(updated) > 1000:
            FileObject.objects.bulk_update(updated, ["file"])
            updated = []

    FileObject.objects.bulk_update(updated, ['file'])

def migrate_to_mission_file_link_files(apps, schema_editor):
    Action = apps.get_model('core', 'Action')
    link_files(apps, Action, [1])

    PlanktonSample = apps.get_model('core', 'PlanktonSample')
    link_files(apps, PlanktonSample, [4])

    DiscreteSampleValue = apps.get_model('core', 'DiscreteSampleValue')
    link_files(apps, DiscreteSampleValue, [2, 3], lambda a: a.sample.filename)