from django.db import models
from django.utils.translation import gettext_lazy as _

from core import models as core_models
from bio_tables import models as bio_models


class LocalSetting(models.Model):
    database_location = models.FilePathField(verbose_name=_("Mission Database(s) Path"), default="./missions",
                                             help_text=_("Location of individual mission databases"))

    connected = models.BooleanField(verbose_name="Connected", default=False)


# Sample types help us track sensors and samples that have been previously loaded for any mission, when we see a
# sensor or sample with the same short name in the future we'll know what biochem data types to use as well as what
# file configurations to use when loading that data.
class GlobalSampleType(models.Model):
    short_name = models.CharField(verbose_name=_("Short/Column Name"), max_length=20,
                                  help_text=_("The column name of a sensor or a short name commonly "
                                              "used for the sample"), unique=True)
    long_name = models.CharField(verbose_name=_("Name"), max_length=126, null=True, blank=True,
                                 help_text=_("Short descriptive name for this type of sample/sensor"))

    # priority will eventually allow a user to sort their sample types on the Mission Sample form
    priority = models.IntegerField(verbose_name=_("Priority"), default=1)

    # Datatype may not be known by the user at the time they need to create this sensor, but it will
    # have to be specified before BioChem tables can be created
    datatype = models.ForeignKey(bio_models.BCDataType, verbose_name=_("BioChem DataType"), null=True,
                                 blank=True, related_name='sample_types', on_delete=models.SET_NULL)

    is_sensor = models.BooleanField(verbose_name=_("Is Sensor"), default=False,
                                    help_text=_("Identify this sample type as a type of sensor"))

    class Meta:
        ordering = ('is_sensor', 'short_name')

    def get_mission_sample_type(self, mission: core_models.Mission):
        database = mission._state.db
        mission_sample_type = mission.mission_sample_types.filter(name=self.short_name)
        if not mission_sample_type.exists():
            mission_sample_type = core_models.MissionSampleType(mission=mission,
                                                                name=self.short_name,
                                                                long_name=self.long_name,
                                                                priority=self.priority,
                                                                is_sensor=self.is_sensor,
                                                                datatype=self.datatype)
            mission_sample_type.save(using=database)
        else:
            mission_sample_type = mission_sample_type.first()

        return mission_sample_type

    def __str__(self):
        label = self.short_name + (f" - {self.long_name}" if self.long_name else "")
        label += f" {self.datatype.data_type_seq} : {self.datatype.description}" if self.datatype else ""

        return label


class SampleTypeConfig(models.Model):
    sample_type = models.ForeignKey(GlobalSampleType, verbose_name=_("Sample Type"),
                                    related_name="configs", on_delete=models.DO_NOTHING,
                                    help_text=_("The sample type this config is intended for"))
    file_type = models.CharField(verbose_name=_("File Type"), max_length=5,
                                 help_text=_("file type extension e.g csv, xls, xlsx, dat"))

    skip = models.IntegerField(verbose_name=_("Header Row"), default=0,
                               help_text=_("The row containing headers is often not the first row of a file. "
                                           "This value indicates what row it is normally located on."))

    sample_field = models.CharField(verbose_name=_("Sample Column"), max_length=50,
                                    help_text=_("Lowercase name of the column that contains the bottle ids"))

    value_field = models.CharField(verbose_name=_("Value Column"), max_length=50,
                                   help_text=_("Lowercase name of the column that contains the value data"))

    tab = models.IntegerField(verbose_name=_("Tab"), default=0, help_text=_("The tab number data is located on."
                                                                            "For MS Excel, the first tab is zero"))

    flag_field = models.CharField(verbose_name=_("Flag Column"), max_length=50, blank=True, null=True,
                                  help_text=_("Lowercase name of the column that contains flags, if it exists"))

    limit_field = models.CharField(verbose_name=_("Detection Limit Column"), max_length=50, blank=True, null=True,
                                   help_text=_("Lowercase name of the column that contains flags, if it exists"))

    comment_field = models.CharField(verbose_name=_("Comment Column"), max_length=50, blank=True, null=True,
                                     help_text=_("Lowercase name of the column containing comments, if it exists"))

    allow_blank = models.BooleanField(verbose_name=_("Allow Blank Samples?"), default=True,
                                      help_text=_("Should values be kept if the sample column is blank?"))

    allow_replicate = models.BooleanField(verbose_name=_("Allow Replicate Samples?"), default=True,
                                          help_text=_("Can this sample have replicate sample values?"))

    def __str__(self):
        return f"{self.sample_type}"


class EngineType(models.IntegerChoices):
    oracle = 1, 'Oracle'


class BcDatabaseConnection(models.Model):
    engine = models.IntegerField(verbose_name=_("Database Type"), choices=EngineType.choices,
                                 default=EngineType.oracle)
    host = models.CharField(verbose_name=_("Server Address"), max_length=50)
    name = models.CharField(verbose_name=_("Database Name"), help_text="TTRAN/PTRAN", max_length=20)
    port = models.IntegerField(verbose_name=_("Port"), default=1521)

    account_name = models.CharField(verbose_name=_('Account Name'), max_length=20)
    uploader = models.CharField(verbose_name=_("Uploader Name"), max_length=20, blank=True, null=True,
                                help_text=_("If not Account Name"))

    bc_discrete_data_edits = models.CharField(verbose_name=_("BCD Table Name"), max_length=60,
                                              default='BCDISCRETEDATAEDITS')
    bc_discrete_station_edits = models.CharField(verbose_name=_("BCD Table Name"), max_length=60,
                                                 default='BCDISCRETESTATNEDITS')
    bc_plankton_data_edits = models.CharField(verbose_name=_("BCD Table Name"), max_length=60,
                                              default='BCPLANKTONDATAEDITS')
    bc_plankton_station_edits = models.CharField(verbose_name=_("BCD Table Name"), max_length=60,
                                                 default='BCPLANKTONSTATNEDITS')

    def __str__(self):
        return f'{self.account_name} - {self.name}'

    # create a django database connection dictionary to be used with django-dynamic-db-router
    def connect(self, password):
        # at the moment we only handle Oracle Biochem DBs, but this could be expanded in the future
        engine = 'django.db.backends.oracle'

        biochem_db = {
            'ENGINE': engine,
            'NAME': self.name,
            'USER': self.account_name,
            'PASSWORD': password,
            'PORT': self.port,
            'HOST': self.host,
            'TIME_ZONE': None,
            'CONN_HEALTH_CHECKS': False,
            'CONN_MAX_AGE': 0,
            'AUTOCOMMIT': True,
            'ATOMIC_REQUESTS': False,
            'OPTIONS': {}
        }

        return biochem_db


# File configuration should be used by parsers that will create entries for what fields they require
class FileConfiguration(models.Model):
    file_type = models.CharField(max_length=20)
    required_field = models.CharField(max_length=50, verbose_name=_("Required Field"),
                                      help_text=_("This is a field the parser will require to set DART table values"))
    mapped_field = models.CharField(max_length=50, verbose_name=_("Mapped Field"),
                                    help_text=_("This is the field as it appears in the file being parsed"))
    description = models.TextField(verbose_name=_("Description"),
                                   help_text=_("Description of the purpose of the mapped field"))


class GlobalStation(models.Model):
    name = models.CharField(verbose_name=_("Station Name"), max_length=20, unique=True)

    latitude = models.FloatField(verbose_name=_("Latitude"), blank=True, null=True)
    longitude = models.FloatField(verbose_name=_("Longitude"), blank=True, null=True)
    sounding = models.FloatField(verbose_name=_("Sounding"), blank=True, null=True)
    fixstation = models.BooleanField(verbose_name=_("Fix Station"), default=False)

    def __str__(self):
        return self.name


class GlobalGeographicRegion(models.Model):
    name = models.CharField(verbose_name=_("Geographic Region Name"), max_length=100, unique=True)

    def __str__(self):
        return self.name
