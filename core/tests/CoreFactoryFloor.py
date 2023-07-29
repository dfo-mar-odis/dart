import factory
from factory.django import DjangoModelFactory
from faker import Faker

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
