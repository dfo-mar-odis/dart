# Generated by Django 4.2 on 2023-08-09 11:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_sampletype_priority_sampletype_units'),
    ]

    operations = [
        migrations.AddField(
            model_name='sampletype',
            name='comments',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Comments'),
        ),
    ]
