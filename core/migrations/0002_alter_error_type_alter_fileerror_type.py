# Generated by Django 4.2 on 2023-08-02 13:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='error',
            name='type',
            field=models.IntegerField(choices=[(0, 'Unknown'), (1, 'Missing ID'), (2, 'Missing Value')], default=0, verbose_name='Error type'),
        ),
        migrations.AlterField(
            model_name='fileerror',
            name='type',
            field=models.IntegerField(choices=[(0, 'Unknown'), (1, 'Missing ID'), (2, 'Missing Value')], default=0, verbose_name='Error type'),
        ),
    ]
