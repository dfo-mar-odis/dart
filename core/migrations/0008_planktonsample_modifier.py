# Generated by Django 4.2 on 2024-07-18 12:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_remove_mission_biochem_table_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='planktonsample',
            name='modifier',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Plankton Modifier'),
        ),
    ]
