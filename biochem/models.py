from django.db import models


class Bcdatacenters(models.Model):
    data_center_code = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=50)
    location = models.CharField(max_length=50)
    description = models.CharField(max_length=100, blank=True, null=True)
    data_manager_only = models.CharField(max_length=1, blank=True, null=True)
    dfo_only = models.CharField(max_length=1, blank=True, null=True)
    region_only = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Bcdatacenters'


class Bcunits(models.Model):
    unit_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    name = models.CharField(max_length=20)
    description = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False  # Created from a view. Don't remove.
        db_table = 'bcunits'


class Bcstorages(models.Model):
    storage_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=250, blank=True, null=True)

    class Meta:
        managed = False  # Created from a view. Don't remove.
        db_table = 'bcstorages'


class Bcsamplehandlings(models.Model):
    sample_handling_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=250, blank=True, null=True)

    class Meta:
        managed = False  # Created from a view. Don't remove.
        db_table = 'bcsamplehandlings'


class Bcpreservations(models.Model):
    preservation_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=250, blank=True, null=True)
    type = models.CharField(max_length=30, blank=True, null=True)

    class Meta:
        managed = False  # Created from a view. Don't remove.
        db_table = 'bcpreservations'


class Bcanalyses(models.Model):
    analysis_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=250, blank=True, null=True)

    class Meta:
        managed = False  # Created from a view. Don't remove.
        db_table = 'bcanalyses'


class Bcdataretrievals(models.Model):
    data_retrieval_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    parameter_name = models.CharField(max_length=20)
    parameter_description = models.CharField(max_length=100)
    unit_seq = models.IntegerField()
    places_before = models.IntegerField()
    places_after = models.IntegerField()
    minimum_value = models.DecimalField(max_digits=12, decimal_places=5, blank=True, null=True)
    maximum_value = models.DecimalField(max_digits=12, decimal_places=5, blank=True, null=True)
    originally_entered_by = models.CharField(max_length=30)

    class Meta:
        managed = False  # Created from a view. Don't remove.
        db_table = 'bcdataretrievals'


class Bcdatatypes(models.Model):
    data_type_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    data_retrieval_seq = models.IntegerField()
    analysis_seq = models.IntegerField()
    preservation_seq = models.IntegerField()
    sample_handling_seq = models.IntegerField()
    storage_seq = models.IntegerField()
    unit_seq = models.IntegerField()
    description = models.CharField(max_length=250)
    conversion_equation = models.CharField(max_length=250, blank=True, null=True)
    originally_entered_by = models.CharField(max_length=30)
    method = models.CharField(max_length=20)
    priority = models.IntegerField()
    p_code = models.CharField(max_length=4, blank=True, null=True)
    bodc_code = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False  # Created from a view. Don't remove.
        db_table = 'bcdatatypes'


class Bcgears(models.Model):
    gear_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    type = models.CharField(max_length=40)
    model = models.CharField(max_length=50, blank=True, null=True)
    gear_size = models.CharField(max_length=20, blank=True, null=True)
    description = models.CharField(max_length=2000, blank=True, null=True)

    class Meta:
        managed = False  # Created from a view. Don't remove.
        db_table = 'bcgears'


# This matches the Biochem.BCDiscreteDataEdits table
class BcdD(models.Model):
    dis_data_num = models.IntegerField(primary_key=True)
    mission_descriptor = models.CharField(max_length=50, blank=True, null=True)
    event_collector_event_id = models.CharField(max_length=50, blank=True, null=True)
    event_collector_stn_name = models.CharField(max_length=50, blank=True, null=True)
    dis_header_start_depth = models.DecimalField(max_digits=9, decimal_places=3, blank=True, null=True)
    dis_header_end_depth = models.DecimalField(max_digits=9, decimal_places=3, blank=True, null=True)
    dis_header_slat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    dis_header_slon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    dis_header_sdate = models.DateField(blank=True, null=True)
    dis_header_stime = models.IntegerField(blank=True, null=True)
    dis_detail_data_type_seq = models.IntegerField(blank=True, null=True)
    data_type_method = models.CharField(max_length=20, blank=True, null=True)
    dis_detail_data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    dis_detail_data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    dis_detail_detection_limit = models.DecimalField(max_digits=11, decimal_places=5, blank=True, null=True)
    dis_detail_detail_collector = models.CharField(max_length=50, blank=True, null=True)
    dis_detail_collector_samp_id = models.CharField(max_length=50, blank=True, null=True)
    created_by = models.CharField(max_length=30)
    created_date = models.DateField()
    data_center_code = models.IntegerField(blank=True, null=True)

    # The process flag is used by the Biochem upload app to indicate if the data should be processed by
    # the application. Pl/SQL code is run on the table and this flag is set to 'DVE' depending on
    # if the data validates.
    process_flag = models.CharField(max_length=3, blank=True, null=True)
    batch_seq = models.IntegerField(blank=True, null=True)
    dis_sample_key_value = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        abstract = True
        ordering = ['dis_sample_key_value', 'dis_data_num']

    def __str__(self):
        bcd_str = ", ".join([f"{attr.name}: {getattr(self, attr.name)}" for attr in BcdD._meta.fields if hasattr(self, attr.name)])
        return bcd_str


class BcdDReportModel(BcdD):
    pass


class BcsD(models.Model):
    dis_headr_collector_sample_id = models.CharField(primary_key=True, max_length=50)

    dis_sample_key_value = models.CharField(max_length=50, blank=True, null=True)
    mission_descriptor = models.CharField(max_length=50, blank=True, null=True)
    event_collector_event_id = models.CharField(max_length=50, blank=True, null=True)
    event_collector_stn_name = models.CharField(max_length=50, blank=True, null=True)
    mission_name = models.CharField(max_length=50, blank=True, null=True)
    mission_leader = models.CharField(max_length=50, blank=True, null=True)
    mission_sdate = models.DateField(blank=True, null=True)
    mission_edate = models.DateField(blank=True, null=True)
    mission_institute = models.CharField(max_length=50, blank=True, null=True)
    mission_platform = models.CharField(max_length=50, blank=True, null=True)
    mission_protocol = models.CharField(max_length=50, blank=True, null=True)

    mission_geographic_region = models.CharField(max_length=100, blank=True, null=True)
    mission_collector_comment1 = models.CharField(max_length=2000, blank=True, null=True)
    mission_collector_comment2 = models.CharField(max_length=2000, blank=True, null=True)
    mission_data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)

    event_sdate = models.DateField(blank=True, null=True)
    event_edate = models.DateField(blank=True, null=True)
    event_stime = models.IntegerField(blank=True, null=True)
    event_etime = models.IntegerField(blank=True, null=True)
    event_min_lat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    event_max_lat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    event_min_lon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    event_max_lon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    event_utc_offset = models.DecimalField(max_digits=4, decimal_places=1, blank=True, null=True)

    event_collector_comment1 = models.CharField(max_length=2000, blank=True, null=True)
    event_collector_comment2 = models.CharField(max_length=2000, blank=True, null=True)
    event_data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)

    # Partly done, I use the 90000019 code for Niskin 10L Bottle. The user will have to have the ability to change
    # this value, but I think it could be a mission level option.
    #
    # ################  Lindsay would prefer if we used 90000002, Niskin of unknown size ###########
    dis_headr_gear_seq = models.IntegerField(blank=True, null=True)
    dis_headr_sdate = models.DateField(blank=True, null=True)
    dis_headr_edate = models.DateField(blank=True, null=True)
    dis_headr_stime = models.IntegerField(blank=True, null=True)
    dis_headr_etime = models.IntegerField(blank=True, null=True)
    dis_headr_time_qc_code = models.CharField(max_length=2, blank=True, null=True)
    dis_headr_slat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    dis_headr_elat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    dis_headr_slon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    dis_headr_elon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    dis_headr_position_qc_code = models.CharField(max_length=2, blank=True, null=True)
    dis_headr_start_depth = models.DecimalField(max_digits=9, decimal_places=3, blank=True, null=True)
    dis_headr_end_depth = models.DecimalField(max_digits=9, decimal_places=3, blank=True, null=True)
    dis_headr_sounding = models.IntegerField(blank=True, null=True)
    dis_headr_collector_deplmt_id = models.CharField(max_length=50, blank=True, null=True),  # Done, value is null

    dis_headr_collector = models.CharField(max_length=50, blank=True, null=True)
    dis_headr_collector_comment1 = models.CharField(max_length=2000, blank=True, null=True)  # comes from Sample excel file
    dis_headr_data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)
    dis_headr_responsible_group = models.CharField(max_length=50, blank=True, null=True)

    dis_headr_shared_data = models.CharField(max_length=50, blank=True, null=True),  # Done, value is null
    created_by = models.CharField(max_length=30)
    created_date = models.DateField()
    data_center_code = models.IntegerField(blank=True, null=True)

    # The process flag is used by the Biochem upload app to indicate if the data should be processed by
    # the application. Pl/SQL code is run on the table and this flag is set to 'SVE' depending on
    # if the data validates.
    process_flag = models.CharField(max_length=3, blank=True, null=True)
    batch_seq = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        abstract = True


class BcsDReportModel(BcsD):

    class Meta:
        managed = False


class BcdP(models.Model):
    plank_data_num = models.AutoField(primary_key=True)

    plank_sample_key_value = models.CharField(max_length=50)

    mission_descriptor = models.CharField(max_length=50, blank=True, null=True)
    event_collector_event_id = models.CharField(max_length=50, blank=True, null=True)
    event_collector_stn_name = models.CharField(max_length=50, blank=True, null=True)
    pl_gen_national_taxonomic_seq = models.BigIntegerField(blank=True, null=True)
    pl_gen_collector_taxonomic_id = models.CharField(max_length=20, blank=True, null=True)
    pl_gen_life_history_seq = models.IntegerField(blank=True, null=True)
    pl_gen_trophic_seq = models.IntegerField(blank=True, null=True)
    pl_gen_min_sieve = models.DecimalField(max_digits=8, decimal_places=4, blank=True, null=True)
    pl_gen_max_sieve = models.DecimalField(max_digits=8, decimal_places=4, blank=True, null=True)
    pl_gen_split_fraction = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    pl_gen_sex_seq = models.IntegerField(blank=True, null=True)
    pl_gen_counts = models.DecimalField(max_digits=9, decimal_places=3, blank=True, null=True)
    pl_gen_count_pct = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)
    pl_gen_wet_weight = models.DecimalField(max_digits=9, decimal_places=4, blank=True, null=True)
    pl_gen_dry_weight = models.DecimalField(max_digits=9, decimal_places=4, blank=True, null=True)
    pl_gen_bio_volume = models.DecimalField(max_digits=8, decimal_places=3, blank=True, null=True)
    pl_gen_presence = models.CharField(max_length=1, blank=True, null=True)
    pl_gen_collector_comment = models.CharField(max_length=2000, blank=True, null=True)
    pl_gen_data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)
    pl_gen_source = models.CharField(max_length=30, blank=True, null=True)
    pl_freq_data_type_seq = models.IntegerField(blank=True, null=True)
    pl_freq_upper_bin_size = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)
    pl_freq_lower_bin_size = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)
    pl_freq_bug_count = models.IntegerField(blank=True, null=True)
    pl_freq_bug_seq = models.IntegerField(blank=True, null=True)
    pl_freq_data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    pl_freq_data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    pl_freq_detail_collector = models.CharField(max_length=50, blank=True, null=True)
    pl_detail_data_type_seq = models.IntegerField(blank=True, null=True)
    pl_detail_data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    pl_detail_data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    pl_detail_detail_collector = models.CharField(max_length=50, blank=True, null=True)
    pl_indiv_data_type_seq = models.IntegerField(blank=True, null=True)
    pl_indiv_bug_seq = models.IntegerField(blank=True, null=True)
    pl_indiv_data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    pl_indiv_data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    pl_indiv_data_collector = models.CharField(max_length=50, blank=True, null=True)
    created_by = models.CharField(max_length=30)
    created_date = models.DateField()
    data_center_code = models.IntegerField(blank=True, null=True)
    process_flag = models.CharField(max_length=3, blank=True, null=True)
    batch_seq = models.IntegerField(blank=True, null=True)
    pl_gen_modifier = models.CharField(max_length=50, blank=True, null=True)
    pl_gen_unit = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        abstract = True


class BcdPReportModel(BcdP):
    pass


class BcsP(models.Model):
    plank_sample_key_value = models.CharField(primary_key=True, max_length=50)

    mission_name = models.CharField(max_length=50, blank=True, null=True)  # done
    mission_descriptor = models.CharField(max_length=50, blank=True, null=True)  # done
    mission_leader = models.CharField(max_length=50, blank=True, null=True)  # done
    mission_sdate = models.DateField(blank=True, null=True)  # done
    mission_edate = models.DateField(blank=True, null=True)  # done
    mission_institute = models.CharField(max_length=50, blank=True, null=True)  # done
    mission_platform = models.CharField(max_length=50, blank=True, null=True)  # done
    mission_protocol = models.CharField(max_length=50, blank=True, null=True)  # done
    mission_geographic_region = models.CharField(max_length=100, blank=True, null=True)  # done
    mission_collector_comment = models.CharField(max_length=2000, blank=True, null=True)  # done
    mission_more_comment = models.CharField(max_length=2000, blank=True, null=True)  # done
    mission_data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)  # done
    event_sdate = models.DateField(blank=True, null=True)  # done
    event_edate = models.DateField(blank=True, null=True)  # done
    event_stime = models.IntegerField(blank=True, null=True)  # done
    event_etime = models.IntegerField(blank=True, null=True)  # done
    event_min_lat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)  # done
    event_max_lat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)  # done
    event_min_lon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)  # done
    event_max_lon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)  # done
    event_collector_stn_name = models.CharField(max_length=50, blank=True, null=True)  # done
    event_collector_event_id = models.CharField(max_length=50, blank=True, null=True)  # done
    event_utc_offset = models.DecimalField(max_digits=4, decimal_places=1, blank=True, null=True)  # done
    event_collector_comment = models.CharField(max_length=2000, blank=True, null=True)  # null in existing data
    event_more_comment = models.CharField(max_length=2000, blank=True, null=True)  # null in existing data

    # Appears as "Created using AZMP Data Entry Template" in existing data.
    event_data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)

    # Partly done, for plankton this depends on if it's zoo or phyto,
    # Zooplankton comes from nets, phyto plankton comes from bottles
    #
    # I use the 90000019 code for Niskin 10L Bottle. The user will have to have the ability to change
    # this value, but I think it could be a mission level option.
    #
    # ################  Lindsay would prefer if we used 90000002, Niskin of unknown size ###########
    pl_headr_gear_seq = models.IntegerField(blank=True, null=True)  # done
    pl_headr_sdate = models.DateField(blank=True, null=True)  # done
    pl_headr_edate = models.DateField(blank=True, null=True)  # done
    pl_headr_stime = models.IntegerField(blank=True, null=True)  # done
    pl_headr_etime = models.IntegerField(blank=True, null=True)  # done
    pl_headr_phase_of_daylight = models.CharField(max_length=15, blank=True, null=True)  # null in existing data
    pl_headr_slat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)  # done
    pl_headr_elat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)  # done
    pl_headr_slon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)  # done
    pl_headr_elon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)  # done
    pl_headr_time_qc_code = models.CharField(max_length=2, blank=True, null=True)  # done
    pl_headr_position_qc_code = models.CharField(max_length=2, blank=True, null=True)  # done
    pl_headr_start_depth = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)  # done
    pl_headr_end_depth = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)  # done
    pl_headr_sounding = models.IntegerField(blank=True, null=True)
    pl_headr_volume = models.DecimalField(max_digits=7, decimal_places=3, blank=True, null=True)
    pl_headr_volume_method_seq = models.IntegerField(blank=True, null=True)
    pl_headr_lrg_plankton_removed = models.CharField(max_length=1, blank=True, null=True)  # 'Y'
    pl_headr_mesh_size = models.IntegerField(blank=True, null=True)  # 0 if phyto, 202 or 76 if zoo
    pl_headr_collection_method_seq = models.IntegerField(blank=True, null=True)
    pl_headr_collector_deplmt_id = models.CharField(max_length=50, blank=True, null=True)
    pl_headr_collector_sample_id = models.CharField(max_length=50, blank=True, null=True)  # done
    pl_headr_procedure_seq = models.IntegerField(blank=True, null=True)  # 90000001 'quantitative'
    pl_headr_preservation_seq = models.IntegerField(blank=True, null=True)  # 90000039 'formaldehyde'
    pl_headr_storage_seq = models.IntegerField(blank=True, null=True)  # 90000016 seems to be the default
    pl_headr_collector = models.CharField(max_length=50, blank=True, null=True)  # seems to be the event data_collector
    pl_headr_collector_comment = models.CharField(max_length=2000, blank=True, null=True)
    pl_headr_meters_sqd_flag = models.CharField(max_length=1, blank=True, null=True)  # seems to be 'Y' in existing data

    # Appears as "Created using AZMP Data Entry Template" in existing data.
    pl_headr_data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)

    pl_headr_responsible_group = models.CharField(max_length=50, blank=True, null=True)  # 'AZMP' in existing data
    pl_headr_shared_data = models.CharField(max_length=50, blank=True, null=True)  # 'N' in existing data
    created_by = models.CharField(max_length=30)  # done
    created_date = models.DateField()  # done
    data_center_code = models.IntegerField(blank=True, null=True)  # done
    process_flag = models.CharField(max_length=3, blank=True, null=True)  # done
    batch_seq = models.IntegerField(blank=True, null=True)  # done

    class Meta:
        managed = False
        abstract = True


class BcsPReportModel(BcsP):

    class Meta:
        managed = False


# For demonstration purposes
class TestAzmpUploadBCD(models.Model):
    class Meta:
        managed = False
        app_label = 'biochem'

    dis_data_num = models.AutoField(primary_key=True)
    unit = models.ForeignKey(Bcunits, related_name="bcd_entries", on_delete=models.DO_NOTHING, blank=True, null=True)
    mission_descriptor = models.CharField(max_length=50, blank=True, null=True)
    event_collector_event_id = models.CharField(max_length=50, blank=True, null=True)
    event_collector_stn_name = models.CharField(max_length=50, blank=True, null=True)
    dis_header_start_depth = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    dis_header_end_depth = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    dis_header_slat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    dis_header_slon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    dis_header_sdate = models.DateField(blank=True, null=True)
    dis_header_stime = models.IntegerField(blank=True, null=True)
    dis_detail_data_type_seq = models.IntegerField(blank=True, null=True)
    data_type_method = models.CharField(max_length=20, blank=True, null=True)
    dis_detail_data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    dis_detail_data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    dis_detail_detection_limit = models.DecimalField(max_digits=11, decimal_places=5, blank=True, null=True)
    dis_detail_detail_collector = models.CharField(max_length=50, blank=True, null=True)
    dis_detail_collector_samp_id = models.CharField(max_length=50, blank=True, null=True)
    created_by = models.CharField(max_length=30)
    created_date = models.DateField()
    data_center_code = models.IntegerField(blank=True, null=True)
    process_flag = models.CharField(max_length=3, blank=True, null=True)
    batch_seq = models.IntegerField(blank=True, null=True)
    dis_sample_key_value = models.CharField(max_length=50, blank=True, null=True)


class Bcnatnltaxoncodes(models.Model):
    national_taxonomic_seq = models.BigIntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    tsn = models.BigIntegerField()
    taxonomic_name = models.CharField(max_length=100)
    best_nodc7 = models.BigIntegerField()
    authority = models.CharField(max_length=50, blank=True, null=True)
    collectors_comment = models.CharField(max_length=2000, blank=True, null=True)
    data_managers_comment = models.CharField(max_length=2000, blank=True, null=True)
    short_name = models.CharField(max_length=15, blank=True, null=True)
    tsn_itis = models.BigIntegerField(blank=True, null=True)
    aphiaid = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCNATNLTAXONCODES'


class Bcsexes(models.Model):
    sex_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=1000, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCSEXES'


class Bclifehistories(models.Model):
    life_history_seq = models.IntegerField(primary_key=True,)
    data_center_code = models.IntegerField()
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=1000, blank=True, null=True)
    molt_number = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCLIFEHISTORIES'


class Bccollectionmethods(models.Model):
    collection_method_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=1000, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCCOLLECTIONMETHODS'


class Bcprocedures(models.Model):
    procedure_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=1000, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCPROCEDURES'


class Bcvolumemethods(models.Model):
    volume_method_seq = models.IntegerField(primary_key=True)
    data_center_code = models.IntegerField()
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=1000, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCVOLUMEMETHODS'


class Bcbatches(models.Model):
    batch_seq = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=250, blank=True, null=True)
    username = models.CharField(max_length=30)

    class Meta:
        managed = False
        db_table = 'BCBATCHES'


class Bcactivityedits(models.Model):
    activity_edt_seq = models.BigIntegerField(primary_key=True)  # The composite primary key (activity_edt_seq, event_edt_seq) found, that is not supported. The first column is selected.
    event_edt_seq = models.BigIntegerField()
    event_seq = models.BigIntegerField(blank=True, null=True)
    activity_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    data_pointer_code = models.CharField(max_length=2, blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCACTIVITYEDITS'
        unique_together = (('activity_edt_seq', 'event_edt_seq'),)


class Bcerrors(models.Model):
    error_num_seq = models.IntegerField(primary_key=True)
    edit_table_name = models.CharField(max_length=30)
    record_num_seq = models.BigIntegerField()
    column_name = models.CharField(max_length=30)
    error_code = models.IntegerField()
    last_updated_by = models.CharField(max_length=30)
    last_update_date = models.DateField()
    batch_seq = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'BCERRORS'


class Bcstatndataerrors(models.Model):
    statn_data_table_name = models.CharField(max_length=30)
    record_sequence_value = models.CharField(max_length=50, primary_key=True)
    column_name = models.CharField(max_length=30)
    error_code = models.IntegerField()
    statn_data_created_date = models.DateField()
    collector_sample_id = models.CharField(max_length=50)
    batch_seq = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'BCSTATNDATAERRORS'


class Bcerrorcodes(models.Model):
    error_code = models.IntegerField(primary_key=True, db_comment='Code that specifies the validation error in the Edit table system.')
    description = models.CharField(max_length=80, db_comment='Description of the validation error.')
    long_desc = models.CharField(max_length=300, blank=True, null=True, db_comment='Detailed description of the validation error.')
    last_update_by = models.CharField(max_length=30, db_comment='The user id of the user who last updated the Codes in the ERROR_CODE table.')
    last_update_date = models.DateField(db_comment='The date that the last update took place to a specified record in the ERROR_CODE table.')

    class Meta:
        managed = False
        db_table = 'BCERRORCODES'


class Bcmissionedits(models.Model):
    mission_edt_seq = models.BigIntegerField(primary_key=True)
    mission_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    name = models.CharField(max_length=50, blank=True, null=True)
    descriptor = models.CharField(max_length=50, blank=True, null=True)
    leader = models.CharField(max_length=50, blank=True, null=True)
    sdate = models.DateField(blank=True, null=True)
    edate = models.DateField(blank=True, null=True)
    institute = models.CharField(max_length=50, blank=True, null=True)
    platform = models.CharField(max_length=50, blank=True, null=True)
    protocol = models.CharField(max_length=50, blank=True, null=True)
    geographic_region = models.CharField(max_length=100, blank=True, null=True)
    collector_comment = models.CharField(max_length=2000, blank=True, null=True)
    data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)
    more_comment = models.CharField(max_length=1, blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCMISSIONEDITS'


class Bceventedits(models.Model):
    event_edt_seq = models.BigIntegerField(primary_key=True)
    event_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    mission_seq = models.BigIntegerField(blank=True, null=True)
    sdate = models.DateField(blank=True, null=True)
    edate = models.DateField(blank=True, null=True)
    stime = models.IntegerField(blank=True, null=True)
    etime = models.IntegerField(blank=True, null=True)
    min_lat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    max_lat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    min_lon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    max_lon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    collector_station_name = models.CharField(max_length=50, blank=True, null=True)
    collector_event_id = models.CharField(max_length=50, blank=True, null=True)
    utc_offset = models.DecimalField(max_digits=4, decimal_places=1, blank=True, null=True)
    collector_comment = models.CharField(max_length=2000, blank=True, null=True)
    data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)
    more_comment = models.CharField(max_length=1, blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)
    mission_edt_seq = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCEVENTEDITS'


class Bccommentedits(models.Model):
    comment_edt_seq = models.BigIntegerField(primary_key=True)
    comment_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    mission_seq = models.BigIntegerField(blank=True, null=True)
    event_seq = models.BigIntegerField(blank=True, null=True)
    edit_comment = models.CharField(max_length=2000, blank=True, null=True)
    comment_num = models.IntegerField(blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)
    mission_edt_seq = models.BigIntegerField(blank=True, null=True)
    event_edt_seq = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCCOMMENTEDITS'


class Bcdiscretedtailedits(models.Model):
    dis_detail_edt_seq = models.BigIntegerField(primary_key=True)
    discrete_detail_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    data_type_seq = models.IntegerField(blank=True, null=True)
    discrete_seq = models.BigIntegerField(blank=True, null=True)
    data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    data_flag = models.CharField(max_length=3, blank=True, null=True)
    averaged_data = models.CharField(max_length=1, blank=True, null=True)
    data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    qc_flag = models.CharField(max_length=3, blank=True, null=True)
    detection_limit = models.DecimalField(max_digits=11, decimal_places=5, blank=True, null=True)
    detail_collector = models.CharField(max_length=50, blank=True, null=True)
    collector_sample_id = models.CharField(max_length=50, blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)
    dis_headr_edt_seq = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCDISCRETEDTAILEDITS'


class Bcdiscretehedredits(models.Model):
    dis_headr_edt_seq = models.BigIntegerField(primary_key=True)
    discrete_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    event_seq = models.BigIntegerField(blank=True, null=True)
    activity_seq = models.BigIntegerField(blank=True, null=True)
    gear_seq = models.IntegerField(blank=True, null=True)
    sdate = models.DateField(blank=True, null=True)
    edate = models.DateField(blank=True, null=True)
    stime = models.IntegerField(blank=True, null=True)
    etime = models.IntegerField(blank=True, null=True)
    time_qc_code = models.CharField(max_length=2, blank=True, null=True)
    slat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    elat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    slon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    elon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    position_qc_code = models.CharField(max_length=2, blank=True, null=True)
    start_depth = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    end_depth = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    sounding = models.IntegerField(blank=True, null=True)
    collector_deployment_id = models.CharField(max_length=50, blank=True, null=True)
    collector_sample_id = models.CharField(max_length=50, blank=True, null=True)
    collector = models.CharField(max_length=50, blank=True, null=True)
    collector_comment = models.CharField(max_length=2000, blank=True, null=True)
    data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)
    responsible_group = models.CharField(max_length=50, blank=True, null=True)
    shared_data = models.CharField(max_length=50, blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)
    activity_edt_seq = models.BigIntegerField(blank=True, null=True)
    event_edt_seq = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCDISCRETEHEDREDITS'


class Bcdisreplicatedits(models.Model):
    dis_repl_edt_seq = models.BigIntegerField(primary_key=True)
    discrete_replicate_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    discrete_detail_seq = models.BigIntegerField(blank=True, null=True)
    data_type_seq = models.IntegerField(blank=True, null=True)
    data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    detection_limit = models.DecimalField(max_digits=11, decimal_places=5, blank=True, null=True)
    detail_collector = models.CharField(max_length=50, blank=True, null=True)
    collector_sample_id = models.CharField(max_length=50, blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)
    dis_detail_edt_seq = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCDISREPLICATEDITS'


class Bceditsaudittrails(models.Model):
    audit_seq = models.BigIntegerField()
    data_center_code = models.IntegerField()
    audit_date = models.DateField()
    table_name = models.CharField(max_length=30)
    column_name = models.CharField(max_length=30)
    sequence_name = models.CharField(max_length=30)
    sequence_number = models.BigIntegerField()
    user_name = models.CharField(max_length=30)
    old_value = models.CharField(max_length=100, blank=True, null=True)
    new_value = models.CharField(max_length=100, blank=True, null=True)
    batch_seq = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCEDITSAUDITTRAILS'


class Bcplanktndtailedits(models.Model):
    pl_detail_edt_seq = models.BigIntegerField(primary_key=True)
    plankton_detail_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    data_type_seq = models.IntegerField(blank=True, null=True)
    plankton_general_seq = models.BigIntegerField(blank=True, null=True)
    data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    detail_collector = models.CharField(max_length=50, blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)
    pl_general_edt_seq = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCPLANKTNDTAILEDITS'


class Bcplanktnfreqedits(models.Model):
    pl_freq_edt_seq = models.BigIntegerField(primary_key=True)
    plankton_frequency_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    data_type_seq = models.IntegerField(blank=True, null=True)
    plankton_general_seq = models.BigIntegerField(blank=True, null=True)
    upper_bin_size = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)
    lower_bin_size = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)
    bug_count = models.IntegerField(blank=True, null=True)
    bug_seq = models.IntegerField(blank=True, null=True)
    data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    detail_collector = models.CharField(max_length=50, blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)
    pl_general_edt_seq = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCPLANKTNFREQEDITS'


class Bcplanktngenerledits(models.Model):
    pl_general_edt_seq = models.BigIntegerField(primary_key=True)
    plankton_general_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    plankton_seq = models.BigIntegerField(blank=True, null=True)
    national_taxonomic_seq = models.BigIntegerField(blank=True, null=True)
    collector_taxonomic_id = models.CharField(max_length=20, blank=True, null=True)
    life_history_seq = models.IntegerField(blank=True, null=True)
    trophic_seq = models.IntegerField(blank=True, null=True)
    min_sieve = models.DecimalField(max_digits=8, decimal_places=4, blank=True, null=True)
    max_sieve = models.DecimalField(max_digits=8, decimal_places=4, blank=True, null=True)
    split_fraction = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    sex_seq = models.IntegerField(blank=True, null=True)
    counts = models.DecimalField(max_digits=15, decimal_places=3, blank=True, null=True)
    count_pct = models.DecimalField(max_digits=15, decimal_places=5, blank=True, null=True)
    wet_weight = models.DecimalField(max_digits=9, decimal_places=4, blank=True, null=True)
    dry_weight = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    bio_volume = models.DecimalField(max_digits=8, decimal_places=3, blank=True, null=True)
    presence = models.CharField(max_length=1, blank=True, null=True)
    collector_comment = models.CharField(max_length=2000, blank=True, null=True)
    source = models.CharField(max_length=30, blank=True, null=True)
    data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)
    pl_headr_edt_seq = models.BigIntegerField(blank=True, null=True)
    modifier = models.CharField(max_length=50, blank=True, null=True, db_comment='additional taxonomic information')
    unit_seq = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCPLANKTNGENERLEDITS'


class Bcplanktnhedredits(models.Model):
    pl_headr_edt_seq = models.BigIntegerField(primary_key=True)
    plankton_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    event_seq = models.BigIntegerField(blank=True, null=True)
    activity_seq = models.BigIntegerField(blank=True, null=True)
    gear_seq = models.IntegerField(blank=True, null=True)
    sdate = models.DateField(blank=True, null=True)
    edate = models.DateField(blank=True, null=True)
    stime = models.IntegerField(blank=True, null=True)
    etime = models.IntegerField(blank=True, null=True)
    phase_of_daylight = models.CharField(max_length=15, blank=True, null=True)
    slat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    elat = models.DecimalField(max_digits=8, decimal_places=5, blank=True, null=True)
    slon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    elon = models.DecimalField(max_digits=9, decimal_places=5, blank=True, null=True)
    time_qc_code = models.CharField(max_length=2, blank=True, null=True)
    position_qc_code = models.CharField(max_length=2, blank=True, null=True)
    start_depth = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    end_depth = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    sounding = models.IntegerField(blank=True, null=True)
    volume = models.DecimalField(max_digits=7, decimal_places=3, blank=True, null=True)
    volume_method_seq = models.IntegerField(blank=True, null=True)
    large_plankton_removed = models.CharField(max_length=1, blank=True, null=True)
    mesh_size = models.IntegerField(blank=True, null=True)
    collection_method_seq = models.IntegerField(blank=True, null=True)
    collector_deployment_id = models.CharField(max_length=50, blank=True, null=True)
    collector_sample_id = models.CharField(max_length=50, blank=True, null=True)
    procedure_seq = models.IntegerField(blank=True, null=True)
    preservation_seq = models.IntegerField(blank=True, null=True)
    storage_seq = models.IntegerField(blank=True, null=True)
    collector = models.CharField(max_length=50, blank=True, null=True)
    collector_comment = models.CharField(max_length=2000, blank=True, null=True)
    meters_sqd_flag = models.CharField(max_length=1, blank=True, null=True)
    data_manager_comment = models.CharField(max_length=2000, blank=True, null=True)
    responsible_group = models.CharField(max_length=50, blank=True, null=True)
    shared_data = models.CharField(max_length=50, blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)
    event_edt_seq = models.BigIntegerField(blank=True, null=True)
    activity_edt_seq = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCPLANKTNHEDREDITS'


class Bcplanktnindivdledits(models.Model):
    pl_indiv_edt_seq = models.BigIntegerField(primary_key=True)
    plankton_individual_seq = models.BigIntegerField(blank=True, null=True)
    data_center_code = models.IntegerField(blank=True, null=True)
    data_type_seq = models.IntegerField(blank=True, null=True)
    plankton_general_seq = models.BigIntegerField(blank=True, null=True)
    bug_seq = models.IntegerField(blank=True, null=True)
    data_value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    data_qc_code = models.CharField(max_length=2, blank=True, null=True)
    data_collector = models.CharField(max_length=50, blank=True, null=True)
    prod_created_date = models.DateField(blank=True, null=True)
    created_by = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateField(blank=True, null=True)
    last_update_by = models.CharField(max_length=30, blank=True, null=True)
    last_update_date = models.DateField(blank=True, null=True)
    process_flag = models.CharField(max_length=3)
    batch_seq = models.IntegerField(blank=True, null=True)
    pl_general_edt_seq = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'BCPLANKTNINDIVDLEDITS'
