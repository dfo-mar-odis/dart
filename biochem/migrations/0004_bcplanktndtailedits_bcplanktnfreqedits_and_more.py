# Generated by Django 4.2 on 2024-08-26 13:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('biochem', '0003_bccommentedits_bcdiscretedtailedits_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Bcplanktndtailedits',
            fields=[
                ('pl_detail_edt_seq', models.BigIntegerField(primary_key=True, serialize=False)),
                ('plankton_detail_seq', models.BigIntegerField(blank=True, null=True)),
                ('data_center_code', models.IntegerField(blank=True, null=True)),
                ('data_type_seq', models.IntegerField(blank=True, null=True)),
                ('plankton_general_seq', models.BigIntegerField(blank=True, null=True)),
                ('data_value', models.DecimalField(blank=True, decimal_places=5, max_digits=10, null=True)),
                ('data_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('detail_collector', models.CharField(blank=True, max_length=50, null=True)),
                ('prod_created_date', models.DateField(blank=True, null=True)),
                ('created_by', models.CharField(blank=True, max_length=30, null=True)),
                ('created_date', models.DateField(blank=True, null=True)),
                ('last_update_by', models.CharField(blank=True, max_length=30, null=True)),
                ('last_update_date', models.DateField(blank=True, null=True)),
                ('process_flag', models.CharField(max_length=3)),
                ('batch_seq', models.IntegerField(blank=True, null=True)),
                ('pl_general_edt_seq', models.BigIntegerField(blank=True, null=True)),
            ],
            options={
                'db_table': 'BCPLANKTNDTAILEDITS',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcplanktnfreqedits',
            fields=[
                ('pl_freq_edt_seq', models.BigIntegerField(primary_key=True, serialize=False)),
                ('plankton_frequency_seq', models.BigIntegerField(blank=True, null=True)),
                ('data_center_code', models.IntegerField(blank=True, null=True)),
                ('data_type_seq', models.IntegerField(blank=True, null=True)),
                ('plankton_general_seq', models.BigIntegerField(blank=True, null=True)),
                ('upper_bin_size', models.DecimalField(blank=True, decimal_places=3, max_digits=6, null=True)),
                ('lower_bin_size', models.DecimalField(blank=True, decimal_places=3, max_digits=6, null=True)),
                ('bug_count', models.IntegerField(blank=True, null=True)),
                ('bug_seq', models.IntegerField(blank=True, null=True)),
                ('data_value', models.DecimalField(blank=True, decimal_places=5, max_digits=10, null=True)),
                ('data_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('detail_collector', models.CharField(blank=True, max_length=50, null=True)),
                ('prod_created_date', models.DateField(blank=True, null=True)),
                ('created_by', models.CharField(blank=True, max_length=30, null=True)),
                ('created_date', models.DateField(blank=True, null=True)),
                ('last_update_by', models.CharField(blank=True, max_length=30, null=True)),
                ('last_update_date', models.DateField(blank=True, null=True)),
                ('process_flag', models.CharField(max_length=3)),
                ('batch_seq', models.IntegerField(blank=True, null=True)),
                ('pl_general_edt_seq', models.BigIntegerField(blank=True, null=True)),
            ],
            options={
                'db_table': 'BCPLANKTNFREQEDITS',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcplanktngenerledits',
            fields=[
                ('pl_general_edt_seq', models.BigIntegerField(primary_key=True, serialize=False)),
                ('plankton_general_seq', models.BigIntegerField(blank=True, null=True)),
                ('data_center_code', models.IntegerField(blank=True, null=True)),
                ('plankton_seq', models.BigIntegerField(blank=True, null=True)),
                ('national_taxonomic_seq', models.BigIntegerField(blank=True, null=True)),
                ('collector_taxonomic_id', models.CharField(blank=True, max_length=20, null=True)),
                ('life_history_seq', models.IntegerField(blank=True, null=True)),
                ('trophic_seq', models.IntegerField(blank=True, null=True)),
                ('min_sieve', models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ('max_sieve', models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ('split_fraction', models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ('sex_seq', models.IntegerField(blank=True, null=True)),
                ('counts', models.DecimalField(blank=True, decimal_places=3, max_digits=15, null=True)),
                ('count_pct', models.DecimalField(blank=True, decimal_places=5, max_digits=15, null=True)),
                ('wet_weight', models.DecimalField(blank=True, decimal_places=4, max_digits=9, null=True)),
                ('dry_weight', models.DecimalField(blank=True, decimal_places=5, max_digits=10, null=True)),
                ('bio_volume', models.DecimalField(blank=True, decimal_places=3, max_digits=8, null=True)),
                ('presence', models.CharField(blank=True, max_length=1, null=True)),
                ('collector_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('source', models.CharField(blank=True, max_length=30, null=True)),
                ('data_manager_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('prod_created_date', models.DateField(blank=True, null=True)),
                ('created_by', models.CharField(blank=True, max_length=30, null=True)),
                ('created_date', models.DateField(blank=True, null=True)),
                ('last_update_by', models.CharField(blank=True, max_length=30, null=True)),
                ('last_update_date', models.DateField(blank=True, null=True)),
                ('process_flag', models.CharField(max_length=3)),
                ('batch_seq', models.IntegerField(blank=True, null=True)),
                ('pl_headr_edt_seq', models.BigIntegerField(blank=True, null=True)),
                ('modifier', models.CharField(blank=True, db_comment='additional taxonomic information', max_length=50, null=True)),
                ('unit_seq', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'db_table': 'BCPLANKTNGENERLEDITS',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcplanktnhedredits',
            fields=[
                ('pl_headr_edt_seq', models.BigIntegerField(primary_key=True, serialize=False)),
                ('plankton_seq', models.BigIntegerField(blank=True, null=True)),
                ('data_center_code', models.IntegerField(blank=True, null=True)),
                ('event_seq', models.BigIntegerField(blank=True, null=True)),
                ('activity_seq', models.BigIntegerField(blank=True, null=True)),
                ('gear_seq', models.IntegerField(blank=True, null=True)),
                ('sdate', models.DateField(blank=True, null=True)),
                ('edate', models.DateField(blank=True, null=True)),
                ('stime', models.IntegerField(blank=True, null=True)),
                ('etime', models.IntegerField(blank=True, null=True)),
                ('phase_of_daylight', models.CharField(blank=True, max_length=15, null=True)),
                ('slat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('elat', models.DecimalField(blank=True, decimal_places=5, max_digits=8, null=True)),
                ('slon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('elon', models.DecimalField(blank=True, decimal_places=5, max_digits=9, null=True)),
                ('time_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('position_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('start_depth', models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ('end_depth', models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ('sounding', models.IntegerField(blank=True, null=True)),
                ('volume', models.DecimalField(blank=True, decimal_places=3, max_digits=7, null=True)),
                ('volume_method_seq', models.IntegerField(blank=True, null=True)),
                ('large_plankton_removed', models.CharField(blank=True, max_length=1, null=True)),
                ('mesh_size', models.IntegerField(blank=True, null=True)),
                ('collection_method_seq', models.IntegerField(blank=True, null=True)),
                ('collector_deployment_id', models.CharField(blank=True, max_length=50, null=True)),
                ('collector_sample_id', models.CharField(blank=True, max_length=50, null=True)),
                ('procedure_seq', models.IntegerField(blank=True, null=True)),
                ('preservation_seq', models.IntegerField(blank=True, null=True)),
                ('storage_seq', models.IntegerField(blank=True, null=True)),
                ('collector', models.CharField(blank=True, max_length=50, null=True)),
                ('collector_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('meters_sqd_flag', models.CharField(blank=True, max_length=1, null=True)),
                ('data_manager_comment', models.CharField(blank=True, max_length=2000, null=True)),
                ('responsible_group', models.CharField(blank=True, max_length=50, null=True)),
                ('shared_data', models.CharField(blank=True, max_length=50, null=True)),
                ('prod_created_date', models.DateField(blank=True, null=True)),
                ('created_by', models.CharField(blank=True, max_length=30, null=True)),
                ('created_date', models.DateField(blank=True, null=True)),
                ('last_update_by', models.CharField(blank=True, max_length=30, null=True)),
                ('last_update_date', models.DateField(blank=True, null=True)),
                ('process_flag', models.CharField(max_length=3)),
                ('batch_seq', models.IntegerField(blank=True, null=True)),
                ('event_edt_seq', models.BigIntegerField(blank=True, null=True)),
                ('activity_edt_seq', models.BigIntegerField(blank=True, null=True)),
            ],
            options={
                'db_table': 'BCPLANKTNHEDREDITS',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Bcplanktnindivdledits',
            fields=[
                ('pl_indiv_edt_seq', models.BigIntegerField(primary_key=True, serialize=False)),
                ('plankton_individual_seq', models.BigIntegerField(blank=True, null=True)),
                ('data_center_code', models.IntegerField(blank=True, null=True)),
                ('data_type_seq', models.IntegerField(blank=True, null=True)),
                ('plankton_general_seq', models.BigIntegerField(blank=True, null=True)),
                ('bug_seq', models.IntegerField(blank=True, null=True)),
                ('data_value', models.DecimalField(blank=True, decimal_places=5, max_digits=10, null=True)),
                ('data_qc_code', models.CharField(blank=True, max_length=2, null=True)),
                ('data_collector', models.CharField(blank=True, max_length=50, null=True)),
                ('prod_created_date', models.DateField(blank=True, null=True)),
                ('created_by', models.CharField(blank=True, max_length=30, null=True)),
                ('created_date', models.DateField(blank=True, null=True)),
                ('last_update_by', models.CharField(blank=True, max_length=30, null=True)),
                ('last_update_date', models.DateField(blank=True, null=True)),
                ('process_flag', models.CharField(max_length=3)),
                ('batch_seq', models.IntegerField(blank=True, null=True)),
                ('pl_general_edt_seq', models.BigIntegerField(blank=True, null=True)),
            ],
            options={
                'db_table': 'BCPLANKTNINDIVDLEDITS',
                'managed': False,
            },
        ),
    ]
