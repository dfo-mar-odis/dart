from enum import Enum

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory
from faker import Faker

import bio_tables.models
from core import models

faker = Faker()


class MissionFactory(DjangoModelFactory):

    class Meta:
        model = models.Mission

    name = factory.lazy_attribute(lambda o: faker.word())


class GeographicRegionFactory(DjangoModelFactory):

    class Meta:
        model = models.GeographicRegion

    name = factory.lazy_attribute(lambda o: faker.name())


class StationFactory(DjangoModelFactory):

    class Meta:
        model = models.Station

    name = factory.lazy_attribute(lambda o: faker.bothify(text='??_##'))


class InstrumentFactory(DjangoModelFactory):
    class Meta:
        model = models.Instrument

    name = factory.lazy_attribute(lambda o: faker.name())
    type = factory.lazy_attribute(lambda o: faker.random.choice(models.InstrumentType.choices)[0])


class CTDInstrumentFactory(InstrumentFactory):
    name = models.InstrumentType.ctd.name
    type = models.InstrumentType.ctd


class EventFactory(DjangoModelFactory):

    class Meta:
        model = models.Event
        abstract = True

    # Instrument, sample_id and end_sample_id should be set by extending classes because they're typically dependent
    # on the type of instrument the event is recording

    event_id = factory.lazy_attribute(lambda o: faker.random_number(digits=3))
    mission = factory.SubFactory(MissionFactory)
    station = factory.SubFactory(StationFactory)
    instrument = factory.SubFactory(InstrumentFactory, name="other", instrument_type=models.InstrumentType.other)


class CTDEventFactory(EventFactory):

    sample_id = factory.lazy_attribute(lambda o: faker.random.randint(0, 1000))
    end_sample_id = factory.lazy_attribute(lambda o: (o.sample_id + faker.random.randint(0, 1000)))
    instrument = factory.SubFactory(CTDInstrumentFactory)


class NetEventFactory(EventFactory):
    sample_id = factory.lazy_attribute(lambda o: faker.random.randint(0, 1000))
    instrument = factory.SubFactory(InstrumentFactory, name="RingNet", type=models.InstrumentType.net)


class ActionFactory(DjangoModelFactory):
    class Meta:
        model = models.Action

    event = factory.SubFactory(CTDEventFactory)
    date_time = factory.lazy_attribute(lambda o: faker.date_time(tzinfo=timezone.get_current_timezone()))
    latitude = factory.lazy_attribute(lambda o: faker.pyfloat())
    longitude = factory.lazy_attribute(lambda o: faker.pyfloat())
    type = factory.lazy_attribute(lambda o: faker.random.choice(models.ActionType.choices)[0])


class AttachmentFactory(DjangoModelFactory):
    class Meta:
        model = models.InstrumentSensor

    event = factory.SubFactory(CTDEventFactory)
    name = factory.lazy_attribute(lambda o: faker.name())


class SampleTypeFactory(DjangoModelFactory):

    class Meta:
        model = models.SampleType

    short_name = factory.lazy_attribute(lambda o: faker.word())
    long_name = factory.lazy_attribute(lambda o: faker.name())

    datatype = factory.lazy_attribute(lambda o: faker.random.choice(bio_tables.models.BCDataType.objects.all()))


class SampleTypeConfigFactory(DjangoModelFactory):
    FILE_TYPE_CHOICES = ['csv', 'xls', 'xlsx']

    class Meta:
        model = models.SampleTypeConfig
        exclude = ('FILE_TYPE_CHOICES',)

    sample_type = factory.SubFactory(SampleTypeFactory)
    file_type = factory.lazy_attribute(lambda o: faker.random.choice(o.FILE_TYPE_CHOICES))
    skip = factory.lazy_attribute(lambda o: faker.random.randint(0, 20))
    sample_field = factory.lazy_attribute(lambda o: faker.word())
    value_field = factory.lazy_attribute(lambda o: faker.word())


class BottleFactory(DjangoModelFactory):
    class Meta:
        model = models.Bottle

    event = factory.SubFactory(CTDEventFactory)
    date_time = factory.lazy_attribute(lambda o: faker.date_time(tzinfo=timezone.get_current_timezone()))
    bottle_id = factory.sequence(lambda n: n)
    pressure = factory.lazy_attribute(lambda o: faker.pyfloat())

    @classmethod
    def _setup_next_sequence(cls):
        return getattr(cls, 'start_bottle_seq', 0)


class SampleFactory(DjangoModelFactory):

    class Meta:
        model = models.Sample

    bottle = factory.SubFactory(BottleFactory)
    type = factory.SubFactory(SampleTypeFactory, **{'file_type': 'csv'})
    file = factory.lazy_attribute(lambda o: faker.word() + ".csv")


class DiscreteValueFactory(DjangoModelFactory):

    class Meta:
        model = models.DiscreteSampleValue

    sample = factory.SubFactory(SampleFactory)
    value = factory.lazy_attribute(lambda o: faker.pyfloat())


class MissionSampleConfig(DjangoModelFactory):

    class Meta:
        model = models.MissionSampleConfig

    mission = factory.SubFactory(MissionFactory)
    config = factory.SubFactory(SampleTypeConfigFactory)