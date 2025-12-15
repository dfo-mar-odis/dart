from settingsdb import models

def consolidate():
    configs = models.SampleTypeConfig.objects.all()

    # Group configs by their common attributes
    grouped_configs = {}

    for config in configs:
        # Create a key based on the common fields
        key = (
            config.file_type,
            config.skip,
            config.sample_field,
            config.tab,
            config.allow_blank,
            config.allow_replicate
        )

        if key not in grouped_configs:
            grouped_configs[key] = []
        grouped_configs[key].append(config)

    keys = set(grouped_configs.keys())

    new_samplefiletypes = []
    for item, key in enumerate(keys):
        new_sft = models.SampleFileType(
            name=f"config_{item}",
            file_type=key[0].upper(),
            skip=int(key[1]),
            sample_field=key[2].upper(),
            tab=int(key[3]),
            comment_field="COMMENTS",
            are_blank_sample_ids_replicates=key[4],
            allowed_replicates=1 if key[5] else 0
        )
        new_samplefiletypes.append(new_sft)
    models.SampleFileType.objects.bulk_create(new_samplefiletypes)

    # Process each group
    for group in grouped_configs.values():
        if len(group) > 0:
            print(group[0])

            sample_file_type = models.SampleFileType.objects.get(
                file_type__iexact=group[0].file_type,
                skip=group[0].skip,
                tab=group[0].tab,
                sample_field__iexact=group[0].sample_field,
                are_blank_sample_ids_replicates=group[0].allow_blank,
            )

            # Keep the first config as primary
            primary_config = group[0]

            if "config_" in sample_file_type.name:
                sample_file_type.name = primary_config.sample_type.short_name
                sample_file_type.save()

            # Create a variable for the primary config first
            models.SampleTypeVariable.objects.create(
                sample_type=sample_file_type,
                name=primary_config.sample_type.short_name,
                value_field=primary_config.value_field,
                flag_field=primary_config.flag_field,
                limit_field=primary_config.limit_field,
                datatype=primary_config.sample_type.datatype.pk
            )

            # Process duplicates if any
            if len(group) > 1:
                for duplicate in group[1:]:
                    # Create a variable for each duplicate
                    models.SampleTypeVariable.objects.create(
                        sample_type=sample_file_type,
                        value_field=duplicate.value_field,
                        flag_field=duplicate.flag_field,
                        limit_field=duplicate.limit_field,
                        datatype = duplicate.sample_type.datatype.pk
                    )