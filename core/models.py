import datetime

from pandas import DataFrame

import bio_tables.models
from core.utils import distance

from django.db.models.functions import Lower
from django.utils import timezone

from django.db import models
from django.utils.translation import gettext as _

from bio_tables import models as bio_models

import logging

logger = logging.getLogger('dart')


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

    # this is provided for convince so the user won't have to re-enter the directory repeatedly. It may differ based
    # on being 'At-sea' where data is collected or on land where collected data is loaded to BioChem
    bottle_directory = models.FilePathField(verbose_name=_("BTL Directory"),
                                            help_text=_("Location of the .BTL/.ROS fiels to be loaded."),
                                            null=True, blank=True)

    @property
    def get_biochem_table_name(self):
        if not self.biochem_table:
            self.biochem_table = f'bio_upload_{self.name}'
            self.save()

        return self.biochem_table

    def __str__(self):
        return f'{self.name}'


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

    sample_id = models.IntegerField(verbose_name=_("Start Bottle"), null=True, blank=True)
    end_sample_id = models.IntegerField(verbose_name=_("End Bottle"), null=True, blank=True)

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
        actions = self.actions.all()
        if not actions.exists():
            return ""

        a1 = actions.first()
        a2 = actions.last()

        if a1 == a2:
            return ""

        d = distance([a1.latitude, a1.longitude], [a2.latitude, a2.longitude])

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


# Elog events are typically made up of multiple actions. A CTD is 'deployed', it's noted when it reaches 'bottom'
# and then a final action once it's 'recovered'. The action model allows us to track when and where those actions
# are noted so we can track information about them.
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

    # the data collector would bet he person who fired the event on the ship. For BIO this would be the 'Author' field
    data_collector = models.CharField(verbose_name=_("Data Collector"), max_length=100, blank=True, null=True)
    sounding = models.IntegerField(verbose_name=_("Sounding"), blank=True, null=True)

    comment = models.CharField(verbose_name=_("Comment"), max_length=255, blank=True, null=True)

    @property
    def drift_distance(self):
        previous_action = self.event.actions.filter(date_time__lt=self.date_time).last()

        if not previous_action:
            return ""

        if previous_action == self:
            return ""

        d = distance([previous_action.latitude, previous_action.longitude], [self.latitude, self.longitude])

        return d

    @property
    def drift_time(self):
        previous_action = self.event.actions.filter(date_time__lt=self.date_time).last()
        if not previous_action:
            return 0

        return self.date_time - previous_action.date_time

    def __str__(self):
        return f'{self.pk}: {self.get_type_display()} - {self.date_time}'

    class Meta:
        ordering = ('date_time', )


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


# Variable fields are used to keep elog variables that we don't immediately use so that we can optionally query
# them later. I feel like we should have a flag that can turn the processing of these on and off because
# processing variables for an elog takes about 75% of the time required to process an elog. It would really speed
# up the process to remove them if they aren't needed.
class VariableField(models.Model):
    action = models.ForeignKey(Action, verbose_name=_("Action"), related_name="variables", on_delete=models.CASCADE)
    name = models.ForeignKey(VariableName, verbose_name=_("Field Name"), related_name="variables",
                             on_delete=models.CASCADE)
    value = models.CharField(verbose_name=_("Field Value"), max_length=255)


# Bottles keep track of CTD bottles that sensor and sample data will later be attached to.
class Bottle(models.Model):
    event = models.ForeignKey(Event, verbose_name=_("Event"), related_name="bottles", on_delete=models.CASCADE)
    date_time = models.DateTimeField(verbose_name=_("Fired Date/Time"))

    # the bottle number is its order from 1 to N in a series of bottles as opposed tot he bottle ID which is the
    # label placed on the bottle linking it to all samples that come from that bottle.
    bottle_id = models.IntegerField(verbose_name=_("Bottle ID"))

    # the bottle number will not be present if this is a RingNet event
    bottle_number = models.IntegerField(verbose_name=_("Bottle Number"), blank=True, null=True)

    pressure = models.FloatField(verbose_name=_("Pressure"), default=0.0)

    latitude = models.FloatField(verbose_name=_("Latitude"), blank=True, null=True)
    longitude = models.FloatField(verbose_name=_("Longitude"), blank=True, null=True)

    def __str__(self):
        return f"{self.bottle_id}:{self.bottle_number}:{self.pressure}:[{self.latitude}, {self.longitude}]"

    class Meta:
        unique_together = ['event', 'bottle_number']
        ordering = ['bottle_id']


# Sample types help us track sensors and samples that have been previously loaded for any mission, when we see a
# sensor or sample with the same short name in the future we'll know what biochem data types to use as well as what
# file configurations to use when loading that data.
class SampleType(models.Model):
    short_name = models.CharField(verbose_name=_("Short/Column Name"), max_length=20,
                                  help_text=_("The column name of a sensor or a short name commonly "
                                              "used for the sample"))
    long_name = models.CharField(verbose_name=_("Name"), max_length=126, null=True, blank=True,
                            help_text=_("Short descriptive name for this type of sample/sensor"))
    priority = models.IntegerField(verbose_name=_("Priority"), default=1)

    comments = models.CharField(verbose_name=_("Comments"), max_length=255, null=True, blank=True)

    # Datatype may not be known by the user at the time they need to create this sensor, but it will
    # have to be specified before BioChem tables can be created
    datatype = models.ForeignKey(bio_tables.models.BCDataType, verbose_name=_("BioChem DataType"), null=True,
                                 blank=True, related_name='sample_types', on_delete=models.SET_NULL)

    def __str__(self):
        return self.short_name + (f" - {self.long_name}" if self.long_name else "")


# The SampleFileSettings model allows us to track what a file of a specific type with given headers for a specific
# sample type should look like. Once a csv, with the columns 'Sample' and 'O2_Concentration (m/l)' for the 'Oxy'
# sample type has been loaded, the next time we see that file we'll know what to pull out of it. This could be done
# Once and fixtures created that will be distributed like the bio_table fixtures.
# I was going to use the FileConfiguration model for this purpose, but Sensors and Samples are much more
# complicated and require a more specialized approach.
class SampleFileSettings(models.Model):

    sample_type = models.ForeignKey(SampleType,
                                    verbose_name=_("Sample Type"), on_delete=models.CASCADE,
                                    related_name="sample_file_configs",
                                    help_text=_("The sample type this configuration describes"))

    file_config_name = models.CharField(verbose_name=_("Configuration Name"), max_length=50, null=True, blank=True,
                            help_text=_("Human readable name of this configuration to assist in choosing the "
                                        "configuration. If autogenerated this will be the file type and sample type"
                                        "short name (i.e csv - oxy for oxygen loaded from a csv file"))

    file_type = models.CharField(verbose_name=_("File Type"), max_length=5,
                                 help_text=_("file type extension e.g csv, xls, xlsx, dat"))

    header = models.IntegerField(verbose_name=_("Header Row"), default=0,
                                 help_text=_("The row containing headers is often not the first row of a file. "
                                             "This value indicates what row it is normally located on."))

    sample_field = models.CharField(verbose_name=_("Sample Column"), max_length=50,
                                    help_text=_("Lowercase name of the column that contains the bottle ids"))

    value_field = models.CharField(verbose_name=_("Value Column"), max_length=50,
                                   help_text=_("Lowercase name of the column that contains the value data"))

    tab = models.CharField(verbose_name=_("Tab Name"), max_length=20, blank=True, null=True,
                           help_text=_("the tab name data is located on"))

    flag_field = models.CharField(verbose_name=_("Flag Column"), max_length=50, blank=True, null=True,
                                  help_text=_("Lowercase name of the column that contains flags, if it exists"))

    replicate_field = models.CharField(verbose_name=_("Replicate Column"), max_length=50, blank=True, null=True,
                                       help_text=_("Lowercase name of the column indicating a replicate, if it exists"))

    comment_field = models.CharField(verbose_name=_("Comment Column"), max_length=50, blank=True, null=True,
                                     help_text=_("Lowercase name of the column containing comments, if it exists"))


# BioChemUpload is a table for tracking the last time a sensor or sample was uploaded to biochem. This way we can
# track the data per-mission and let the user know if a sample has been uploaded, was modified and needs
# to be re-uploaded, or hasn't been loaded yet.
class BioChemUpload(models.Model):
    mission = models.ForeignKey(Mission, verbose_name=_("Mission"), on_delete=models.CASCADE, related_name='uploads')
    type = models.ForeignKey(SampleType, verbose_name=_("Type"), on_delete=models.CASCADE, related_name='uploads')

    upload_date = models.DateTimeField(verbose_name=_("Upload Date"), null=True, blank=True,
                                       help_text=_("The last time this sensor/sample was uploaded to biochem"))
    modified_date = models.DateTimeField(verbose_name=_("Upload Date"), null=True, blank=True,
                                         help_text=_("The last time this sensor/sample was modified"))


# The Sample model tracks sample/sensor types that can or have been uploaded for a specific bottle. It can also
# track the file data for the sensor was loaded from
class Sample(models.Model):
    bottle = models.ForeignKey(Bottle, verbose_name=_("Bottle"), on_delete=models.CASCADE, related_name='samples')
    type = models.ForeignKey(SampleType, verbose_name=_("Type"), on_delete=models.CASCADE, related_name='samples')

    file = models.CharField(verbose_name=_("File Name"), max_length=50, null=True, blank=True)

    def __str__(self):
        return f'{self.type}: {self.bottle.bottle_id}'


# Most samples loaded are 'Discrete' chemical or mineral measurements. The DiscreteSampleValue table tracks those
# values, but can also be used to keep track of replicates (when a sample has more than one value), data quality flags
# individual BioChem datatypes (for when the data type is differenet or more descriptive than the sensor/sample
# general datatype), and comments related to the sample.
class DiscreteSampleValue(models.Model):
    sample = models.ForeignKey(Sample, verbose_name=_("Sample"), on_delete=models.CASCADE,
                                  related_name='discrete_value')
    value = models.FloatField(verbose_name=_("Value"))

    replicate = models.IntegerField(verbose_name=_("Replicate #"), default=1,
                                    help_text=_("Replicates occur when there are multiple samples of the same type "
                                                "form the same bottle."))

    flag = models.IntegerField(verbose_name=_("Data Quality Flag"), null=True, blank=True)

    # Individual samples can have different datatype than the general datatype provided by the
    # sample type. If this is blank the sample.type.datatype value should be used for the sample
    sample_datatype = models.ForeignKey(bio_tables.models.BCDataType, verbose_name=_("BioChem DataType"), null=True,
                                        blank=True, on_delete=models.SET_NULL)

    comment = models.TextField(verbose_name=_("Sample Comments"), null=True, blank=True)

    @property
    def datatype(self) -> bio_models.BCDataType:
        return self.sample_datatype if self.sample_datatype else self.sample.type.datatype

    def __str__(self):
        return f'{self.sample}: {self.value}'


# These are some of the common errors that occur when processing data and allow us to sort various errors depending
# on what problems we're using the errors to solve.
class ErrorType(models.IntegerChoices):
    unknown = 0, "Unknown"
    missing_id = 1, "Missing ID"
    missing_value = 2, "Missing Value"
    validation = 3, "Validation Error"


# This is the basis for most errors that we want to report to the user. All errors should have at the very least
# a message and what type of error it is.
class AbstractError(models.Model):
    class Meta:
        abstract = True

    message = models.CharField(max_length=255, verbose_name=_("Message"))
    type = models.IntegerField(verbose_name=_("Error type"), default=0, choices=ErrorType.choices)


# General errors we want to keep track of and notify the user about
class Error(AbstractError):
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='errors', verbose_name=_("Mission"))


# Errors that take place when validating an object. This might be something like a missing attachment, date or sample ID
class ValidationError(AbstractError):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='validation_errors',
                              verbose_name=_("Event"))

    def __str__(self):
        return f"{self.get_type_display()} : {self.message}"


# File errors occur when reading data from a file before an object is created, it's fundmentally something wrong with
# the file itself like when columns or specific tags are missing or if a file is improperly formatted.
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
              ("comment", "Comment"), ("data_collector", "Author"), ("sounding", "Sounding")]

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
