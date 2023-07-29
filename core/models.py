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


class Instrument(models.Model):
    name = models.CharField(max_length=50, verbose_name=_("Instrument"))
    type = models.IntegerField(verbose_name=_("Instrument type"), default=999, choices=InstrumentType.choices)

    def __str__(self):
        return f"{self.type} - {self.name}"


class Station(models.Model):
    name = models.CharField(max_length=20, verbose_name=_("Station"))

    def __str__(self):
        return self.name


class Event(models.Model):
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='events', verbose_name=_("Mission"))

    event_id = models.IntegerField(verbose_name=_("Event ID"))
    station = models.ForeignKey(Station, on_delete=models.DO_NOTHING, verbose_name=_("Station"), related_name="events")
    instrument = models.ForeignKey(Instrument, on_delete=models.DO_NOTHING, verbose_name=_("Instrument"),
                                   related_name="events")

    sample_id = models.IntegerField(verbose_name=_("Sample ID"), null=True, blank=True)
    end_sample_id = models.IntegerField(verbose_name=_("End Sample ID"), null=True, blank=True)
