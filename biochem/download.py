from datetime import timezone, timedelta

from django.db.models import QuerySet
from django.utils.translation import gettext as _

from bio_tables import sync_tables
from core.models import ActionType

from . import models as biochem_models
from bio_tables import models as biotable_model
from core import models as core_models
from settingsdb import utils

import logging

user_logger = logging.getLogger('dart.user')
logger = logging.getLogger('dart')


class DatabaseDownloader:
    def __init__(self, mission_seq):
        self.bio_mission = biochem_models.Bcmissions.objects.using('biochem').get(mission_seq=mission_seq)

        bio_mission_name = self.bio_mission.name
        self.db_name = "DART_" + bio_mission_name.upper()

        user_logger.info("Creating Local Mission DB for " + bio_mission_name)

    def _parse_date_time(self, start_date, start_time, utc_offset=0):
        from datetime import datetime

        # Assuming bio_event.start_date is a DateField and bio_event.start_time is an integer
        start_date = start_date

        # Convert start_time (HHMM) into hours and minutes
        hours = start_time // 100
        minutes = start_time % 100

        # Combine start_date with hours and minutes to create a datetime object
        start_datetime = datetime.combine(start_date, datetime.min.time()).replace(hour=hours, minute=minutes)

        # Set the UTC offset as the timezone without adjusting the time
        utc_offset_timedelta = timedelta(hours=int(utc_offset))
        start_datetime = start_datetime.astimezone(timezone(utc_offset_timedelta))
        return start_datetime

    def copy_mission(self):
        bio_mission = self.bio_mission
        mission_attrs = {
            "name": bio_mission.name,
            "dart_version": utils.get_dart_git_version(),
            "mission_descriptor": bio_mission.descriptor,
            "geographic_region": bio_mission.geographic_region,
            "lead_scientist": bio_mission.leader,
            "start_date": bio_mission.start_date,
            "end_date": bio_mission.end_date,
            "platform": bio_mission.platform,
            "protocol": bio_mission.protocol,
            "data_center": biotable_model.BCDataCenter(pk=bio_mission.data_center.pk),
            "collector_comments": bio_mission.collector_comment,
            "data_manager_comments": bio_mission.data_manager_comment,
        }
        mission = core_models.Mission.objects.create(**mission_attrs)
        return mission

    def copy_stations(self):
        user_logger.info("Copying station data")

        events = self.bio_mission.events.all()
        stations = {
            station.name: station for station in core_models.Station.objects.all()
        }

        station_list = events.values_list('collector_station_name', flat=True).distinct()
        create_stations = [core_models.Station(name=station) for station in station_list if station not in stations]
        if create_stations:
            core_models.Station.objects.bulk_create(create_stations)

        user_logger.info(f"Created {len(create_stations)} stations")

    def copy_discrete_actions(self, headers, core_event: core_models.Event):

        # if this is a discrete mission we can use the BCEvents start_date, start_time, for the deploy action
        # and the end_date, end_time for the recovered action, but the event min/max lat/lon doesn't tell us
        # Where the events started or ended. Presumably though, the deployed start_location will be the furtherest
        # from the recovery location.
        #
        # BCDiscreteHedrs start_date, start_time, start_lat, start_lon are the times and locations of where
        # bottles were closed and can give us specifics on bottom and recovery actions.
        #
        # If the earliest bottle closed is the deepest the bottles are on a CTD rosette, if the earliest
        # bottle closed is a shallow bottle, this is bottles on a wire.
        #
        # Presumably wherever the latest bottle was closed will be nearest to the recovery action.

        collector = headers.order_by('collector').distinct().values_list('collector', flat=True).first()
        comment = headers.order_by('collector_comment').distinct().values_list('collector_comment', flat=True).first()

        first_bottle = headers.first()
        last_bottle = headers.last()
        deployed = core_models.Action(event=core_event, type=ActionType.deployed)
        deployed.date_time = self._parse_date_time(first_bottle.event.start_date, first_bottle.event.start_time, first_bottle.event.utc_offset)
        deployed.data_collector = collector
        deployed.comment = comment

        # I can't think of a way we could get the deployment sounding
        deployed.sounding = first_bottle.sounding

        # Presumably, the event has a min/max lat/lon making it a square. If we assumed a ship drifts in a strength
        # line, then the recovery point will be one corner of this square and the deployment would be the opposite
        # corner. For now I'll just assume the bottom and deployed have the same coordinates
        deployed.latitude = first_bottle.start_lat
        deployed.longitude = first_bottle.start_lon

        bottom = core_models.Action(event=core_event, type=ActionType.bottom)
        bottom.date_time = self._parse_date_time(first_bottle.start_date, first_bottle.start_time, first_bottle.event.utc_offset)
        bottom.data_collector = collector
        bottom.sounding = first_bottle.sounding
        bottom.latitude = first_bottle.start_lat
        bottom.longitude = first_bottle.start_lon

        recovered = core_models.Action(event=core_event, type=ActionType.recovered)
        recovered.date_time = self._parse_date_time(last_bottle.start_date, last_bottle.start_time, last_bottle.event.utc_offset)
        recovered.data_collector = collector
        recovered.sounding = last_bottle.sounding
        recovered.latitude = last_bottle.start_lat
        recovered.longitude = last_bottle.start_lon

        return [deployed, bottom, recovered]

    def copy_bottles(self, headers: QuerySet[biochem_models.Bcdiscretehedrs], core_event: core_models.Event):
        create_bottles = []
        total_rows = len(headers)
        for row, header in enumerate(headers):
            if (row % 10) == 0:
                user_logger.info(_("Creating Bottles") + ": %d/%d", (row+1), total_rows)

            bottle_id = header.collector_sample_id
            bottle = core_models.Bottle(event=core_event, bottle_id=bottle_id, bottle_number=(row+1))
            bottle.closed = self._parse_date_time(header.start_date, header.start_time, int(header.event.utc_offset))
            bottle.pressure = header.start_depth
            bottle.end_pressure = header.end_depth
            bottle.latitude = header.start_lat
            bottle.longitude = header.start_lon
            bottle.gear_type = biotable_model.BCGear(gear_seq=header.gear_seq)
            create_bottles.append(bottle)

        return create_bottles

    def copy_mission_data_types(self, data_types):
        create_data_types = []

        total_rows = len(data_types)
        for row, data_type_seq in enumerate(data_types):
            if (row % 10) == 0:
                user_logger.info(_("Loading Data Types") + ": %d/%d", (row+1), total_rows)

            datatype = biotable_model.BCDataType.objects.get(data_type_seq=data_type_seq)
            is_sensor = "CTD" in datatype.method.upper()
            mission_sample_type = core_models.MissionSampleType(
                mission=self.core_mission,
                is_sensor=is_sensor,
                name=datatype.method,
                long_name=datatype.description,
                datatype=datatype,
            )
            create_data_types.append(mission_sample_type)

        core_models.MissionSampleType.objects.bulk_create(create_data_types)

    def copy_discrete_sample_values(self, values: QuerySet[biochem_models.Bcdiscretedtails]):
        bottles = {b.bottle_id: b for b in core_models.Bottle.objects.all()}

        data_types = {m.datatype.data_type_seq: m for m in core_models.MissionSampleType.objects.all()}

        create_samples = []
        create_discrete_values = []
        total_rows = len(values)
        values_list = list(values)
        for row, value in enumerate(values_list):
            if (row % 10) == 0:
                user_logger.info(_("Loading Discrete Values") + ": %d/%d", (row+1), total_rows)

            try:
                bottle_id = int(value.discrete.collector_sample_id)
            except ValueError as ex:
                raise ValueError(f"Cannot convert bottle id {value.discrete.collector_sample_id} to int")

            if bottle_id not in bottles:
                raise ValueError(f"Bottle hasn't been created for {bottle_id}")

            bottle = bottles[bottle_id]
            data_type = data_types[value.data_type.data_type_seq]

            sample = core_models.Sample(bottle=bottle, type=data_type)
            create_samples.append(sample)

            if value.averaged_data.upper() == 'N':
                discrete_value = core_models.DiscreteSampleValue()
                discrete_value.sample = sample
                discrete_value.value = value.data_value
                discrete_value.flag = value.data_qc_code if value.data_qc_code != '' else None
                discrete_value.limit = value.detection_limit if value.detection_limit else None

                create_discrete_values.append(discrete_value)
            elif (replicates:=value.discrete_replicates.all()).exists():
                for replicate_number, replicate in enumerate(replicates):
                    discrete_value = core_models.DiscreteSampleValue()
                    discrete_value.sample = sample
                    discrete_value.replicate = (replicate_number + 1)
                    discrete_value.value = value.data_value
                    discrete_value.flag = value.data_qc_code if value.data_qc_code != '' else None
                    discrete_value.limit = value.detection_limit if value.detection_limit else None

                    create_discrete_values.append(discrete_value)

            if len(create_discrete_values) > 500:
                core_models.Sample.objects.bulk_create(create_samples)
                core_models.DiscreteSampleValue.objects.bulk_create(create_discrete_values)
                create_samples = []
                create_discrete_values = []

        core_models.Sample.objects.bulk_create(create_samples)
        core_models.DiscreteSampleValue.objects.bulk_create(create_discrete_values)

    def copy_events(self):
        has_discrete = len(self.bio_mission.events.filter(discrete_headers__isnull=False).distinct()) > 1
        has_plankton = len(self.bio_mission.events.filter(planktonheaders__isnull=False).distinct()) > 1

        events = list(self.bio_mission.events.all())
        stations = {
            station.name: station for station in core_models.Station.objects.all()
        }

        create_events = []
        create_actions = []
        create_bottles = []
        total_rows = len(events)
        for row, event in enumerate(events):
            if (row % 10) == 0:
                user_logger.info(_("Loading Events") + ": %d/%d", (row+1), total_rows)

            station = None
            instrument = None
            start_sample = None
            end_sample = None
            if event.collector_station_name in stations:
                station = stations[event.collector_station_name]
            else:
                raise ValueError(f"Missing station: {event.collector_station_name}")

            if has_discrete:
                instrument = core_models.Instrument.objects.get_or_create(name="CTD", type=core_models.InstrumentType.ctd)[0]
                samples = event.discrete_headers.order_by('collector_sample_id')
                start_sample = samples.first().collector_sample_id
                end_sample = samples.last().collector_sample_id
            elif has_plankton:
                # we'll get more complex here later. We should be able to get the netdata from the plankton headers
                raise NotImplementedError("Need to create plankton net")
            else:
                raise ValueError("Unknown Instrument that is not a CTD or a Ring Net")

            core_event = core_models.Event()
            core_event.mission = self.core_mission
            core_event.station = station
            core_event.instrument = instrument
            core_event.event_id = event.collector_event_id
            core_event.sample_id = start_sample
            core_event.end_sample_id = end_sample

            # we will likely have to take some guesses at the optional net attributes, if this is a plankton event.
            # This data doesn't get captured in Discrete or Plankton Headers. Someone thought it'd be a great idea
            # to compute this data into a volume, store the computed value in biochem and discard the rest so the
            # data is now lost forever.
            core_event.surface_area = None
            core_event.wire_angle = None
            core_event.wire_out = None
            core_event.flow_start = None
            core_event.flow_end = None

            create_events.append(core_event)
            if has_discrete:
                headers = event.discrete_headers.all().order_by("start_date", "start_time")
                create_actions.extend(self.copy_discrete_actions(headers, core_event))
                create_bottles.extend(self.copy_bottles(headers, core_event))

        core_models.Event.objects.bulk_create(create_events)
        core_models.Action.objects.bulk_create(create_actions)
        core_models.Bottle.objects.bulk_create(create_bottles)

    def download(self):
        utils.add_database(self.db_name)
        self.core_mission = self.copy_mission()
        self.copy_stations()
        self.copy_events()

        values = biochem_models.Bcdiscretedtails.objects.using("biochem").filter(discrete__event__mission=self.bio_mission)
        data_types = values.values_list('data_type', flat=True).distinct()

        self.copy_mission_data_types(data_types)
        self.copy_discrete_sample_values(values)

        user_logger.info(_("Complete"))

def test():

    import environ
    import os
    logger.level = logging.DEBUG

    env = environ.Env()
    user = env('BIOCHEM_DB_USER')
    password = env('BIOCHEM_DB_PASS')
    tns = env('BIOCHEM_DB_NAME')
    sync_tables.connect_tns(user, password, tns)

    # BiochemT test
    # downloader = DatabaseDownloader(20000000010872)

    # BiochemP test
    downloader = DatabaseDownloader(20000000012946)
    location = utils.get_db_location(downloader.db_name)
    if os.path.exists(location):
        os.remove(location)

    downloader.download()

    utils.close_connections()
