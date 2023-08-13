import pandas as pd

from core import models as core_models

import logging

logger = logging.getLogger('dart')


def parse_csv_sample_file(mission: core_models.Mission, sample_type: core_models.SampleType,
                          file_settings: core_models.SampleFileSettings, file_name: str, dataframe: pd.DataFrame):

    create_samples = {}
    create_discrete_values = []
    for i in range(dataframe.shape[0]):
        sample_id = dataframe[file_settings.sample_field][i]
        value = dataframe[file_settings.value_field][i]

        sample = sample_id.split("_")
        bottle = core_models.Bottle.objects.get(event__mission=mission, bottle_id=int(sample[0]))

        db_sample = core_models.Sample(bottle=bottle, type=sample_type, file=file_name)
        if bottle.bottle_id in create_samples:
            db_sample = create_samples[bottle.bottle_id]

        if file_settings.comment_field:
            db_sample.comment = dataframe[file_settings.comment_field][i]

        create_samples[bottle.bottle_id] = db_sample
        new_sample_discrete = core_models.DiscreteSampleValue(sample=db_sample, value=value, replicate=sample[1])
        create_discrete_values.append(new_sample_discrete)

    core_models.Sample.objects.bulk_create(create_samples.values())
    core_models.DiscreteSampleValue.objects.bulk_create(create_discrete_values)
