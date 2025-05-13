from django.db.models import QuerySet

from settingsdb.models import FileConfiguration

def _get_or_create_file_config(file_type, fields) -> QuerySet[FileConfiguration]:
    existing_mappings = FileConfiguration.objects.filter(file_type=file_type)

    create_mapping = []
    for field in fields:
        if not existing_mappings.filter(required_field=field[0]).exists():
            mapping = FileConfiguration(file_type=file_type)
            mapping.required_field = field[0]
            mapping.mapped_field = field[1]
            mapping.description = field[2]
            create_mapping.append(mapping)

    if len(create_mapping) > 0:
        FileConfiguration.objects.bulk_create(create_mapping)

    return existing_mappings
