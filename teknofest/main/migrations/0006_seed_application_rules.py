from django.db import migrations

RULES = {
    "bug": {"code_prefix": "BUG", "attachment_policy": "required"},
    "development": {"code_prefix": "DEVELOPMENT", "attachment_policy": "none"},
}


def seed_application_rules(apps, schema_editor):
    Category = apps.get_model("main", "Category")
    for slug, defaults in RULES.items():
        Category.objects.filter(slug=slug).update(**defaults)


def unseed_application_rules(apps, schema_editor):
    Category = apps.get_model("main", "Category")
    Category.objects.filter(slug__in=RULES).update(
        code_prefix="",
        attachment_policy="optional",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0005_category_attachment_policy_category_code_prefix_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_application_rules, unseed_application_rules),
    ]
