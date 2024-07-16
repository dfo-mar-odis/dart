import datetime

import factory
from factory.django import DjangoModelFactory
from faker import Faker

import bio_tables.models
from settingsdb import models as settings_models

from core import models

faker = Faker()


class GlobalSampleTypeFactory(DjangoModelFactory):

    class Meta:
        model = settings_models.GlobalSampleType

    short_name = factory.lazy_attribute(lambda o: faker.word())
    long_name = factory.lazy_attribute(lambda o: faker.name())

    datatype = factory.lazy_attribute(lambda o: faker.random.choice(bio_tables.models.BCDataType.objects.all()))


class SampleTypeConfigFactory(DjangoModelFactory):
    FILE_TYPE_CHOICES = ['csv', 'xls', 'xlsx']

    class Meta:
        model = settings_models.SampleTypeConfig
        exclude = ('FILE_TYPE_CHOICES',)

    sample_type = factory.SubFactory(GlobalSampleTypeFactory)
    file_type = factory.lazy_attribute(lambda o: faker.random.choice(o.FILE_TYPE_CHOICES))
    skip = factory.lazy_attribute(lambda o: faker.random.randint(0, 20))
    sample_field = factory.lazy_attribute(lambda o: faker.word())
    value_field = factory.lazy_attribute(lambda o: faker.word())


class BcDatabaseConnection(DjangoModelFactory):

    class Meta:
        model = settings_models.BcDatabaseConnection

    host = "localhost"
    name = "TestDB"

    account_name = "test_account"
    uploader = "UploaderT"