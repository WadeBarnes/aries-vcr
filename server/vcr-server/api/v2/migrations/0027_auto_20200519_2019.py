# Generated by Django 2.2.12 on 2020-05-19 20:19

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api_v2', '0026_auto_20190923_0217'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='credential',
            index_together={('topic', 'latest', 'revoked')},
        ),
    ]
