from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='formfield',
            old_name='help_text',
            new_name='short_description',
        ),
        migrations.AlterField(
            model_name='formfield',
            name='short_description',
            field=models.CharField(
                blank=True,
                help_text='Shown under the question title.',
                max_length=255,
                verbose_name='Short description',
            ),
        ),
    ]
