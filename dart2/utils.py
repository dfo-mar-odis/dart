import os.path

import pandas as pd
from bs4 import BeautifulSoup

from core import models as core_models
from dart2 import settings

import logging

logger = logging.getLogger('dart')


def convertDMS_degs(dms_string):
    dms = dms_string.split()
    nsew = dms[2].upper()  # north, south, east, west
    degs = (float(dms[0]) + float(dms[1]) / 60) * (-1 if (nsew == 'S' or nsew == 'W') else 1)

    return degs


def convertDegs_DMS(dd):
    d = int(dd)
    m = float((dd - d) * 60.0)

    return [d, m]


def load_svg(svg_name: str):
    file = os.path.join(settings.STATIC_ROOT, settings.BS_ICONS_CUSTOM_PATH,
                        svg_name + ("" if svg_name.endswith('.svg') else ".svg"))

    if not os.path.isfile(file):
        file = os.path.join(settings.BASE_DIR, settings.STATIC_URL, settings.BS_ICONS_CUSTOM_PATH,
                            svg_name + ("" if svg_name.endswith('.svg') else ".svg"))
        if not os.path.isfile(file):
            raise FileNotFoundError

    with open(file, 'r') as fp:
        svg_icon = fp.read()

    return svg_icon


def parse_csv_sample_file(mission: core_models.Mission, sample_type: core_models.SampleType,
                          dataframe: pd.DataFrame, sample_id_column: int, sample_value_column):

    slim_data: pd.DataFrame = dataframe.iloc[:, [sample_id_column, sample_value_column]]

    create_samples = []
    create_discrete_values = []
    for i in range(len(slim_data)):
        sample_id = slim_data.iloc[i, 0]
        value = slim_data.iloc[i, 1]

        sample = sample_id.split("_")
        bottle = core_models.Bottle.objects.get(event__mission=mission, bottle_id=int(sample[0]))
        new_sample = core_models.Sample(bottle=bottle, type=sample_type)
        create_samples.append(new_sample)

        new_sample_discrete = core_models.DiscreteSampleValue(sample=new_sample, value=value, replicate=sample[1])
        create_discrete_values.append(new_sample_discrete)

    core_models.Sample.objects.bulk_create(create_samples)
    core_models.DiscreteSampleValue.objects.bulk_create(create_discrete_values)