import datetime

import factory

from factory.django import DjangoModelFactory
from faker import Faker

from biochem import models

faker = Faker()


class BcBatchesFactory(DjangoModelFactory):
    class Meta:
        model = models.Bcbatches

    batch_seq = factory.Sequence(lambda n: n)
    name = factory.lazy_attribute(lambda o: faker.name())
    username = factory.lazy_attribute(lambda o: o.name.upper())


class BcDataCenterFactory(DjangoModelFactory):
    class Meta:
        model = models.Bcdatacenters
        django_get_or_create = ("data_center_code",)


class BcMissionEditsFactory(DjangoModelFactory):
    class Meta:
        model = models.Bcmissionedits

    mission_edt_seq = factory.Sequence(lambda n: 200000000 + n)
    data_center = factory.SubFactory(BcDataCenterFactory, data_center_code=20, name="BIO")
    batch = factory.SubFactory(BcBatchesFactory)

    descriptor = factory.lazy_attribute(lambda o: faker.name())


class BcEventEditsFactory(DjangoModelFactory):
    class Meta:
        model = models.Bceventedits

    event_edt_seq = factory.Sequence(lambda n: 300000000 + n)
    mission_edit = factory.SubFactory(BcMissionEditsFactory)
    data_center = factory.lazy_attribute(lambda o: o.mission_edit.data_center)
    batch = factory.lazy_attribute(lambda o: o.mission_edit.batch)


class BcActivityEditsFactory(DjangoModelFactory):
    class Meta:
        model = models.Bcactivityedits

    activity_edt_seq = factory.Sequence(lambda n: 400000000 + n)
    event_edit = factory.SubFactory(BcEventEditsFactory)
    data_center = factory.lazy_attribute(lambda o: o.event_edit.data_center)
    batch = factory.lazy_attribute(lambda o: o.event_edit.batch)


class BcDiscreteHeaderEditsFactory(DjangoModelFactory):
    class Meta:
        model = models.Bcdiscretehedredits

    dis_headr_edt_seq = factory.Sequence(lambda n: 500000000 + n)
    event_edit = factory.SubFactory(BcEventEditsFactory)
    data_center = factory.lazy_attribute(lambda o: o.event_edit.data_center)
    batch = factory.lazy_attribute(lambda o: o.event_edit.batch)


class BcDataTypeFactory(DjangoModelFactory):
    class Meta:
        model = models.Bcdatatypes
        django_get_or_create = ("data_type_seq",)

    data_type_seq = 10001
    data_center = factory.SubFactory(BcDataCenterFactory, data_center_code=20, name="BIO")

    data_retrieval_seq = 10001
    analysis_seq = 20001
    preservation_seq = 30001
    sample_handling_seq = 40001
    storage_seq = 50001
    unit_seq = 60001
    description = "some description"
    conversion_equation = "An equation"
    originally_entered_by = "Upsonp"
    method = "A method"
    priority = 1
    p_code = "asdf"
    bodc_code = "ACodeOfSomeKind"


class BcDiscreteDetailEditsFactory(DjangoModelFactory):
    class Meta:
        model = models.Bcdiscretedtailedits

    dis_detail_edt_seq = factory.Sequence(lambda n: 600000000 + n)
    dis_header_edit = factory.SubFactory(BcDiscreteHeaderEditsFactory)
    collector_sample_id = factory.lazy_attribute(lambda o: o.dis_header_edit.collector_sample_id)
    data_type = factory.SubFactory(BcDataTypeFactory)
    data_center = factory.lazy_attribute(lambda o: o.dis_header_edit.data_center)
    batch = factory.lazy_attribute(lambda o: o.dis_header_edit.batch)


class BcDiscreteReplicateEditsFactory(DjangoModelFactory):
    class Meta:
        model = models.Bcdisreplicatedits

    dis_repl_edt_seq = factory.Sequence(lambda n: 700000000 + n)
    dis_detail_edit = factory.SubFactory(BcDiscreteDetailEditsFactory)
    collector_sample_id = factory.lazy_attribute(lambda o: o.dis_detail_edit.collector_sample_id)
    data_type = factory.lazy_attribute(lambda o: o.dis_detail_edit.data_type)
    data_center = factory.lazy_attribute(lambda o: o.dis_detail_edit.data_center)
    batch = factory.lazy_attribute(lambda o: o.dis_detail_edit.batch)


class BcPlanktonHeaderEditsFactory(DjangoModelFactory):
    class Meta:
        model = models.Bcplanktnhedredits

    pl_headr_edt_seq = factory.Sequence(lambda n: 500000000 + n)
    plankton_seq = factory.Sequence(lambda n: 510000000 + n)
    event_edit = factory.SubFactory(BcEventEditsFactory)
    data_center = factory.lazy_attribute(lambda o: o.event_edit.data_center)
    batch = factory.lazy_attribute(lambda o: o.event_edit.batch)


class BcMoreCommentEditsEventFactory(DjangoModelFactory):
    class Meta:
        model = models.Bccommentedits

    comment_edt_seq = factory.Sequence(lambda n: 600000000 + n)
    comment_seq = factory.Sequence(lambda n: 610000000 + n)
    event_edit = factory.SubFactory(BcEventEditsFactory)
    data_center = factory.lazy_attribute(lambda o: o.event_edit.data_center)
    batch = factory.lazy_attribute(lambda o: o.event_edit.batch)


class BcMoreCommentEditsMissionFactory(DjangoModelFactory):
    class Meta:
        model = models.Bccommentedits

    comment_edt_seq = factory.Sequence(lambda n: 600000000 + n)
    mission_edit = factory.SubFactory(BcMissionEditsFactory)
    data_center = factory.lazy_attribute(lambda o: o.mission_edit.data_center)
    batch = factory.lazy_attribute(lambda o: o.mission_edit.batch)


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
        model = models.BcdD
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
    batch=factory.SubFactory(BcBatchesFactory)
