from django.db import migrations, models

from main.validators import validate_application_title

TITLE_KEY = "title"
TITLE_LABEL = "Başvuru başlığı"
TITLE_DESCRIPTION = "Başvurunuzu tanımlayan kısa ve açık bir başlık girin."
TITLE_PLACEHOLDER = "Örn. Giriş ekranında hata"


def ensure_title_fields(apps, schema_editor):
    """Make sure every form definition has a strict, required title field."""
    FormDefinition = apps.get_model("main", "FormDefinition")
    FormField = apps.get_model("main", "FormField")

    for form in FormDefinition.objects.all().iterator():
        fields = list(FormField.objects.filter(form=form))
        title_field = next(
            (field for field in fields if field.key == TITLE_KEY),
            None,
        )

        if title_field is None:
            for field in fields:
                FormField.objects.filter(pk=field.pk).update(order=field.order + 1)
            FormField.objects.create(
                form=form,
                key=TITLE_KEY,
                label=TITLE_LABEL,
                field_type="short_text",
                short_description=TITLE_DESCRIPTION,
                placeholder=TITLE_PLACEHOLDER,
                is_required=True,
                min_length=3,
                max_length=100,
                order=0,
                is_active=True,
                review_visibility="visible",
            )
            continue

        if title_field.order != 0:
            for field in fields:
                if field.pk != title_field.pk:
                    FormField.objects.filter(pk=field.pk).update(
                        order=field.order + 1
                    )
            title_field.order = 0

        title_field.is_active = True
        title_field.is_required = True
        title_field.field_type = "short_text"
        title_field.review_visibility = "visible"
        if not title_field.max_length or title_field.max_length > 100:
            title_field.max_length = 100
        if not title_field.min_length or title_field.min_length < 3:
            title_field.min_length = 3
        if not title_field.short_description:
            title_field.short_description = TITLE_DESCRIPTION
        if not title_field.placeholder:
            title_field.placeholder = TITLE_PLACEHOLDER
        title_field.save(
            update_fields=[
                "order",
                "is_active",
                "is_required",
                "field_type",
                "review_visibility",
                "max_length",
                "min_length",
                "short_description",
                "placeholder",
            ]
        )


def backfill_application_titles(apps, schema_editor):
    Application = apps.get_model("main", "Application")
    ApplicationAnswer = apps.get_model("main", "ApplicationAnswer")

    for application in Application.objects.select_related("form").iterator():
        value = (
            ApplicationAnswer.objects.filter(
                application=application,
                field__key=TITLE_KEY,
            )
            .values_list("value", flat=True)
            .first()
        )
        title = value.strip() if isinstance(value, str) else ""
        if not title:
            title = (application.form.title or "").strip()
        if not title:
            title = application.code or "Application"
        Application.objects.filter(pk=application.pk).update(title=title[:100])


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0003_add_formfield_placeholder"),
    ]

    operations = [
        migrations.AddField(
            model_name="application",
            name="title",
            field=models.CharField(
                default="",
                help_text="The title entered by the applicant.",
                max_length=100,
                validators=[validate_application_title],
                verbose_name="Application title",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(ensure_title_fields, migrations.RunPython.noop),
        migrations.RunPython(backfill_application_titles, migrations.RunPython.noop),
    ]
