# Generated by Django 3.2.15 on 2024-10-08 11:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("apm_web", "0023_auto_20240926_1222"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apmmetaconfig",
            name="level_key",
            field=models.CharField(max_length=528, verbose_name="配置目标key"),
        ),
    ]