import datetime
import math

from django.db.models.functions import Lower
from django.utils import timezone

from django.db import models
from django.utils.translation import gettext as _

from bio_tables import models as bio_models


# Used to track a list of reusable names, should be extended to create separated tables
class SimpleLookupName(models.Model):
    name = models.CharField(verbose_name=_("Field Name"), max_length=50, unique=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class GeographicRegion(SimpleLookupName):
    pass


class Mission(models.Model):
    name = models.CharField(verbose_name=_("Mission Name"), max_length=50,
                            help_text=_("Originator’s mission number and/or common name(s) for the mission"))
    mission_descriptor = models.CharField(verbose_name=_("Mission Descriptor"), max_length=50, blank=True, null=True,
                                          help_text=_("Code assigned by OSD, ensures national coordination"))
    start_date = models.DateField(verbose_name=_("Cruise Start Date"),
                                  default=timezone.now)
    end_date = models.DateField(verbose_name=_("Cruise End Date"),
                                default=timezone.now)

    lead_scientist = models.CharField(verbose_name=_("Lead Scientist"), max_length=50, default="N/A",
                                      help_text=_("Chief scientist / principal investigator; LASTNAME,FIRSTNAME"))
    platform = models.CharField(verbose_name=_("Platform"), max_length=50, default="N/A",
                                help_text=_("May be vessel name, fishing boat, wharf, various small vessels, multiple "
                                            "ships. Check that name is spelled correctly. “Unknown” is acceptable for "
                                            "historical data"))
    protocol = models.CharField(verbose_name=_("Protocol"), max_length=50, default="N/A",
                                help_text=_("A citation should be given if standard protocols were used during the "
                                            "mission. The use of non-standard protocols should be noted and further "
                                            "details provided in the collector comments field"))

    geographic_region = models.ForeignKey(GeographicRegion, verbose_name=_("Geographic Region"),
                                          max_length=100, blank=True, null=True, on_delete=models.DO_NOTHING,
                                          help_text=_("Examples: Scotian Shelf, lower St. Lawrence Estuary"))

    collector_comments = models.CharField(verbose_name=_("Collector Comments"), max_length=200, blank=True, null=True,
                                          help_text=_("Comments from the collector that are pertinent to the entire "
                                                      "mission. Generally referring to data collection, analysis, "
                                                      "publications, joint missions (more than one institute involved)"))
    more_comments = models.CharField(verbose_name=_("More Comments"), max_length=200, blank=True, null=True)
    data_manager_comments = models.CharField(verbose_name=_("Data Manager Comments"), max_length=200,
                                             help_text=_("Comments from the data manager that are pertinent to the "
                                                         "entire mission. Generally referring to data management "
                                                         "history (processing steps, edits, special warnings)"),
                                             blank=True, null=True)

    # default=20 is BIO
    data_center = models.ForeignKey(bio_models.BCDataCenter, verbose_name=_("Data Center"), default=20,
                                    on_delete=models.DO_NOTHING)

    biochem_table = models.CharField(verbose_name=_("Root BioChem Table Name"), max_length=100, null=True, blank=True,
                                     help_text=_("How BioChem staging tables will be named without pre or post fixes. "
                                                 "If blank, mission descriptor will be used."))

    @property
    def get_biochem_table_name(self):
        if not self.biochem_table:
            self.biochem_table = f'bio_upload_{self.name}'
            self.save()

        return self.biochem_table

    def __str__(self):
        return f'{self.name}'


class FileType(models.IntegerChoices):
    log = 1, ".LOG"
    btl = 2, ".BTL"
    ros = 3, ".ROS"


class DataFileDirectory(models.Model):
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='files', verbose_name=_("Mission"))
    directory = models.FileField(verbose_name=_("Directory"), help_text=_("Absolute Path to Directory"))
    file_type = models.IntegerField(verbose_name=_("File Types"), choices=FileType.choices)


class InstrumentType(models.IntegerChoices):
    ctd = 1, "CTD"
    net = 2, "Net"
    mooring = 3, "Mooring"
    buoy = 4, "Buoy"
    vpr = 5, "VPR"

    other = 999, "Other"

    @classmethod
    def get(cls, value: str):
        if cls.has_value(value):
            return cls.__getitem__(value.lower())

        return cls.__getitem__('other')

    @classmethod
    def has_value(cls, value: str):
        return cls.__members__.__contains__(value.lower())


class ActionType(models.IntegerChoices):
    # make sure new option names are in lowercase with underscores instead of spaces
    # Labels, in quotations marks, can be uppercase with spaces
    deployed = 1, "Deployed"
    bottom = 2, "Bottom"
    recovered = 3, "Recovered"
    aborted = 4, "Aborted"
    attempt_comms = 5, "Attempted Comms"
    release = 6, "Release"
    on_deck = 7, "On Deck"
    in_water = 8, "In Water"
    start_deployment = 9, "Start Deployment"
    on_bottom = 10, "On Bottom"
    started = 11, "Started"

    other = 999, "Other"

    @classmethod
    def get(cls, value: str):
        if cls.has_value(value):
            return cls.__getitem__(value.lower().replace(' ', '_'))

        return cls.__getitem__('other')

    @classmethod
    def has_value(cls, value: str):
        return cls.__members__.__contains__(value.lower().replace(' ', '_'))


class Instrument(models.Model):
    name = models.CharField(max_length=50, verbose_name=_("Instrument"))
    type = models.IntegerField(verbose_name=_("Instrument Type"), default=999, choices=InstrumentType.choices)

    def __str__(self):
        return f"{self.get_type_display()} - {self.name}"

    class Meta:
        ordering = ('type', 'name',)


class Station(models.Model):
    name = models.CharField(max_length=20, verbose_name=_("Station"))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)


class Event(models.Model):
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='events', verbose_name=_("Mission"))

    event_id = models.IntegerField(verbose_name=_("Event ID"))
    station = models.ForeignKey(Station, on_delete=models.DO_NOTHING, verbose_name=_("Station"), related_name="events")
    instrument = models.ForeignKey(Instrument, on_delete=models.DO_NOTHING, verbose_name=_("Instrument"),
                                   related_name="events")

    sample_id = models.IntegerField(verbose_name=_("Sample ID"), null=True, blank=True)
    end_sample_id = models.IntegerField(verbose_name=_("End Sample ID"), null=True, blank=True)

    @property
    def files(self):
        files = set()
        for action in self.actions.all():
            if action.file:
                files.add(action.file)

        if len(files) > 0:
            return ",".join(files)

        return ''

    @property
    def total_samples(self):
        if self.sample_id is None:
            return 0

        if self.end_sample_id is None:
            return 1

        return self.end_sample_id - self.sample_id

    @property
    def start_location(self):
        action = self.actions.all().order_by("date_time")[0]
        return [action.latitude, action.longitude]

    @property
    def end_location(self):
        action = self.actions.all().order_by("-date_time")[0]
        return [action.latitude, action.longitude]

    @property
    def start_date(self) -> datetime.datetime:
        action = self.actions.all().order_by("date_time")[0]
        return action.date_time

    @property
    def end_date(self) -> datetime.datetime:
        action = self.actions.all().order_by("-date_time")[0]
        return action.date_time

    @property
    def drift_distance(self):
        actions = self.actions.order_by("date_time")
        if not actions.exists():
            return ""

        a1 = actions.first()
        a2 = actions.last()

        if a1 == a2:
            return ""

        lat1 = a1.latitude * math.pi / 180
        lat2 = a2.latitude * math.pi / 180
        lon = (a2.longitude - a1.longitude) * math.pi / 180
        R = 6371e3
        d = math.acos(math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon)) * R
        return round(d, 4)

    @property
    def drift_time(self):
        actions = self.actions.order_by("date_time")
        if not actions.exists():
            return ""

        a1 = actions.first()
        a2 = actions.last()

        return a2.date_time - a1.date_time

    class Meta:
        unique_together = ("event_id", "mission")
        ordering = ("event_id",)

    def __str__(self):
        return f"{self.event_id} - {self.station.name}"


class Action(models.Model):
    event = models.ForeignKey(Event, verbose_name=_("Event"), related_name="actions", on_delete=models.CASCADE)

    date_time = models.DateTimeField(verbose_name=_("Date/Time"))
    latitude = models.FloatField(verbose_name=_("Latitude"))
    longitude = models.FloatField(verbose_name=_("Longitude"))

    # The file this action was loaded from. Events can span different files, but they can also be entered
    # manually (comming soon) so this allows us to track an action back to the file it comes from, if it comes
    # from a file.
    file = models.CharField(verbose_name=_("File Name"), max_length=100, null=True, blank=True)

    # mid helps us track issues, but in the event that this was a manually entered action this will be null
    mid = models.IntegerField(verbose_name="$@MID@$", null=True, blank=True)

    type = models.IntegerField(verbose_name=_("Action Type"), choices=ActionType.choices)
    # if the action is an unknown type then leave a comment here identifying what the 'other' type is
    action_type_other = models.CharField(verbose_name=_("Action Other"), max_length=50, blank=True, null=True,
                                         help_text=_("if the action is an unknown type then leave a comment here "
                                                     "identifying what the 'other' type is"))

    data_collector = models.CharField(verbose_name=_("Data Collector"), max_length=100, blank=True, null=True)
    comment = models.CharField(verbose_name=_("Comment"), max_length=255, blank=True, null=True)

    @property
    def drift_distance(self):
        previous_action = self.event.actions.filter(pk__lt=self.pk).last()
        if not previous_action:
            return 0

        lat1 = previous_action.latitude * math.pi / 180
        lat2 = self.latitude * math.pi / 180
        lon = (self.longitude - previous_action.longitude) * math.pi / 180
        R = 6371e3
        d = math.acos(math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon)) * R
        return d

    @property
    def drift_time(self):
        previous_action = self.event.actions.filter(pk__lt=self.pk).last()
        if not previous_action:
            return 0

        return self.date_time - previous_action.date_time


# In reality a sensor is physically attached to an instrument, but depending on a station's depth a sensor might be
# removed. The Ph sensor for example is only rated to 1,200m, if a station is deeper than that the Ph sensor has to be
# removed. In which case it makes more 'database' sense to attached the sensor to an event.
class InstrumentSensor(models.Model):
    event = models.ForeignKey(Event, verbose_name=_("Event"), related_name="attachments", on_delete=models.CASCADE)
    name = models.CharField(verbose_name=_("Attachment Name"), max_length=50)

    def __str__(self):
        return f"{self.name}"


# A variable field has a variable name because variable names can be reused. Instead of having 50 variable fields
# with the name 'Flowmeter Start' taking up DB space we have one Variable Name 'Flowmeter Start' referenced
# 50 times in the VariableField. Integers take up less space than strings. SimpleLookupName can also be used
# later on to add bilingual support
class VariableName(SimpleLookupName):

    class Meta:
        ordering = (Lower('name'),)


class VariableField(models.Model):
    action = models.ForeignKey(Action, verbose_name=_("Action"), related_name="variables", on_delete=models.CASCADE)
    name = models.ForeignKey(VariableName, verbose_name=_("Field Name"), related_name="variables",
                             on_delete=models.CASCADE)
    value = models.CharField(verbose_name=_("Field Value"), max_length=255)


class ErrorType(models.IntegerChoices):
    unknown = 0, "Unknown"
    missing_id = 1, "Missing ID"
    missing_value = 2, "Missing Value"
    validation = 3, "Validation Error"


class AbstractError(models.Model):
    class Meta:
        abstract = True

    message = models.CharField(max_length=255, verbose_name=_("Message"))
    type = models.IntegerField(verbose_name=_("Error type"), default=0, choices=ErrorType.choices)


class Error(AbstractError):
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='errors', verbose_name=_("Mission"))


class ValidationError(AbstractError):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='validation_errors',
                              verbose_name=_("Event"))

    def __str__(self):
        return f"{self.get_type_display()} : {self.message}"


class FileError(AbstractError):
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='file_errors',
                                verbose_name=_("Mission"))

    # The file this error is associated with if the error is from a file
    file_name = models.CharField(max_length=50, verbose_name=_("File Name"))

    # the line or object to help locate an error within a file
    line = models.IntegerField(verbose_name=_("Line/Object"), blank=True, null=True)

    def __str__(self):
        return f"{self.file_name}: {self.mission} - {self.get_type_display()} : {self.message}"


# File configuration is a method to map fields/columns in a file being parsed to a specific name
# for example, When reading an Elog file the field 'lead_scientist' is required. In a Maritimes' specific elog file
# the field 'PI' represents the lead scientist so the application should be configured that when reading Maritime
# Elog files 'lead_scientist' = 'PI'
class FileConfiguration(models.Model):
    file_type = models.CharField(max_length=18, verbose_name=_("File Type"))

    def __str__(self):
        return f'{self.file_type}'

    def get_mapping(self, field_name):
        return self.mappings.get(field=field_name).mapped_to


class FileConfigurationMapping(models.Model):
    config = models.ForeignKey(FileConfiguration, related_name="mappings", verbose_name=_("Configuration File"),
                               on_delete=models.CASCADE)
    field = models.CharField(max_length=100, verbose_name=_("Dart Field"), help_text=_("The field DART is expecting"))
    mapped_to = models.CharField(max_length=100, verbose_name=_("Elog Field"), help_text=_("The field Elog has"))
    required = models.BooleanField(verbose_name=_("Is Required"), default=False,
                                   help_text=_("Indicate if this is a required field for validation"))

    def __str__(self):
        return f'{self.config.file_type}: [{self.field}: {self.mapped_to}]'


class ElogConfig(FileConfiguration):
    mission = models.OneToOneField(Mission, on_delete=models.CASCADE, related_name='elogconfig',
                                   verbose_name=_('Mission'))

    # required fields that we cannot continue without
    required_fields = [("event", "Event"), ("time_position", "Time|Position"), ("station", "Station"),
                       ("action", "Action"), ("instrument", "Instrument")]

    # optional fields used at various points, but may be event specific. A buoy has no sample ID,
    # or a net will have a sample id, but no end sample id for example
    fields = [('lead_scientist', 'PI'), ('protocol', "Protocol"), ('cruise', "Cruise"), ("platform", "Platform"),
              ("attached", "Attached"), ("start_sample_id", "Sample ID"), ("end_sample_id", "End_Sample_ID"),
              ("comment", "Comment"), ("data_collector", "Author")]

    @staticmethod
    def get_default_config(mission):
        mission_id = mission
        if type(mission) is Mission:
            mission_id = mission.pk

        required_fields = ElogConfig.required_fields
        optional_fields = ElogConfig.fields

        # If a default configuration has been loaded from a fixture file use its mappings.
        default_config = FileConfiguration.objects.filter(file_type='default_elog')
        if default_config.exists():
            required_fields = [(f.field, f.mapped_to) for f in default_config[0].mappings.filter(required=True)]
            optional_fields = [(f.field, f.mapped_to) for f in default_config[0].mappings.filter(required=False)]

        elog_config = ElogConfig.objects.get_or_create(mission_id=mission_id, file_type="elog")[0]

        for field in required_fields:
            if not elog_config.mappings.filter(field=field[0]).exists():
                mapping = FileConfigurationMapping(config=elog_config, field=field[0], mapped_to=field[1],
                                                   required=True)
                mapping.save()

        for field in optional_fields:
            if not elog_config.mappings.filter(field=field[0]).exists():
                mapping = FileConfigurationMapping(config=elog_config, field=field[0], mapped_to=field[1],
                                                   required=False)
                mapping.save()

        return elog_config