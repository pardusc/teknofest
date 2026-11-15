from django.db import migrations, models


def copy_policy_to_forms(apps, schema_editor):
    FormDefinition = apps.get_model("main", "FormDefinition")
    for form in FormDefinition.objects.select_related("category"):
        form.attachment_policy = form.category.attachment_policy
        form.save(update_fields=["attachment_policy"])


def delete_draft_applications(apps, schema_editor):
    Application = apps.get_model("main", "Application")
    for application in Application.objects.filter(status="draft"):
        for attachment in application.attachments.all():
            if attachment.file:
                attachment.file.storage.delete(attachment.file.name)
        application.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0010_remove_formfield_is_visible_in_review_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="formdefinition",
            name="attachment_policy",
            field=models.CharField(
                choices=[
                    ("none", "No attachments"),
                    ("optional", "Optional"),
                    ("required", "Required"),
                ],
                default="optional",
                max_length=16,
            ),
        ),
        migrations.RunPython(copy_policy_to_forms, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="category",
            name="attachment_policy",
        ),
        migrations.RunPython(delete_draft_applications, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="application",
            name="status",
            field=models.CharField(
                choices=[
                    ("submitted", "Submitted"),
                    ("in_review", "In review"),
                    ("evaluated", "Evaluated"),
                ],
                default="submitted",
                max_length=16,
            ),
        ),
    ]
