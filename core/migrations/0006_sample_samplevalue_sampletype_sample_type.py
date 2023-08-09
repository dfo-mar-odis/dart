# Generated by Django 4.2 on 2023-08-09 11:33

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bio_tables', '0001_initial'),
        ('core', '0005_alter_event_end_sample_id_alter_event_sample_id_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Sample',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.CharField(blank=True, max_length=50, null=True, verbose_name='File Name')),
                ('bottle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.bottle', verbose_name='Bottle')),
            ],
        ),
        migrations.CreateModel(
            name='SampleValue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('replicate', models.IntegerField(default=1, help_text='Replicates occur when there are multiple samples of the same type form the same bottle.', verbose_name='Replicate #')),
                ('value', models.FloatField(verbose_name='Value')),
                ('flag', models.IntegerField(blank=True, null=True, verbose_name='Data Quality Flag')),
                ('sample', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='values', to='core.sample', verbose_name='Sample')),
            ],
        ),
        migrations.CreateModel(
            name='SampleType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('short_name', models.CharField(help_text='The column name of a sensor or a short name commonly used for the sample', max_length=20, verbose_name='Short/Column Name')),
                ('name', models.CharField(blank=True, help_text='Short descriptive name for this type of sample/sensor', max_length=126, null=True, verbose_name='Name')),
                ('datatype', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sample_types', to='bio_tables.bcdatatype', verbose_name='BioChem DataType')),
            ],
        ),
        migrations.AddField(
            model_name='sample',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.sampletype', verbose_name='Type'),
        ),
    ]
