import datetime
import decimal

import factory
import random

from django.utils import timezone
from factory.django import DjangoModelFactory
from faker import Faker

from biochem import models

faker = Faker()


class BcdDFactory(DjangoModelFactory):
    '''
    Factory for BcdD - will require a valid BioChem Datatype (dis_detail_data_type_seq), the data_type_method
     and a batch_seq to build data in bulk

    common dis_detail_data_type_seq:
    dis_detail_data_type_seq | data_type_method
                    90000203 | O2_Winkler_Auto
                    90000105 | Salinity_Sal_PSS

    '''

    class Meta:
        model = models.BcdDReportModel
        database = 'biochem'


    dis_data_num = factory.sequence(lambda n: n+1)
    mission_descriptor = factory.lazy_attribute(lambda o: faker.word())

    event_collector_event_id = factory.lazy_attribute(lambda o: f'{faker.random.randint(0, 100):03d}')
    event_collector_stn_name = factory.lazy_attribute(lambda o: faker.word())
    dis_header_start_depth = factory.lazy_attribute(lambda o: faker.pyfloat(left_digits=1, right_digits=2))
    dis_header_end_depth = factory.lazy_attribute(lambda o: o.dis_header_start_depth +
                                                            faker.pyfloat(min_value=60, max_value=5000))
    dis_header_slat = factory.lazy_attribute(lambda o: faker.pyfloat(left_digits=3, right_digits=5,
                                                                     min_value=-90, max_value=90))
    dis_header_slon = factory.lazy_attribute(lambda o: faker.pyfloat(left_digits=3, right_digits=5,
                                                                     min_value=-180, max_value=180))
    dis_header_sdate = factory.lazy_attribute(lambda o: faker.date())
    dis_header_stime = factory.lazy_attribute(lambda o: f'{faker.random.randint(0, 59):02d}{faker.random.randint(0, 59):02d}{faker.random.randint(0, 59):02d}')

    dis_detail_data_value = factory.lazy_attribute(lambda o: faker.pyfloat(left_digits=2, right_digits=3))
    dis_detail_data_qc_code = 0
    dis_detail_detection_limit = 0
    dis_detail_detail_collector = factory.lazy_attribute(lambda o: faker.name())
    dis_sample_key_value = factory.lazy_attribute(lambda o: f'{faker.random.randint(1000, 100000)}')
    dis_detail_collector_samp_id = factory.lazy_attribute(
        lambda o: f'{o.mission_descriptor}_{o.event_collector_event_id}_{o.dis_sample_key_value}')
    created_by = factory.lazy_attribute(lambda o: faker.word())
    created_date = datetime.datetime.now()
    data_center_code = 20  # 20 is BIO
