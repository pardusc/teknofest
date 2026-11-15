from django.db import migrations

JURY_GROUP_NAME = "jury"


def create_jury_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=JURY_GROUP_NAME)


def remove_jury_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=JURY_GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("main", "0008_review"),
    ]

    operations = [
        migrations.RunPython(create_jury_group, remove_jury_group),
    ]
