from django.db import migrations

CATEGORIES = (
    (
        "bug",
        "Bug / Suggestion",
        "Bug reports and suggestions for Pardus applications.",
        1,
    ),
    (
        "development",
        "Development",
        "New software or improvements developed for Pardus.",
        2,
    ),
)


def seed_categories(apps, schema_editor):
    Category = apps.get_model("main", "Category")
    for slug, name, description, order in CATEGORIES:
        Category.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "description": description, "order": order},
        )


def unseed_categories(apps, schema_editor):
    Category = apps.get_model("main", "Category")
    Category.objects.filter(
        slug__in=[slug for slug, *_rest in CATEGORIES],
        forms__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0003_category_competitionyear_formdefinition_formfield_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
