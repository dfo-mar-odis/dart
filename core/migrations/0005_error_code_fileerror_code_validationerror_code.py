# Generated by Django 4.2 on 2024-06-07 14:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_mission_dart_version'),
    ]

    operations = [
        migrations.AddField(
            model_name='error',
            name='code',
            field=models.IntegerField(default=-1, verbose_name='Error code'),
        ),
        migrations.AddField(
            model_name='fileerror',
            name='code',
            field=models.IntegerField(default=-1, verbose_name='Error code'),
        ),
        migrations.AddField(
            model_name='validationerror',
            name='code',
            field=models.IntegerField(default=-1, verbose_name='Error code'),
        ),
    ]
