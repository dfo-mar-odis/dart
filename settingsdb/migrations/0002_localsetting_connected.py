# Generated by Django 4.2 on 2024-01-29 20:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settingsdb', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='localsetting',
            name='connected',
            field=models.BooleanField(default=False, verbose_name='Connected'),
        ),
    ]
