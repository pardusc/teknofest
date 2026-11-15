from django.db import migrations


def seed_initial_data(apps, schema_editor):
    Category = apps.get_model("main", "Category")
    Group = apps.get_model("auth", "Group")

    Category.objects.update_or_create(
        slug="bug",
        defaults={
            "name": "Bug / Suggestion",
            "description": "Bug reports and suggestions for Pardus applications.",
            "code_prefix": "BUG",
            "order": 1,
        },
    )
    Category.objects.update_or_create(
        slug="development",
        defaults={
            "name": "Development",
            "description": "New software or improvements developed for Pardus.",
            "code_prefix": "DEVELOPMENT",
            "order": 2,
        },
    )
    Group.objects.get_or_create(name="jury")


def remove_initial_data(apps, schema_editor):
    Category = apps.get_model("main", "Category")
    Category.objects.filter(
        slug__in=("bug", "development"),
        forms__isnull=True,
    ).delete()
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="jury").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_initial_data, remove_initial_data),
    ]
