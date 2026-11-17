from django.db import migrations


def set_bug_attachment_profile(apps, schema_editor):
    FormDefinition = apps.get_model("main", "FormDefinition")
    FormDefinition.objects.filter(category__slug="bug").update(
        attachment_profile="webp_webm"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0005_formdefinition_attachment_profile"),
    ]

    operations = [
        migrations.RunPython(
            set_bug_attachment_profile,
            migrations.RunPython.noop,
        ),
    ]
