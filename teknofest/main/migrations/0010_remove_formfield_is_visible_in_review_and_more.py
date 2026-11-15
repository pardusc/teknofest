from django.db import migrations, models


def copy_review_visibility(apps, schema_editor):
    FormField = apps.get_model("main", "FormField")
    FormField.objects.filter(is_visible_in_review=False).update(
        review_visibility="hidden"
    )


def restore_is_visible_in_review(apps, schema_editor):
    FormField = apps.get_model("main", "FormField")
    FormField.objects.filter(review_visibility="hidden").update(
        is_visible_in_review=False
    )


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0009_create_jury_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="formdefinition",
            name="mask_applicant_identity",
            field=models.BooleanField(
                default=False,
                help_text="Hide the applicant's name and e-mail from the jury.",
            ),
        ),
        migrations.AddField(
            model_name="formfield",
            name="review_visibility",
            field=models.CharField(
                choices=[
                    ("visible", "Visible"),
                    ("masked", "Masked"),
                    ("hidden", "Hidden"),
                ],
                default="visible",
                help_text="What the jury can see for this field.",
                max_length=8,
            ),
        ),
        migrations.RunPython(copy_review_visibility, restore_is_visible_in_review),
        migrations.RemoveField(
            model_name="formfield",
            name="is_visible_in_review",
        ),
    ]
