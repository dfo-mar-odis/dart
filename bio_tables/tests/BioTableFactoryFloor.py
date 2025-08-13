import factory
from bio_tables import models as bio_models
from faker import Faker

faker = Faker()


class BCDataCenterFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = bio_models.BCDataCenter
        django_get_or_create = ('data_center_code',)

    data_center_code = factory.Sequence(lambda n: n + 1)
    name = factory.lazy_attribute(lambda _: faker.company())
    location = factory.lazy_attribute(lambda _: faker.city())
    description = factory.lazy_attribute(lambda _: faker.sentence(nb_words=10))


class BCUnitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = bio_models.BCUnit

    unit_seq = factory.Sequence(lambda n: n + 1)
    data_center_code = factory.SubFactory(BCDataCenterFactory)
    name = factory.lazy_attribute(lambda _: faker.word())
    description = factory.lazy_attribute(lambda _: faker.sentence(nb_words=10))


class BCDataRetrievalFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = bio_models.BCDataRetrieval

    data_retrieval_seq = factory.Sequence(lambda n: n + 1)
    data_center_code = factory.SubFactory(BCDataCenterFactory)
    parameter_name = factory.lazy_attribute(lambda _: faker.word())
    parameter_description = factory.lazy_attribute(lambda _: faker.sentence())
    unit_seq = factory.SubFactory(BCUnitFactory)
    places_before = factory.lazy_attribute(lambda _: faker.random_int(min=0, max=5))
    places_after = factory.lazy_attribute(lambda _: faker.random_int(min=0, max=5))
    minimum_value = factory.lazy_attribute(lambda _: faker.pydecimal(left_digits=7, right_digits=5, positive=True))
    maximum_value = factory.lazy_attribute(lambda _: faker.pydecimal(left_digits=7, right_digits=5, positive=True))
    originally_entered_by = factory.lazy_attribute(lambda _: faker.name())


class BCAnalysisFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = bio_models.BCAnalysis

    analysis_seq = factory.Sequence(lambda n: n + 1)
    data_center_code = factory.SubFactory(BCDataCenterFactory)
    name = factory.lazy_attribute(lambda _: faker.word())
    description = factory.lazy_attribute(lambda _: faker.sentence(nb_words=10))


class BCSampleHandlingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = bio_models.BCSampleHandling

    sample_handling_seq = factory.Sequence(lambda n: n + 1)
    data_center_code = factory.SubFactory(BCDataCenterFactory)
    name = factory.lazy_attribute(lambda _: faker.word())
    description = factory.lazy_attribute(lambda _: faker.sentence(nb_words=10))


class BCPreservationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = bio_models.BCPreservation

    preservation_seq = factory.Sequence(lambda n: n + 1)
    data_center_code = factory.SubFactory(BCDataCenterFactory)
    name = factory.lazy_attribute(lambda _: faker.word())
    description = factory.lazy_attribute(lambda _: faker.sentence(nb_words=10))
    type = factory.lazy_attribute(lambda _: faker.word())


class BCStorageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = bio_models.BCStorage

    storage_seq = factory.Sequence(lambda n: n + 1)
    data_center_code = factory.SubFactory(BCDataCenterFactory)
    name = factory.lazy_attribute(lambda _: faker.word())
    description = factory.lazy_attribute(lambda _: faker.sentence(nb_words=10))


class BCDataTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = bio_models.BCDataType

    data_type_seq = factory.Sequence(lambda n: n + 1)
    data_center_code = factory.SubFactory(BCDataCenterFactory)
    data_retrieval = factory.SubFactory(BCDataRetrievalFactory)
    analysis = factory.SubFactory(BCAnalysisFactory)
    preservation = factory.SubFactory(BCPreservationFactory)
    sample_handling = factory.SubFactory(BCSampleHandlingFactory)
    storage = factory.SubFactory(BCStorageFactory)
    unit = factory.SubFactory(BCUnitFactory)
    description = factory.lazy_attribute(lambda _: faker.sentence())
    conversion_equation = factory.lazy_attribute(lambda _: faker.sentence())
    originally_entered_by = factory.lazy_attribute(lambda _: faker.name())
    method = factory.lazy_attribute(lambda _: faker.word())
    priority = factory.lazy_attribute(lambda _: faker.random_int(min=1, max=10))
    p_code = factory.lazy_attribute(lambda _: faker.lexify(text='????'))
    bodc_code = factory.lazy_attribute(lambda _: faker.lexify(text='??????????'))