# Generated by Django 4.2 on 2024-02-05 17:03

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Bcanalyses',
            fields=[
                ('analysis_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(blank=True, max_length=250, null=True)),
            ],
            options={
                'db_table': 'bcanalyses',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bccollectionmethods',
            fields=[
                ('collection_method_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(blank=True, max_length=1000, null=True)),
            ],
            options={
                'db_table': 'BCCOLLECTIONMETHODS',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcdatacenters',
            fields=[
                ('data_center_code', models.IntegerField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50)),
                ('location', models.CharField(max_length=50)),
                ('description', models.CharField(blank=True, max_length=100, null=True)),
                ('data_manager_only', models.CharField(blank=True, max_length=1, null=True)),
                ('dfo_only', models.CharField(blank=True, max_length=1, null=True)),
                ('region_only', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'db_table': 'Bcdatacenters',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcdataretrievals',
            fields=[
                ('data_retrieval_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('parameter_name', models.CharField(max_length=20)),
                ('parameter_description', models.CharField(max_length=100)),
                ('unit_seq', models.IntegerField()),
                ('places_before', models.IntegerField()),
                ('places_after', models.IntegerField()),
                ('minimum_value', models.DecimalField(blank=True, decimal_places=5, max_digits=12, null=True)),
                ('maximum_value', models.DecimalField(blank=True, decimal_places=5, max_digits=12, null=True)),
                ('originally_entered_by', models.CharField(max_length=30)),
            ],
            options={
                'db_table': 'bcdataretrievals',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcdatatypes',
            fields=[
                ('data_type_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('data_retrieval_seq', models.IntegerField()),
                ('analysis_seq', models.IntegerField()),
                ('preservation_seq', models.IntegerField()),
                ('sample_handling_seq', models.IntegerField()),
                ('storage_seq', models.IntegerField()),
                ('unit_seq', models.IntegerField()),
                ('description', models.CharField(max_length=250)),
                ('conversion_equation', models.CharField(blank=True, max_length=250, null=True)),
                ('originally_entered_by', models.CharField(max_length=30)),
                ('method', models.CharField(max_length=20)),
                ('priority', models.IntegerField()),
                ('p_code', models.CharField(blank=True, max_length=4, null=True)),
                ('bodc_code', models.CharField(blank=True, max_length=50, null=True)),
            ],
            options={
                'db_table': 'bcdatatypes',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='BcdDReportModel',
            fields=[
                ('dis_data_num', models.IntegerField(primary_key=True, serialize=False)),
                ('mission_descriptor', models.CharField(blank=True, max_length=50, null=True)),
                ('event_collector_event_id', models.CharField(blank=True, max_length=50, null=True)),
                ('event_collector_stn_name', models.CharField(blank=True, max_length=50, null=True)),
                ('dis_header_start_depth', models.DecimalField(blank=True, decimal_places=3, max_digits=9, null=True)),
                ('dis_header_end_depth', models.DecimalField(blank=True, decimal_places=3, max_digits=9, null=True)),
                ('dis_header_slat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('dis_header_slon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('dis_header_sdate', models.DateField(blank=True, null=True)),
                ('dis_header_stime', models.IntegerField(blank=True, null=True)),
                ('dis_detail_data_type_seq', models.IntegerField(blank=True, null=True)),
                ('data_type_method', models.CharField(blank=True, max_length=20, null=True)),
                ('dis_detail_data_value', models.DecimalField(blank=True, decimal_places=5, max_digits=10, null=True)),
                ('dis_detail_data_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('dis_detail_detection_limit', models.DecimalField(blank=True, decimal_places=5, max_digits=11, null=True)),
                ('dis_detail_detail_collector', models.CharField(blank=True, max_length=50, null=True)),
                ('dis_detail_collector_samp_id', models.CharField(blank=True, max_length=50, null=True)),
                ('created_by', models.CharField(max_length=30)),
                ('created_date', models.DateField()),
                ('data_center_code', models.IntegerField(blank=True, null=True)),
                ('process_flag', models.CharField(blank=True, max_length=3, null=True)),
                ('batch_seq', models.IntegerField(blank=True, null=True)),
                ('dis_sample_key_value', models.CharField(blank=True, max_length=50, null=True)),
            ],
            options={
                'ordering': ['dis_sample_key_value', 'dis_data_num'],
                'abstract': False,
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='BcdPReportModel',
            fields=[
                ('plank_data_num', models.AutoField(primary_key=True, serialize=False)),
                ('plank_sample_key_value', models.CharField(max_length=50)),
                ('mission_descriptor', models.CharField(blank=True, max_length=50, null=True)),
                ('event_collector_event_id', models.CharField(blank=True, max_length=50, null=True)),
                ('event_collector_stn_name', models.CharField(blank=True, max_length=50, null=True)),
                ('pl_gen_national_taxonomic_seq', models.BigIntegerField(blank=True, null=True)),
                ('pl_gen_collector_taxonomic_id', models.CharField(blank=True, max_length=20, null=True)),
                ('pl_gen_life_history_seq', models.IntegerField(blank=True, null=True)),
                ('pl_gen_trophic_seq', models.IntegerField(blank=True, null=True)),
                ('pl_gen_min_sieve', models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ('pl_gen_max_sieve', models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ('pl_gen_split_fraction', models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ('pl_gen_sex_seq', models.IntegerField(blank=True, null=True)),
                ('pl_gen_counts', models.DecimalField(blank=True, decimal_places=3, max_digits=9, null=True)),
                ('pl_gen_count_pct', models.DecimalField(blank=True, decimal_places=3, max_digits=6, null=True)),
                ('pl_gen_wet_weight', models.DecimalField(blank=True, decimal_places=4, max_digits=9, null=True)),
                ('pl_gen_dry_weight', models.DecimalField(blank=True, decimal_places=4, max_digits=9, null=True)),
                ('pl_gen_bio_volume', models.DecimalField(blank=True, decimal_places=3, max_digits=8, null=True)),
                ('pl_gen_presence', models.CharField(blank=True, max_length=1, null=True)),
                ('pl_gen_collector_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('pl_gen_data_manager_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('pl_gen_source', models.CharField(blank=True, max_length=30, null=True)),
                ('pl_freq_data_type_seq', models.IntegerField(blank=True, null=True)),
                ('pl_freq_upper_bin_size', models.DecimalField(blank=True, decimal_places=3, max_digits=6, null=True)),
                ('pl_freq_lower_bin_size', models.DecimalField(blank=True, decimal_places=3, max_digits=6, null=True)),
                ('pl_freq_bug_count', models.IntegerField(blank=True, null=True)),
                ('pl_freq_bug_seq', models.IntegerField(blank=True, null=True)),
                ('pl_freq_data_value', models.DecimalField(blank=True, decimal_places=5, max_digits=10, null=True)),
                ('pl_freq_data_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('pl_freq_detail_collector', models.CharField(blank=True, max_length=50, null=True)),
                ('pl_detail_data_type_seq', models.IntegerField(blank=True, null=True)),
                ('pl_detail_data_value', models.DecimalField(blank=True, decimal_places=5, max_digits=10, null=True)),
                ('pl_detail_data_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('pl_detail_detail_collector', models.CharField(blank=True, max_length=50, null=True)),
                ('pl_indiv_data_type_seq', models.IntegerField(blank=True, null=True)),
                ('pl_indiv_bug_seq', models.IntegerField(blank=True, null=True)),
                ('pl_indiv_data_value', models.DecimalField(blank=True, decimal_places=5, max_digits=10, null=True)),
                ('pl_indiv_data_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('pl_indiv_data_collector', models.CharField(blank=True, max_length=50, null=True)),
                ('created_by', models.CharField(max_length=30)),
                ('created_date', models.DateField()),
                ('data_center_code', models.IntegerField(blank=True, null=True)),
                ('process_flag', models.CharField(blank=True, max_length=3, null=True)),
                ('batch_seq', models.IntegerField(blank=True, null=True)),
                ('pl_gen_modifier', models.CharField(blank=True, max_length=50, null=True)),
                ('pl_gen_unit', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'abstract': False,
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcgears',
            fields=[
                ('gear_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('type', models.CharField(max_length=40)),
                ('model', models.CharField(blank=True, max_length=50, null=True)),
                ('gear_size', models.CharField(blank=True, max_length=20, null=True)),
                ('description', models.CharField(blank=True, max_length=2000, null=True)),
            ],
            options={
                'db_table': 'bcgears',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bclifehistories',
            fields=[
                ('life_history_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(blank=True, max_length=1000, null=True)),
                ('molt_number', models.CharField(blank=True, max_length=20, null=True)),
            ],
            options={
                'db_table': 'BCLIFEHISTORIES',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcnatnltaxoncodes',
            fields=[
                ('national_taxonomic_seq', models.BigIntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('tsn', models.BigIntegerField()),
                ('taxonomic_name', models.CharField(max_length=100)),
                ('best_nodc7', models.BigIntegerField()),
                ('authority', models.CharField(blank=True, max_length=50, null=True)),
                ('collectors_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('data_managers_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('short_name', models.CharField(blank=True, max_length=15, null=True)),
                ('tsn_itis', models.BigIntegerField(blank=True, null=True)),
                ('aphiaid', models.BigIntegerField(blank=True, null=True)),
            ],
            options={
                'db_table': 'BCNATNLTAXONCODES',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcpreservations',
            fields=[
                ('preservation_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(blank=True, max_length=250, null=True)),
                ('type', models.CharField(blank=True, max_length=30, null=True)),
            ],
            options={
                'db_table': 'bcpreservations',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcprocedures',
            fields=[
                ('procedure_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(blank=True, max_length=1000, null=True)),
            ],
            options={
                'db_table': 'BCPROCEDURES',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcsamplehandlings',
            fields=[
                ('sample_handling_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(blank=True, max_length=250, null=True)),
            ],
            options={
                'db_table': 'bcsamplehandlings',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='BcsDReportModel',
            fields=[
                ('dis_headr_collector_sample_id', models.CharField(max_length=50, primary_key=True, serialize=False)),
                ('dis_sample_key_value', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_descriptor', models.CharField(blank=True, max_length=50, null=True)),
                ('event_collector_event_id', models.CharField(blank=True, max_length=50, null=True)),
                ('event_collector_stn_name', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_name', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_leader', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_sdate', models.DateField(blank=True, null=True)),
                ('mission_edate', models.DateField(blank=True, null=True)),
                ('mission_institute', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_platform', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_protocol', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_geographic_region', models.CharField(blank=True, max_length=100, null=True)),
                ('mission_collector_comment1', models.CharField(blank=True, max_length=2000, null=True)),
                ('mission_collector_comment2', models.CharField(blank=True, max_length=2000, null=True)),
                ('mission_data_manager_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('event_sdate', models.DateField(blank=True, null=True)),
                ('event_edate', models.DateField(blank=True, null=True)),
                ('event_stime', models.IntegerField(blank=True, null=True)),
                ('event_etime', models.IntegerField(blank=True, null=True)),
                ('event_min_lat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('event_max_lat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('event_min_lon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('event_max_lon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('event_utc_offset', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('event_collector_comment1', models.CharField(blank=True, max_length=2000, null=True)),
                ('event_collector_comment2', models.CharField(blank=True, max_length=2000, null=True)),
                ('event_data_manager_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('dis_headr_gear_seq', models.IntegerField(blank=True, null=True)),
                ('dis_headr_sdate', models.DateField(blank=True, null=True)),
                ('dis_headr_edate', models.DateField(blank=True, null=True)),
                ('dis_headr_stime', models.IntegerField(blank=True, null=True)),
                ('dis_headr_etime', models.IntegerField(blank=True, null=True)),
                ('dis_headr_time_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('dis_headr_slat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('dis_headr_elat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('dis_headr_slon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('dis_headr_elon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('dis_headr_position_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('dis_headr_start_depth', models.DecimalField(blank=True, decimal_places=3, max_digits=9, null=True)),
                ('dis_headr_end_depth', models.DecimalField(blank=True, decimal_places=3, max_digits=9, null=True)),
                ('dis_headr_sounding', models.IntegerField(blank=True, null=True)),
                ('dis_headr_collector', models.CharField(blank=True, max_length=50, null=True)),
                ('dis_headr_collector_comment1', models.CharField(blank=True, max_length=2000, null=True)),
                ('dis_headr_data_manager_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('dis_headr_responsible_group', models.CharField(blank=True, max_length=50, null=True)),
                ('created_by', models.CharField(max_length=30)),
                ('created_date', models.DateField()),
                ('data_center_code', models.IntegerField(blank=True, null=True)),
                ('process_flag', models.CharField(blank=True, max_length=3, null=True)),
                ('batch_seq', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcsexes',
            fields=[
                ('sex_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(blank=True, max_length=1000, null=True)),
            ],
            options={
                'db_table': 'BCSEXES',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='BcsPReportModel',
            fields=[
                ('plank_sample_key_value', models.CharField(max_length=50, primary_key=True, serialize=False)),
                ('mission_name', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_descriptor', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_leader', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_sdate', models.DateField(blank=True, null=True)),
                ('mission_edate', models.DateField(blank=True, null=True)),
                ('mission_institute', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_platform', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_protocol', models.CharField(blank=True, max_length=50, null=True)),
                ('mission_geographic_region', models.CharField(blank=True, max_length=100, null=True)),
                ('mission_collector_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('mission_more_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('mission_data_manager_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('event_sdate', models.DateField(blank=True, null=True)),
                ('event_edate', models.DateField(blank=True, null=True)),
                ('event_stime', models.IntegerField(blank=True, null=True)),
                ('event_etime', models.IntegerField(blank=True, null=True)),
                ('event_min_lat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('event_max_lat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('event_min_lon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('event_max_lon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('event_collector_stn_name', models.CharField(blank=True, max_length=50, null=True)),
                ('event_collector_event_id', models.CharField(blank=True, max_length=50, null=True)),
                ('event_utc_offset', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('event_collector_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('event_more_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('event_data_manager_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('pl_headr_gear_seq', models.IntegerField(blank=True, null=True)),
                ('pl_headr_sdate', models.DateField(blank=True, null=True)),
                ('pl_headr_edate', models.DateField(blank=True, null=True)),
                ('pl_headr_stime', models.IntegerField(blank=True, null=True)),
                ('pl_headr_etime', models.IntegerField(blank=True, null=True)),
                ('pl_headr_phase_of_daylight', models.CharField(blank=True, max_length=15, null=True)),
                ('pl_headr_slat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('pl_headr_elat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('pl_headr_slon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('pl_headr_elon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('pl_headr_time_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('pl_headr_position_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('pl_headr_start_depth', models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ('pl_headr_end_depth', models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ('pl_headr_sounding', models.IntegerField(blank=True, null=True)),
                ('pl_headr_volume', models.DecimalField(blank=True, decimal_places=3, max_digits=7, null=True)),
                ('pl_headr_volume_method_seq', models.IntegerField(blank=True, null=True)),
                ('pl_headr_lrg_plankton_removed', models.CharField(blank=True, max_length=1, null=True)),
                ('pl_headr_mesh_size', models.IntegerField(blank=True, null=True)),
                ('pl_headr_collection_method_seq', models.IntegerField(blank=True, null=True)),
                ('pl_headr_collector_deplmt_id', models.CharField(blank=True, max_length=50, null=True)),
                ('pl_headr_collector_sample_id', models.CharField(blank=True, max_length=50, null=True)),
                ('pl_headr_procedure_seq', models.IntegerField(blank=True, null=True)),
                ('pl_headr_preservation_seq', models.IntegerField(blank=True, null=True)),
                ('pl_headr_storage_seq', models.IntegerField(blank=True, null=True)),
                ('pl_headr_collector', models.CharField(blank=True, max_length=50, null=True)),
                ('pl_headr_collector_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('pl_headr_meters_sqd_flag', models.CharField(blank=True, max_length=1, null=True)),
                ('pl_headr_data_manager_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('pl_headr_responsible_group', models.CharField(blank=True, max_length=50, null=True)),
                ('pl_headr_shared_data', models.CharField(blank=True, max_length=50, null=True)),
                ('created_by', models.CharField(max_length=30)),
                ('created_date', models.DateField()),
                ('data_center_code', models.IntegerField(blank=True, null=True)),
                ('process_flag', models.CharField(blank=True, max_length=3, null=True)),
                ('batch_seq', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcstorages',
            fields=[
                ('storage_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(blank=True, max_length=250, null=True)),
            ],
            options={
                'db_table': 'bcstorages',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcunits',
            fields=[
                ('unit_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('name', models.CharField(max_length=20)),
                ('description', models.CharField(blank=True, max_length=100, null=True)),
            ],
            options={
                'db_table': 'bcunits',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcvolumemethods',
            fields=[
                ('volume_method_seq', models.IntegerField(primary_key=True, serialize=False)),
                ('data_center_code', models.IntegerField()),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(blank=True, max_length=1000, null=True)),
            ],
            options={
                'db_table': 'BCVOLUMEMETHODS',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='TestAzmpUploadBCD',
            fields=[
                ('dis_data_num', models.AutoField(primary_key=True, serialize=False)),
                ('mission_descriptor', models.CharField(blank=True, max_length=50, null=True)),
                ('event_collector_event_id', models.CharField(blank=True, max_length=50, null=True)),
                ('event_collector_stn_name', models.CharField(blank=True, max_length=50, null=True)),
                ('dis_header_start_depth', models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ('dis_header_end_depth', models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ('dis_header_slat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('dis_header_slon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('dis_header_sdate', models.DateField(blank=True, null=True)),
                ('dis_header_stime', models.IntegerField(blank=True, null=True)),
                ('dis_detail_data_type_seq', models.IntegerField(blank=True, null=True)),
                ('data_type_method', models.CharField(blank=True, max_length=20, null=True)),
                ('dis_detail_data_value', models.DecimalField(blank=True, decimal_places=5, max_digits=10, null=True)),
                ('dis_detail_data_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('dis_detail_detection_limit', models.DecimalField(blank=True, decimal_places=5, max_digits=11, null=True)),
                ('dis_detail_detail_collector', models.CharField(blank=True, max_length=50, null=True)),
                ('dis_detail_collector_samp_id', models.CharField(blank=True, max_length=50, null=True)),
                ('created_by', models.CharField(max_length=30)),
                ('created_date', models.DateField()),
                ('data_center_code', models.IntegerField(blank=True, null=True)),
                ('process_flag', models.CharField(blank=True, max_length=3, null=True)),
                ('batch_seq', models.IntegerField(blank=True, null=True)),
                ('dis_sample_key_value', models.CharField(blank=True, max_length=50, null=True)),
            ],
            options={
                'managed': False,
            },
        ),
    ]
