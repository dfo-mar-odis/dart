from django.db import models

# Create your models here.
from django.utils.translation import gettext as _


class BCUpdate(models.Model):
    last_update = models.DateTimeField(verbose_name=_("Last Updated"))


class BCDataCenter(models.Model):
    data_center_code = models.IntegerField(verbose_name=_("Data Center Code"), primary_key=True)
    name = models.CharField(verbose_name=_("Data Center Name"), max_length=50)
    location = models.CharField(verbose_name=_("Data Center Location"), max_length=50)
    description = models.CharField(verbose_name=_("Data Center Description"), max_length=100, blank=True, null=True)

    def __str__(self):
        return f'{self.name}: {self.location} - {self.description}'


class BCUnit(models.Model):
    unit_seq = models.IntegerField(verbose_name=_("Unit Code"), primary_key=True)
    data_center_code = models.ForeignKey(BCDataCenter, verbose_name=_("Data Center"),
                                         related_name="units", on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=20, verbose_name=_("Name"))
    description = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Description"))

    def __str__(self):
        return f'{self.name}: {self.data_center_code.name} - {self.description}'


class BCDataRetrieval(models.Model):
    data_retrieval_seq = models.IntegerField(primary_key=True, verbose_name=_("Data Retrieval"))
    data_center_code = models.ForeignKey(BCDataCenter, verbose_name=_("Data Center"), related_name="data_retrievals",
                                         on_delete=models.DO_NOTHING)
    parameter_name = models.CharField(max_length=20, verbose_name=_("Parameter Name"))
    parameter_description = models.CharField(max_length=100, verbose_name=_("Parameter Description"))
    unit_seq = models.ForeignKey(BCUnit, verbose_name=_("Units"), related_name="data_retrievals",
                                 on_delete=models.DO_NOTHING)
    places_before = models.IntegerField(verbose_name=_("Places Before Decimal"))
    places_after = models.IntegerField(verbose_name=_("Places After Decimal"))
    minimum_value = models.DecimalField(max_digits=12, decimal_places=5, blank=True, null=True,
                                        verbose_name=_("Maximum Value"))
    maximum_value = models.DecimalField(max_digits=12, decimal_places=5, blank=True, null=True,
                                        verbose_name=_("Minimum Value"))
    originally_entered_by = models.CharField(max_length=30, verbose_name=_("Original Creator"))

    def __str__(self):
        return f'{self.parameter_name} ({self.unit_seq}): {self.parameter_description}'


class BCAnalysis(models.Model):
    analysis_seq = models.IntegerField(primary_key=True, verbose_name=_("Analysis Code"))
    data_center_code = models.ForeignKey(BCDataCenter, verbose_name=_("Data Center"), related_name="data_analyses",
                                         on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=30, verbose_name=_("Name"))
    description = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Description"))

    def __str__(self):
        return f'{self.name}: {self.description}'


class BCStorage(models.Model):
    storage_seq = models.IntegerField(primary_key=True, verbose_name=_("Storage Method"))
    data_center_code = models.ForeignKey(BCDataCenter, verbose_name=_("Data Center"), related_name="storages",
                                         on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=30, verbose_name=_("Name"))
    description = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Description"))

    def __str__(self):
        return f'{self.name}: {self.description}'


class BCSampleHandling(models.Model):
    sample_handling_seq = models.IntegerField(primary_key=True, verbose_name=_("Sample Handling Method"))
    data_center_code = models.ForeignKey(BCDataCenter, verbose_name=_("Data Center"), related_name="sample_handlings",
                                         on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=30, verbose_name=_("Name"))
    description = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Description"))

    def __str__(self):
        return f'{self.name}: {self.description}'


class BCPreservation(models.Model):
    preservation_seq = models.IntegerField(primary_key=True, verbose_name=_("Preservation Method"))
    data_center_code = models.ForeignKey(BCDataCenter, verbose_name=_("Data Center"), related_name="preservations",
                                         on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=30, verbose_name=_("Name"))
    description = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Description"))
    type = models.CharField(max_length=30, blank=True, null=True, verbose_name=_("Type"))

    def __str__(self):
        return f'{self.name}: {self.description}'


class BCDataType(models.Model):
    data_type_seq = models.IntegerField(primary_key=True, verbose_name=_("Data Type"))
    data_center_code = models.ForeignKey(BCDataCenter, verbose_name=_("Data Center"), related_name="data_types",
                                         on_delete=models.DO_NOTHING)
    data_retrieval = models.ForeignKey(BCDataRetrieval, verbose_name=_("Data Retrieval"), related_name="data_types",
                                           on_delete=models.DO_NOTHING)
    analysis = models.ForeignKey(BCAnalysis, verbose_name=_("Analysis"), related_name="data_types",
                                    on_delete=models.DO_NOTHING)
    preservation = models.ForeignKey(BCPreservation, verbose_name=_("Preservation"), related_name="data_types",
                                         on_delete=models.DO_NOTHING)
    sample_handling = models.ForeignKey(BCSampleHandling, verbose_name=_("Sample Handling"),
                                            related_name="data_types", on_delete=models.DO_NOTHING)
    storage = models.ForeignKey(BCStorage, verbose_name=_("Storage"),
                                    related_name="data_types", on_delete=models.DO_NOTHING)
    unit = models.ForeignKey(BCUnit, verbose_name=_("Unit"), related_name="data_types",
                                 on_delete=models.DO_NOTHING)
    description = models.CharField(max_length=250, verbose_name=_("Description"))
    conversion_equation = models.CharField(max_length=250, blank=True, null=True, verbose_name=_("Conversion Equation"))
    originally_entered_by = models.CharField(max_length=30, verbose_name=_("Original Creator"))
    method = models.CharField(max_length=20, verbose_name=_("Method"))
    priority = models.IntegerField(verbose_name=_("Priority"))
    p_code = models.CharField(max_length=4, blank=True, null=True, verbose_name=_("P Code"))
    bodc_code = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("BODC Code"))

    def __str__(self):
        return f'{self.data_type_seq}: {self.description}'


class BCNatnlTaxonCode(models.Model):
    national_taxonomic_seq = models.BigIntegerField(primary_key=True, verbose_name=_("Data Center"))
    data_center_code = models.ForeignKey(BCDataCenter, on_delete=models.DO_NOTHING, related_name='taxon_codes',
                                         verbose_name=_("Data Center"))
    tsn = models.BigIntegerField(verbose_name=_("TSN ID"))
    taxonomic_name = models.CharField(max_length=100, verbose_name=_("Taxonomic Name"))
    best_nodc7 = models.BigIntegerField(verbose_name=_("Best NODC7"))
    authority = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Authority"))
    collectors_comment = models.CharField(max_length=2000, blank=True, null=True, verbose_name=_("Collector Comment"))
    data_managers_comment = models.CharField(max_length=2000, blank=True, null=True,
                                             verbose_name=_("Data Manager Comment"))
    short_name = models.CharField(max_length=15, blank=True, null=True, verbose_name=_("Short Name"))
    tsn_itis = models.BigIntegerField(blank=True, null=True, verbose_name=_("TSN ITIS ID"))
    aphiaid = models.BigIntegerField(blank=True, null=True, verbose_name=_("APHIA ID"))


class BCGear(models.Model):
    gear_seq = models.IntegerField(primary_key=True, verbose_name=_("Gear ID"))
    data_center_code = models.ForeignKey(BCDataCenter, on_delete=models.DO_NOTHING, related_name='gear_codes',
                                         verbose_name=_("Data Center"))
    type = models.CharField(max_length=40, verbose_name=_("Type"))
    model = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Model"))
    gear_size = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Size"))
    description = models.CharField(max_length=2000, blank=True, null=True, verbose_name=_("Description"))

