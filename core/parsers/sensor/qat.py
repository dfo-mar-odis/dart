import pandas as pd
import logging

from io import StringIO
from dateutil.parser import parse
from pytz import UTC

from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext as _

from core.models import Mission, InstrumentType, FileError, ErrorType, Bottle

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.qat')

class QATParser:

    # Expected columns required to create a bottle object
    column_event = 'event'
    column_sample_id = 'sample_id'
    column_date = 'date'
    column_time = 'time'
    column_latitude = 'bottleLatitude'
    column_longitude = 'bottleLongitude'
    column_pressure = 'PrDM'

    # Optional columns
    column_rosette_position = 'rosette'

    def _create_bottles(self):

        create_bottles = []
        update_bottles = []

        for idx, data in self.data_frame.iterrows():
            event_id = data[self.column_event]

            try:
                event = self.mission.events.get(event_id=event_id, instrument__type=InstrumentType.ctd)
            except ObjectDoesNotExist as ex:
                message = _("Could not find matching CTD event for event number") + f" : {event_id}"
                err = FileError(mission=self.mission, message=message, line=0, type=ErrorType.bottle, file_name=self.file_name)
                err.save()
                raise ex


            date = data[self.column_date].replace("\"", "")
            time = data[self.column_time].replace("\"", "")

            if not (latitude := data[self.column_latitude]):
                latitude = None
                # raise ValueError(f"Missing Latitude expected in field \"{self.column_latitude}\"")

            if not (longitude := data[self.column_longitude]):
                longitude = None
                # raise ValueError(f"Missing Latitude expected in field \"{self.column_longitude}\"")

            if not (bottle_id := data[self.column_sample_id]):
                raise ValueError(f"Missing Sample ID expected in field \"{self.column_sample_id}\"")

            if not (pressure := data[self.column_pressure]):
                raise ValueError(f"Missing Pressure expected in field \"{self.column_pressure}\"")

            # Combine date and time into a datetime object
            try:
                closed = parse(f"{date} {time}").astimezone(UTC)
            except ValueError as e:
                message = _("Invalid date or time format for event number") + f" : {event_id}"
                err = FileError(mission=self.mission, message=message, line=0, type=ErrorType.bottle,
                                file_name=self.file_name)
                err.save()
                raise e

            bottle = event.bottles.filter(event=event, bottle_id=bottle_id)
            if bottle.exists():
                bottle = bottle.first()
                update_bottles.append(bottle)
            else:
                bottle = Bottle(event=event, bottle_id=bottle_id)
                create_bottles.append(bottle)

            bottle.closed = closed
            bottle.pressure = pressure
            bottle.latitude = latitude
            bottle.longitude = longitude

            if self.column_rosette_position in data:
                bottle.bottle_number = data[self.column_rosette_position]

        if len(create_bottles) > 0:
            Bottle.objects.bulk_create(create_bottles)

        if len(update_bottles) > 0:
            Bottle.objects.bulk_update(update_bottles, ['closed', 'pressure', 'latitude', 'longitude', 'bottle_number'])

    def parse(self):
        self.data_frame = pd.read_csv(self.file, na_filter=False)

        self._create_bottles()

    def __init__(self, mission: Mission, file_name: str, file: StringIO):
        self.file_name = file_name
        self.file = file
        self.mission = mission