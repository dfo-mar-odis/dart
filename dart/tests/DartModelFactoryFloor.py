import factory
import decimal
import random
import datetime

from factory.django import DjangoModelFactory

from user_settings import models as user_models
from dart import models as dart_models

class GlobalGeographicRegionFactory(DjangoModelFactory):
    class Meta:
        model = user_models.GlobalGeographicRegion

    name = factory.Faker("city")


class GlobalStationFactory(DjangoModelFactory):
    class Meta:
        model = user_models.GlobalStation

    name = factory.Faker("city")


class StationFactory(DjangoModelFactory):
    class Meta:
        model = dart_models.Station

    name = factory.Faker("word")


class OtherInstrumentFactory(DjangoModelFactory):
    class Meta:
        model = dart_models.Instrument

    name = factory.Faker("word")
    type = dart_models.InstrumentType.other


class NetInstrumentFactory(OtherInstrumentFactory):
    type = dart_models.InstrumentType.net


class CTDInstrumentFactory(OtherInstrumentFactory):
    type = dart_models.InstrumentType.ctd


class MissionFactory(DjangoModelFactory):
    class Meta:
        model = dart_models.Mission

    name = factory.Faker("word")
    mission_descriptor = factory.Faker("word")
    start_date = factory.Faker("date_this_decade")
    end_date = factory.Faker("date_this_decade")
    geographic_region = factory.SubFactory('dart.tests.DartModelFactoryFloor.GlobalGeographicRegionFactory')
    lead_scientist = factory.Faker("name")
    platform = factory.Faker("word")
    protocol = factory.Faker("word")
    collector_comments = factory.Faker("text")
    data_manager_comments = factory.Faker("text")
    data_center = 20  # or use a valid choice


class EventFactory(DjangoModelFactory):
    class Meta:
        model = dart_models.Event

    mission = factory.SubFactory(MissionFactory)
    event_id = factory.Sequence(lambda n: n + 1)
    station = factory.SubFactory(StationFactory)
    instrument = factory.SubFactory(OtherInstrumentFactory)


class NetEventFactory(EventFactory):
    instrument = factory.SubFactory(NetInstrumentFactory)


class CTDEventFactory(EventFactory):
    instrument = factory.SubFactory(CTDInstrumentFactory)


class ActionFactory(DjangoModelFactory):
    class Meta:
        model = dart_models.Action

    event = factory.SubFactory(EventFactory)
    type = factory.Iterator([choice[0] for choice in dart_models.ActionType.choices])
    date_time = factory.Faker("date_time_this_decade", tzinfo=datetime.timezone.utc)
    latitude = factory.lazy_attribute(lambda o: decimal.Decimal(random.randint(-89, 89)))
    longitude = factory.lazy_attribute(lambda o: decimal.Decimal(random.randint(-179, 179)))
    sounding = factory.Faker("pyfloat", left_digits=3, right_digits=2, positive=True)