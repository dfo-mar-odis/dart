import datetime

from pandas import DataFrame

import bio_tables.models
import settingsdb.utils
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


class Mission(models.Model):
    name = models.CharField(verbose_name=_("Mission Name"), max_length=50,
                            help_text=_("Originator’s mission number and/or common name(s) for the mission"))

    # default to version 3.2.7
    dart_version = models.CharField(verbose_name=_("Dart Version"), max_length=50,
                                    default="b7f674184f401a6a0192ba5e91462fcd3d97ee04")

    mission_descriptor = models.CharField(verbose_name=_("Mission Descriptor"), max_length=50, blank=True, null=True,
                                          help_text=_("Code assigned by OSD, ensures national coordination"))

    geographic_region = models.CharField(verbose_name=_("Geographic Region"), max_length=100,
                                         help_text=_("Terms describing the geographic region where "
                                                     "the mission took place"))

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

    lead_scientist = models.CharField(verbose_name=_("Lead Scientist"), max_length=50, default="N/A",
                                      help_text=_("Chief scientist / principal investigator; LASTNAME,FIRSTNAME"))

    start_date = models.DateField(verbose_name=_("Cruise Start Date"), default=timezone.now)
    end_date = models.DateField(verbose_name=_("Cruise End Date"), default=timezone.now)

    platform = models.CharField(verbose_name=_("Platform"), max_length=50, default="N/A",
                                help_text=_("May be vessel name, fishing boat, wharf, various small vessels, multiple "
                                            "ships. Check that name is spelled correctly. “Unknown” is acceptable for "
                                            "historical data"))
    protocol = models.CharField(verbose_name=_("Protocol"), max_length=50, default="N/A",
                                help_text=_("A citation should be given if standard protocols were used during the "
                                            "mission. The use of non-standard protocols should be noted and further "
                                            "details provided in the collector comments field"))

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

    @property
    def get_batch_name(self):
        return f'{self.start_date.strftime("%Y%m")}{self.end_date.strftime("%m")}'

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

    # net specific attributes
    wire_out = models.FloatField(verbose_name=_("Wire Out"), null=True, blank=True)
    wire_angle = models.FloatField(verbose_name=_("Wire Angle"), null=True, blank=True)
    flow_start = models.IntegerField(verbose_name=_("Flow Meter Start"), null=True, blank=True)
    flow_end = models.IntegerField(verbose_name=_("Flow Meter End"), null=True, blank=True)

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

        return (self.end_sample_id - self.sample_id) + 1

    @property
    def start_location(self):
        action = self.actions.order_by("date_time").first()
        if action:
            return [action.latitude, action.longitude]

    @property
    def end_location(self):
        action = self.actions.order_by("date_time").last()
        if action:
            return [action.latitude, action.longitude]

    @property
    def start_date(self) -> datetime.datetime:
        action = self.actions.order_by("date_time").first()
        if action:
            return action.date_time

    @property
    def end_date(self) -> datetime.datetime:
        action = self.actions.order_by("date_time").last()
        if action:
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

    @property
    def comments(self):
        comments = []
        for action in self.actions.all():
            if action.comment and action.comment not in comments:
                # don't add comments that are NoneTypes or if the comment is a duplicate
                comments.append(action.comment)

        return " ".join(comments)

    class Meta:
        unique_together = ("event_id", "instrument")
        ordering = ("event_id",)

    def __str__(self):
        return f"{self.event_id} - {self.station.name} - {self.instrument.name}"


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
    latitude = models.DecimalField(verbose_name=_("Latitude"), blank=True, null=True, decimal_places=6, max_digits=8)
    longitude = models.DecimalField(verbose_name=_("Longitude"), blank=True, null=True, decimal_places=6, max_digits=9)

    # The file this action was loaded from. Events can span different files, but they can also be entered
    # manually so this allows us to track an action back to the file it comes from, if it comes
    # from a file.
    file = models.CharField(verbose_name=_("File Name"), max_length=100, null=True, blank=True)

    # mid helps us track issues, but in the event that this was a manually entered action this will be null
    mid = models.IntegerField(verbose_name="$@MID@$", null=True, blank=True)

    type = models.IntegerField(verbose_name=_("Action Type"), choices=ActionType.choices)
    # if the action is an unknown type then leave a comment here identifying what the 'other' type is
    action_type_other = models.CharField(verbose_name=_("Action Other"), max_length=50, blank=True, null=True,
                                         help_text=_("if the action is an unknown type then leave a comment here "
                                                     "identifying what the 'other' type is"))

    # the data collector would be the person who fired the event on the ship. For BIO this would be the 'Author' field
    data_collector = models.CharField(verbose_name=_("Data Collector"), max_length=100, blank=True, null=True)
    sounding = models.FloatField(verbose_name=_("Sounding"), blank=True, null=True)

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
        ordering = ('date_time',)


# In reality a sensor is physically attached to an instrument, but depending on a station's depth a sensor might be
# removed. The Ph sensor for example is only rated to 1,200m, if a station is deeper than that the Ph sensor has to be
# removed. In which case it makes more 'database' sense to attached the sensor to an event.
class Attachment(models.Model):
    event = models.ForeignKey(Event, verbose_name=_("Event"), related_name="attachments", on_delete=models.CASCADE)
    name = models.CharField(verbose_name=_("Attachment Name"), max_length=50)

    def __str__(self):
        return f"{self.name}"


# A variable field has a variable name because variable names can be reused. Instead of having 50 variable fields
# with the name 'Flowmeter Start' taking up DB space we have one Variable Name 'Flowmeter Start' referenced
# 50 times in the VariableField. Integers take up less space than strings. SimpleLookupName can also be used
# later on to add bilingual support
class VariableName(models.Model):
    name = models.CharField(verbose_name=_("Field Name"), max_length=50)

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
    closed = models.DateTimeField(verbose_name=_("Fired Date/Time"))

    # the bottle number is its order from 1 to N in a series of bottles as opposed to the bottle ID which is the
    # label placed on the bottle linking it to all samples that come from that bottle.
    bottle_id = models.IntegerField(verbose_name=_("Bottle ID"))

    # the bottle number will not be present if this is a RingNet event
    bottle_number = models.IntegerField(verbose_name=_("Bottle Number"), blank=True, null=True)

    pressure = models.DecimalField(verbose_name=_("Pressure"), default=0.0, decimal_places=3, max_digits=7)

    latitude = models.DecimalField(verbose_name=_("Latitude"), blank=True, null=True, decimal_places=6, max_digits=8)
    longitude = models.DecimalField(verbose_name=_("Longitude"), blank=True, null=True, decimal_places=6, max_digits=9)

    last_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.bottle_id}:{self.bottle_number}:{self.pressure}:[{self.latitude}, {self.longitude}]"

    class Meta:
        unique_together = ['event', 'bottle_number']
        ordering = ['bottle_id']


# if a biochem datatype is different from the default sample type for a specific mission use the mission sample type
class MissionSampleType(models.Model):
    mission = models.ForeignKey(Mission, verbose_name=_("Mission"), related_name="mission_sample_types",
                                on_delete=models.CASCADE)

    name = models.CharField(verbose_name=_("Short/Column Name"), max_length=20, null=True,
                            help_text=_("The column name of a sensor or a short name commonly used for the sample"))

    long_name = models.CharField(verbose_name=_("Name"), max_length=126, null=True, blank=True,
                                 help_text=_("Short descriptive name for this type of sample/sensor"))

    priority = models.IntegerField(verbose_name=_("Priority"), default=1)

    is_sensor = models.BooleanField(verbose_name=_("Is Sensor"), default=False,
                                    help_text=_("Identify this sample type as a type of sensor"))

    datatype = models.ForeignKey(bio_tables.models.BCDataType, verbose_name=_("BioChem DataType"), null=True,
                                 blank=True, related_name='mission_sample_types', on_delete=models.SET_NULL)

    def __str__(self):
        label = self.name + (f" - {self.long_name}" if self.long_name else "")
        label += f" {self.datatype.data_type_seq} : {self.datatype.description}" if self.datatype else ""

        return label


class BioChemUploadStatus(models.IntegerChoices):
    upload = 1, "upload"
    uploaded = 2, "uploaded"
    delete = 3, "delete"


# BioChemUpload is a table for tracking the last time a sensor or sample was uploaded to biochem. This way we can
# track the data per-mission and let the user know if a sample has been uploaded, was modified and needs
# to be re-uploaded, or hasn't been loaded yet.
class BioChemUpload(models.Model):
    type = models.ForeignKey(MissionSampleType, verbose_name=_("Type"), on_delete=models.CASCADE,
                             related_name='uploads')

    upload_date = models.DateTimeField(verbose_name=_("Upload Date"), null=True, blank=True,
                                       help_text=_("The last time this sensor/sample was uploaded to biochem"))
    modified_date = models.DateTimeField(verbose_name=_("Modified Date"), null=True, blank=True, auto_now=True,
                                         help_text=_("The last time this sensor/sample was loaded"))

    status = models.IntegerField(verbose_name=_("Status"), null=True, blank=True, choices=BioChemUploadStatus.choices)


# The Sample model tracks sample/sensor types that can or have been uploaded for a specific bottle. It can also
# track the file data for the sensor was loaded from
class Sample(models.Model):
    bottle = models.ForeignKey(Bottle, verbose_name=_("Bottle"), on_delete=models.CASCADE, related_name='samples')
    type = models.ForeignKey(MissionSampleType, verbose_name=_("Type"), on_delete=models.CASCADE,
                             related_name='samples')

    file = models.CharField(verbose_name=_("File Name"), max_length=50, null=True, blank=True)

    last_modified = models.DateTimeField(verbose_name=_("Sample Modified"),
                                         help_text=_("Date sample was last updated"), auto_now=True)

    def __str__(self):
        return f'{self.type}: {self.bottle.bottle_id}'


# Most samples loaded are 'Discrete' chemical or mineral measurements. The DiscreteSampleValue table tracks those
# values, but can also be used to keep track of replicates (when a sample has more than one value), data quality flags
# individual BioChem datatypes (for when the data type is different or more descriptive than the sensor/sample
# general datatype), and comments related to the sample.
class DiscreteSampleValue(models.Model):
    sample = models.ForeignKey(Sample, verbose_name=_("Sample"), on_delete=models.CASCADE,
                               related_name='discrete_values')
    value = models.FloatField(verbose_name=_("Value"), null=True)  # values can be null, but must not be blank

    replicate = models.IntegerField(verbose_name=_("Replicate #"), default=1,
                                    help_text=_("Replicates occur when there are multiple samples of the same type "
                                                "form the same bottle."))

    flag = models.IntegerField(verbose_name=_("Data Quality Flag"), null=True, blank=True)

    # According to the BioChem - BioChem_Discrete_Simple_ERD.pdf
    #   BCDiscreteReplicates.Detection_Limit is a Number (11, 5) column
    limit = models.DecimalField(verbose_name=_("Detection Limit"), null=True, blank=True, max_digits=11,
                                decimal_places=5)

    # Individual samples can have different datatype than the general datatype provided by the
    # sample type. If this is blank the sample.type.datatype value should be used for the sample
    datatype = models.ForeignKey(bio_tables.models.BCDataType, verbose_name=_("BioChem DataType"), null=True,
                                 blank=True, on_delete=models.SET_NULL)

    bio_upload_date = models.DateTimeField(verbose_name=_("BioChem Uploaded"), blank=True, null=True,
                                           help_text=_("Date of last BioChem upload"))

    comment = models.TextField(verbose_name=_("Sample Comments"), null=True, blank=True)

    # The dis_data_num is used to link a sample to the BCD version of the sample once it's been uploaded to
    # the BCD table. This is then used when updates are made to the DART DiscreteSample to keep it in sync
    # with the BCD sample.
    dis_data_num = models.IntegerField(verbose_name=_("BioChem Data Number"), null=True, blank=True,
                                       help_text=_("The BCD unique ID provided once a sample has been uploaded"))

    def __str__(self):
        return f'{self.sample}: {self.value}'


class PlanktonSample(models.Model):
    file = models.FileField(verbose_name=_("File"))

    # Zooplankton will come from bottles linked to net events. Phytoplankton will come from bottles linked to CTD events
    bottle = models.ForeignKey(Bottle, verbose_name="Bottle", related_name="plankton_data", on_delete=models.CASCADE)

    # Phytoplankton is collected from multiple Niskin bottles for ONLY station HL_02. Previously, the AZMP template
    # used the code 90000019, which is for a 10L Niskin bottle. Lindsay has asked me to use 90000002 for a Niskin
    # bottle, size unknown, with an option for the user to set the "bottle" type in the future.
    #
    # in the AZMP template, Robert uses 90000102 (0.75 m) if the net is a 202um mesh and
    # 90000105 (0.5 m) if it's a 76um or 70um mesh for Zooplankton
    gear_type = models.ForeignKey(bio_tables.models.BCGear, verbose_name="Gear Type", related_name="plankton_data",
                                  on_delete=models.DO_NOTHING, default=90000002)

    taxa = models.ForeignKey(bio_tables.models.BCNatnlTaxonCode, verbose_name=_("Taxonomy"),
                             related_name="plankton_data", on_delete=models.DO_NOTHING)

    # default unassigned BCLIFEHISTORIES 90000000
    stage = models.ForeignKey(bio_tables.models.BCLifeHistory, verbose_name=_("Stage of Life"), default=90000000,
                              on_delete=models.DO_NOTHING)

    # default unassigned BCSEXES 90000000
    sex = models.ForeignKey(bio_tables.models.BCSex, verbose_name=_("Sex"), default=90000000,
                            on_delete=models.DO_NOTHING)

    # 1 for phytoplankton, more complicated for zooplankton
    split_fraction = models.FloatField(verbose_name=_("Split Fraction"), default=1)

    # these defaults are for phytoplankton, more complicated for zooplankton
    min_sieve = models.FloatField(verbose_name=_("Max Sieve"), default=0.002)
    max_sieve = models.FloatField(verbose_name=_("Max Sieve"), blank=True, null=True, default=0.55)

    # Phytoplankton normally comes from CTD bottles, but there are 76um and 70um nets used normally on 0.5m rings.
    # The mesh can normally be used to determine the gear_type, but if the gear type is set to
    # 90000105 (0.5m diameter ring), the net could be a 76um *or* a 70um mesh.
    # The mesh size goes into the BCS_P table so it has to be tracked for later.
    mesh_size = models.IntegerField(verbose_name=_("Mesh Size"), help_text=_("Mesh size of the net material in um"),
                                    blank=True, null=True)

    # The 'what_was_it' code will determine which of these values gets filled out for Zooplankton
    # count = cell_liters for Phytoplankton, the rest are blank
    count = models.IntegerField(verbose_name=_("count"), blank=True, null=True)
    raw_wet_weight = models.FloatField(verbose_name=_("Weight Weight"), blank=True, null=True)
    raw_dry_weight = models.FloatField(verbose_name=_("Dry Weight"), blank=True, null=True)
    volume = models.FloatField(verbose_name=_("Volume"), blank=True, null=True)
    percent = models.FloatField(verbose_name=_("Percent"), blank=True, null=True)

    comments = models.CharField(verbose_name=_("Comments"), blank=True, null=True, max_length=255)

    # The procedure code is because parsing zooplankton is dumb. The same plankton will show up
    # multiple times for one sample and the proc_code determines what record the value should be written
    # to, but it's also used for totals. Large_biomass, Small_biomass, Totwt and dry_weight all use the same
    # NCODE and 'what_was_it' value. The only thing unique about them in the file is the proc_code.
    proc_code = models.IntegerField(verbose_name=_("Procedure Code"), default=9999)

    plank_data_num = models.IntegerField(verbose_name=_("Plankton data number"), blank=True, null=True,
                                         help_text=_("key linking this plankton sample to a biochem staging table"))

    @property
    def plank_sample_key_value(self):
        event = self.bottle.event
        mission = event.mission
        return f'{mission.mission_descriptor}_{event.event_id:03d}_{self.bottle.bottle_id}_{self.gear_type.gear_seq}'

    @property
    def collector_comment(self):
        if self.raw_wet_weight == -1 or self.raw_dry_weight == -1:
            return 'TOO MUCH PHYTOPLANKTON TO WEIGH'

        if self.raw_wet_weight == -2 or self.raw_dry_weight == -2:
            return 'TOO MUCH SEDIMENT TO WEIGH'

        if self.raw_wet_weight == -3 or self.raw_dry_weight == -3:
            return 'NO FORMALIN - COULD NOT WEIGH'

        if self.raw_wet_weight == -4 or self.raw_dry_weight == -4:
            return 'TOO MUCH JELLY TO WEIGH'

        return None


# These are some of the common errors that occur when processing data and allow us to sort various errors depending
# on what problems we're using the errors to solve.
class ErrorType(models.IntegerChoices):
    unknown = 0, "Unknown"
    missing_id = 1, "Missing ID"
    missing_value = 2, "Missing Value"
    validation = 3, "Validation Error"
    bottle = 4, "Bottle Error"
    biochem = 5, "Biochem Error"
    event = 6, "Event Error"
    sample = 7, "Sample Error"
    plankton = 8, "Plankton Error"


# This is the basis for most errors that we want to report to the user. All errors should have at the very least
# a message and what type of error it is.
class AbstractError(models.Model):
    class Meta:
        abstract = True

    message = models.CharField(max_length=255, verbose_name=_("Message"))
    type = models.IntegerField(verbose_name=_("Error type"), default=0, choices=ErrorType.choices)

    # The error code can be used to be more specific than an error type
    code = models.IntegerField(verbose_name=_("Error code"), default=-1)


# General errors we want to keep track of and notify the user about
class Error(AbstractError):
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='errors', verbose_name=_("Mission"))


# Errors that take place when validating an object. This might be something like a missing attachment, date or sample ID
class ValidationError(AbstractError):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='validation_errors',
                              verbose_name=_("Event"))

    def __str__(self):
        return f"{self.get_type_display()} : {self.message}"


# File errors occur when reading data from a file before an object is created, it's fundamentally something wrong with
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
