import os
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .dynamic_forms import build_form
from .models import (
    Application,
    ApplicationAnswer,
    Attachment,
    Category,
    CompetitionYear,
    FormDefinition,
    FormField,
    Profile,
    Review,
)
from .services.applications import (
    add_attachment,
    delete_application,
    delete_attachment,
    submit_application,
    update_application,
)
from .services.reviews import save_review, submit_review
from .views import (
    MASKED_FIELD_MESSAGE,
    ApplicationDetailView,
    ApplicationListView,
    ApplicationPreviewView,
    ApplicationUpdateView,
    FormDetailView,
    FormListView,
)


def make_image(name="photo.png", image_format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format=image_format)
    content_type = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }[image_format]
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


class HomeViewTests(TestCase):
    def test_home_page_renders(self):
        response = self.client.get(reverse("main:home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "main/home.html")

    def test_home_page_shows_login_link_to_anonymous_users(self):
        response = self.client.get(reverse("main:home"))

        self.assertContains(response, reverse("login"))


class UserModelTests(TestCase):
    def test_email_is_unique(self):
        User = get_user_model()
        User.objects.create_user(username="first", email="same@example.com")

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="second", email="same@example.com")

    def test_keycloak_id_is_unique(self):
        User = get_user_model()
        User.objects.create_user(
            username="first", email="first@example.com", keycloak_id="sub-1"
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(
                username="second", email="second@example.com", keycloak_id="sub-1"
            )

    def test_local_users_may_have_no_keycloak_id(self):
        User = get_user_model()
        User.objects.create_user(username="admin1", email="admin1@example.com")
        User.objects.create_user(username="admin2", email="admin2@example.com")

        self.assertEqual(User.objects.filter(keycloak_id__isnull=True).count(), 2)

    def test_username_field_remains_login_identifier(self):
        self.assertEqual(get_user_model().USERNAME_FIELD, "username")


class MediaTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()


class ProfileTests(MediaTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="applicant",
            email="applicant@example.com",
            password="secret123",
        )
        self.client.force_login(self.user)

    def valid_data(self, **overrides):
        data = {
            "phone": "+90 555 111 22 33",
            "city": "Ankara",
            "institution": "Pardus University",
            "education_level": Profile.EducationLevel.BACHELOR,
        }
        data.update(overrides)
        return data

    def test_profile_page_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("main:profile"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('main:profile')}",
        )

    def test_profile_page_creates_and_displays_profile(self):
        response = self.client.get(reverse("main:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Profile.objects.filter(user=self.user).exists())
        self.assertContains(response, self.user.email)

    def test_profile_update_saves_required_fields(self):
        response = self.client.post(reverse("main:profile_edit"), self.valid_data())

        self.assertRedirects(response, reverse("main:profile"))
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.city, "Ankara")
        self.assertEqual(profile.education_level, Profile.EducationLevel.BACHELOR)
        self.assertTrue(profile.is_complete)

    def test_photo_is_optional(self):
        response = self.client.post(reverse("main:profile_edit"), self.valid_data())

        self.assertRedirects(response, reverse("main:profile"))
        self.assertFalse(Profile.objects.get(user=self.user).photo)

    def test_valid_photo_is_uploaded(self):
        data = self.valid_data()
        data["photo"] = make_image()

        response = self.client.post(reverse("main:profile_edit"), data)

        self.assertRedirects(response, reverse("main:profile"))
        self.assertTrue(Profile.objects.get(user=self.user).photo.name.startswith("profiles/"))

    def test_invalid_photo_type_is_rejected(self):
        data = self.valid_data()
        data["photo"] = make_image(name="photo.gif", image_format="GIF")

        response = self.client.post(reverse("main:profile_edit"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "photo", "Upload a JPG or PNG image."
        )

    @patch("main.forms.MAX_PHOTO_SIZE", 10)
    def test_oversized_photo_is_rejected(self):
        data = self.valid_data()
        data["photo"] = make_image()

        response = self.client.post(reverse("main:profile_edit"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "photo", "The photo must be 1 MB or smaller."
        )

    def test_missing_required_field_is_rejected(self):
        data = self.valid_data()
        del data["city"]

        response = self.client.post(reverse("main:profile_edit"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "city", "This field is required.")

    def test_invalid_phone_is_rejected(self):
        response = self.client.post(
            reverse("main:profile_edit"),
            self.valid_data(phone="not-a-phone"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "phone", "Enter a valid phone number."
        )

    def test_incomplete_profile_is_not_complete(self):
        profile = Profile.objects.create(user=self.user, phone="+90 555 111 22 33")

        self.assertFalse(profile.is_complete)

    def test_login_flow(self):
        self.client.logout()

        response = self.client.post(
            reverse("login"),
            {"username": "applicant", "password": "secret123"},
        )

        self.assertRedirects(response, reverse("main:home"))
        self.assertEqual(self.client.get(reverse("main:profile")).status_code, 200)


class SeedDataTests(TestCase):
    def test_default_categories_exist(self):
        self.assertTrue(Category.objects.filter(slug="bug").exists())
        self.assertTrue(Category.objects.filter(slug="development").exists())


class CompetitionModelTests(TestCase):
    def setUp(self):
        self.year = CompetitionYear.objects.create(year=2026)
        self.category, _ = Category.objects.get_or_create(
            slug="bug",
            defaults={"name": "Bug / Suggestion", "order": 1},
        )

    def make_form(self, **overrides):
        data = {
            "year": self.year,
            "category": self.category,
            "title": "Application form",
        }
        data.update(overrides)
        return FormDefinition.objects.create(**data)

    def test_competition_year_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CompetitionYear.objects.create(year=2026)

    def test_form_is_unique_per_year_and_category(self):
        self.make_form()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_form()

    def test_open_form_accepts_submissions(self):
        form = self.make_form(status=FormDefinition.Status.OPEN)

        self.assertTrue(form.is_accepting_submissions)

    def test_form_in_review_does_not_accept_submissions(self):
        form = self.make_form(status=FormDefinition.Status.IN_REVIEW)

        self.assertFalse(form.is_accepting_submissions)

    def test_form_outside_date_window_does_not_accept_submissions(self):
        now = timezone.now()
        future = self.make_form(opens_at=now + timedelta(days=1))
        past = self.make_form(
            category=Category.objects.create(slug="other", name="Other"),
            opens_at=now - timedelta(days=2),
            closes_at=now - timedelta(days=1),
        )

        self.assertFalse(future.is_accepting_submissions)
        self.assertFalse(past.is_accepting_submissions)

    def test_form_inside_date_window_accepts_submissions(self):
        now = timezone.now()
        form = self.make_form(
            opens_at=now - timedelta(days=1),
            closes_at=now + timedelta(days=1),
        )

        self.assertTrue(form.is_accepting_submissions)

    def test_closing_date_must_be_after_opening_date(self):
        now = timezone.now()
        form = FormDefinition(
            year=self.year,
            category=self.category,
            title="Invalid dates",
            opens_at=now,
            closes_at=now - timedelta(days=1),
        )

        with self.assertRaises(ValidationError):
            form.full_clean()


class FormFieldValidationTests(TestCase):
    def setUp(self):
        self.year = CompetitionYear.objects.create(year=2026)
        self.category = Category.objects.create(slug="custom", name="Custom")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.category,
            title="Custom form",
        )

    def make_field(self, **overrides):
        data = {
            "form": self.form,
            "key": "title",
            "label": "Title",
            "field_type": FormField.FieldType.SHORT_TEXT,
        }
        data.update(overrides)
        return FormField(**data)

    def test_key_must_be_a_lowercase_identifier(self):
        with self.assertRaises(ValidationError) as context:
            self.make_field(key="Title").full_clean()

        self.assertIn("key", context.exception.message_dict)

    def test_reserved_key_is_rejected(self):
        with self.assertRaises(ValidationError) as context:
            self.make_field(key="submit").full_clean()

        self.assertIn("key", context.exception.message_dict)

    def test_select_field_requires_choices(self):
        with self.assertRaises(ValidationError):
            self.make_field(
                key="level",
                field_type=FormField.FieldType.SELECT,
            ).full_clean()

    def test_invalid_regex_is_rejected(self):
        with self.assertRaises(ValidationError) as context:
            self.make_field(regex="[unclosed").full_clean()

        self.assertIn("regex", context.exception.message_dict)

    def test_max_length_must_not_be_below_min_length(self):
        with self.assertRaises(ValidationError) as context:
            self.make_field(min_length=10, max_length=5).full_clean()

        self.assertIn("max_length", context.exception.message_dict)

    def test_field_key_is_unique_per_form(self):
        FormField.objects.create(
            form=self.form,
            key="title",
            label="Title",
            field_type=FormField.FieldType.SHORT_TEXT,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            FormField.objects.create(
                form=self.form,
                key="title",
                label="Another title",
                field_type=FormField.FieldType.SHORT_TEXT,
            )


class DynamicFormTests(TestCase):
    def setUp(self):
        self.year = CompetitionYear.objects.create(year=2026)
        self.category = Category.objects.create(slug="dynamic", name="Dynamic")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.category,
            title="Dynamic form",
        )
        FormField.objects.create(
            form=self.form,
            key="title",
            label="Title",
            field_type=FormField.FieldType.SHORT_TEXT,
            max_length=10,
            order=1,
        )
        FormField.objects.create(
            form=self.form,
            key="repo",
            label="Repository",
            field_type=FormField.FieldType.URL,
            is_required=False,
            order=2,
        )
        FormField.objects.create(
            form=self.form,
            key="level",
            label="Level",
            field_type=FormField.FieldType.SELECT,
            choices=[
                {"value": "low", "label": "Low"},
                {"value": "high", "label": "High"},
            ],
            order=3,
        )
        FormField.objects.create(
            form=self.form,
            key="topics",
            label="Topics",
            field_type=FormField.FieldType.MULTI_SELECT,
            choices=[
                {"value": "ui", "label": "UI"},
                {"value": "core", "label": "Core"},
            ],
            order=4,
        )
        FormField.objects.create(
            form=self.form,
            key="confirmed",
            label="Confirmed",
            field_type=FormField.FieldType.BOOLEAN,
            order=5,
        )
        FormField.objects.create(
            form=self.form,
            key="inactive",
            label="Inactive",
            field_type=FormField.FieldType.SHORT_TEXT,
            is_active=False,
            order=6,
        )

    def valid_data(self, **overrides):
        data = {
            "title": "Hello",
            "repo": "https://example.com/repo",
            "level": "low",
            "topics": ["ui", "core"],
            "confirmed": "on",
        }
        data.update(overrides)
        return data

    def test_only_active_fields_are_included(self):
        form = build_form(self.form)

        self.assertIn("title", form.fields)
        self.assertNotIn("inactive", form.fields)

    def test_valid_data_is_accepted(self):
        form = build_form(self.form, data=self.valid_data())

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["title"], "Hello")
        self.assertEqual(form.cleaned_data["level"], "low")
        self.assertEqual(form.cleaned_data["topics"], ["ui", "core"])
        self.assertTrue(form.cleaned_data["confirmed"])

    def test_required_and_max_length_rules_are_applied(self):
        form = build_form(self.form, data=self.valid_data(title="This is too long"))

        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)

    def test_invalid_select_value_is_rejected(self):
        form = build_form(self.form, data=self.valid_data(level="medium"))

        self.assertFalse(form.is_valid())
        self.assertIn("level", form.errors)

    def test_regex_constraint_is_enforced(self):
        FormField.objects.create(
            form=self.form,
            key="code",
            label="Code",
            field_type=FormField.FieldType.SHORT_TEXT,
            regex=r"^\d{3}$",
            order=7,
        )

        invalid = build_form(self.form, data=self.valid_data(code="12"))
        valid = build_form(self.form, data=self.valid_data(code="123"))

        self.assertFalse(invalid.is_valid())
        self.assertIn("code", invalid.errors)
        self.assertTrue(valid.is_valid(), valid.errors)


class FormPreviewTests(TestCase):
    def setUp(self):
        year = CompetitionYear.objects.create(year=2026)
        category = Category.objects.create(slug="preview", name="Preview")
        self.form = FormDefinition.objects.create(
            year=year,
            category=category,
            title="Preview form",
        )
        FormField.objects.create(
            form=self.form,
            key="title",
            label="Project title",
            field_type=FormField.FieldType.SHORT_TEXT,
        )

    def test_preview_requires_staff(self):
        response = self.client.get(
            reverse("main:form_preview", args=[self.form.pk])
        )

        self.assertEqual(response.status_code, 302)

    def test_staff_can_preview_form(self):
        staff = get_user_model().objects.create_user(
            username="staff",
            email="staff@example.com",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(staff)

        response = self.client.get(
            reverse("main:form_preview", args=[self.form.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Project title")


class AdminTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="admin",
            email="admin@example.com",
            password="secret123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.staff)
        self.year = CompetitionYear.objects.create(year=2026)
        self.category = Category.objects.create(slug="admin", name="Admin")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.category,
            title="Admin form",
        )

    def test_admin_pages_load(self):
        urls = (
            reverse("admin:index"),
            reverse("admin:main_formdefinition_add"),
            reverse("admin:main_formfield_add"),
            reverse("admin:main_formdefinition_change", args=[self.form.pk]),
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_admin_can_create_select_field_with_choices(self):
        response = self.client.post(
            reverse("admin:main_formfield_add"),
            {
                "form": self.form.pk,
                "key": "level",
                "label": "Level",
                "field_type": FormField.FieldType.SELECT,
                "help_text": "",
                "is_required": "on",
                "min_length": "",
                "max_length": "",
                "regex": "",
                "regex_error_message": "",
                "order": 1,
                "is_active": "on",
                "review_visibility": "visible",
                "choices_text": "Low\nHigh",
            },
        )

        self.assertEqual(response.status_code, 302)
        field = FormField.objects.get(key="level")
        self.assertEqual(
            field.choices,
            [
                {"value": "Low", "label": "Low"},
                {"value": "High", "label": "High"},
            ],
        )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ApplicationServiceTests(MediaTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="applicant",
            email="applicant@example.com",
            password="secret123",
        )
        Profile.objects.create(
            user=self.user,
            phone="+90 555 111 22 33",
            city="Ankara",
            institution="Pardus University",
            education_level=Profile.EducationLevel.BACHELOR,
        )
        self.year = CompetitionYear.objects.create(year=2026)
        self.bug = Category.objects.get(slug="bug")
        self.development = Category.objects.get(slug="development")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.bug,
            title="Bug form",
            attachment_policy=FormDefinition.AttachmentPolicy.OPTIONAL,
        )
        self.title_field = FormField.objects.create(
            form=self.form,
            key="title",
            label="Title",
            field_type=FormField.FieldType.SHORT_TEXT,
            order=1,
        )
        self.level_field = FormField.objects.create(
            form=self.form,
            key="level",
            label="Level",
            field_type=FormField.FieldType.SELECT,
            is_required=False,
            choices=[{"value": "low", "label": "Low"}],
            order=2,
        )

    def make_user(self, username="second", email="second@example.com"):
        user = get_user_model().objects.create_user(
            username=username,
            email=email,
            password="secret123",
        )
        Profile.objects.create(
            user=user,
            phone="+90 555 111 22 33",
            city="Ankara",
            institution="Pardus University",
            education_level=Profile.EducationLevel.BACHELOR,
        )
        return user

    def make_form(self, category=None, policy=None):
        form = FormDefinition.objects.create(
            year=self.year,
            category=category or self.development,
            title="Other form",
            attachment_policy=policy or FormDefinition.AttachmentPolicy.OPTIONAL,
        )
        FormField.objects.create(
            form=form,
            key="title",
            label="Title",
            field_type=FormField.FieldType.SHORT_TEXT,
        )
        return form

    def valid_data(self, **overrides):
        data = {"title": "A bug report"}
        data.update(overrides)
        return data

    def submit_application(self, data=None, files=None, form=None, user=None):
        return submit_application(
            user or self.user,
            form or self.form,
            self.valid_data() if data is None else data,
            files=files,
        )

    def test_submission_creates_application_code_and_email(self):
        application = self.submit_application()

        self.assertEqual(application.status, Application.Status.SUBMITTED)
        self.assertEqual(application.code, "BUG-2026-00001")
        self.assertIsNotNone(application.submitted_at)
        self.assertEqual(
            ApplicationAnswer.objects.get(
                application=application,
                field=self.title_field,
            ).value,
            "A bug report",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn(application.code, mail.outbox[0].body)

    def test_submission_rejects_missing_required_fields(self):
        with self.assertRaises(ValidationError) as context:
            self.submit_application(data={})

        self.assertIn("title", context.exception.message_dict)
        self.assertFalse(Application.objects.exists())

    def test_submission_rejects_invalid_choice(self):
        with self.assertRaises(ValidationError) as context:
            self.submit_application(data=self.valid_data(level="unknown"))

        self.assertIn("level", context.exception.message_dict)
        self.assertFalse(Application.objects.exists())

    def test_submission_requires_complete_profile(self):
        self.user.profile.city = ""
        self.user.profile.save()

        with self.assertRaisesMessage(ValidationError, "Complete your profile"):
            self.submit_application()

    def test_required_attachment_policy(self):
        self.form.attachment_policy = FormDefinition.AttachmentPolicy.REQUIRED
        self.form.save()

        with self.assertRaisesMessage(ValidationError, "At least one attachment"):
            self.submit_application()

        application = self.submit_application(files=[make_image()])
        self.assertEqual(application.attachments.count(), 1)

    def test_no_attachment_policy(self):
        self.form.attachment_policy = FormDefinition.AttachmentPolicy.NONE
        self.form.save()

        with self.assertRaisesMessage(ValidationError, "does not accept attachments"):
            self.submit_application(files=[make_image()])

        application = self.submit_application()
        self.assertEqual(application.attachments.count(), 0)

    def test_application_codes_increment_per_year_and_category(self):
        other_user = self.make_user()
        first = self.submit_application()
        second = self.submit_application(user=other_user)

        self.assertEqual([first.code, second.code], ["BUG-2026-00001", "BUG-2026-00002"])

    def test_duplicate_application_per_form_is_rejected(self):
        self.submit_application()

        with self.assertRaisesMessage(ValidationError, "already have an application"):
            self.submit_application()

        self.assertEqual(Application.objects.count(), 1)

    def test_application_is_editable_only_while_form_accepts(self):
        application = self.submit_application()
        self.form.status = FormDefinition.Status.IN_REVIEW
        self.form.save()
        application.refresh_from_db()

        with self.assertRaisesMessage(ValidationError, "can no longer be edited"):
            update_application(application, self.valid_data())
        with self.assertRaisesMessage(ValidationError, "can no longer be edited"):
            delete_application(application)

    def test_update_replaces_answers_and_adds_files(self):
        application = self.submit_application()

        update_application(
            application,
            self.valid_data(title="Updated title"),
            files=[make_image()],
        )

        self.assertEqual(
            ApplicationAnswer.objects.get(
                application=application,
                field=self.title_field,
            ).value,
            "Updated title",
        )
        self.assertEqual(application.attachments.count(), 1)

    def test_update_requires_complete_data(self):
        application = self.submit_application()

        with self.assertRaises(ValidationError):
            update_application(application, {})

        self.assertEqual(
            ApplicationAnswer.objects.get(
                application=application,
                field=self.title_field,
            ).value,
            "A bug report",
        )

    def test_file_types_are_validated(self):
        uploads = (
            make_image(name="animation.gif", image_format="GIF"),
            SimpleUploadedFile("document.pdf", b"%PDF-1.4", content_type="application/pdf"),
            SimpleUploadedFile("fake.png", b"not an image", content_type="image/png"),
        )

        for upload in uploads:
            with self.subTest(name=upload.name):
                with self.assertRaisesMessage(ValidationError, "Upload a JPG or PNG"):
                    self.submit_application(files=[upload])

        self.assertFalse(Application.objects.exists())

    @patch("main.services.applications.MAX_FILE_SIZE", 10)
    def test_per_file_size_limit(self):
        with self.assertRaisesMessage(ValidationError, "2 MB or smaller"):
            self.submit_application(files=[make_image()])

    @patch("main.services.applications.MAX_TOTAL_SIZE", 1)
    def test_total_size_limit(self):
        with self.assertRaisesMessage(ValidationError, "10 MB or smaller"):
            self.submit_application(files=[make_image()])

    @patch("main.services.applications.MAX_ATTACHMENTS", 1)
    def test_attachment_count_limit(self):
        with self.assertRaisesMessage(ValidationError, "At most 1"):
            self.submit_application(files=[make_image(), make_image()])

    def test_delete_application_removes_files(self):
        application = self.submit_application(files=[make_image()])
        attachment = application.attachments.get()
        path = Path(attachment.file.path)
        self.assertTrue(path.exists())

        delete_application(application)

        self.assertFalse(Application.objects.filter(pk=application.pk).exists())
        self.assertFalse(path.exists())

    def test_required_attachment_cannot_be_removed(self):
        self.form.attachment_policy = FormDefinition.AttachmentPolicy.REQUIRED
        self.form.save()
        application = self.submit_application(files=[make_image()])

        with self.assertRaisesMessage(ValidationError, "At least one attachment"):
            delete_attachment(application.attachments.get())

        add_attachment(application, make_image())
        delete_attachment(application.attachments.first())

        self.assertEqual(application.attachments.count(), 1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ApplicationViewTests(MediaTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="applicant",
            email="applicant@example.com",
            password="secret123",
        )
        Profile.objects.create(
            user=self.user,
            phone="+90 555 111 22 33",
            city="Ankara",
            institution="Pardus University",
            education_level=Profile.EducationLevel.BACHELOR,
        )
        self.other_user = get_user_model().objects.create_user(
            username="other",
            email="other@example.com",
            password="secret123",
        )
        Profile.objects.create(
            user=self.other_user,
            phone="+90 555 111 22 33",
            city="Ankara",
            institution="Pardus University",
            education_level=Profile.EducationLevel.BACHELOR,
        )
        self.year = CompetitionYear.objects.create(year=2026)
        self.bug = Category.objects.get(slug="bug")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.bug,
            title="Bug form",
            attachment_policy=FormDefinition.AttachmentPolicy.OPTIONAL,
        )
        self.title_field = FormField.objects.create(
            form=self.form,
            key="title",
            label="Title",
            field_type=FormField.FieldType.SHORT_TEXT,
            order=1,
        )
        FormField.objects.create(
            form=self.form,
            key="level",
            label="Level",
            field_type=FormField.FieldType.SELECT,
            is_required=False,
            choices=[{"value": "low", "label": "Low"}],
            order=2,
        )
        self.client.force_login(self.user)

    def valid_data(self, **overrides):
        data = {"title": "A bug report"}
        data.update(overrides)
        return data

    def make_application(self, user=None, files=None, data=None):
        return submit_application(
            user or self.user,
            self.form,
            self.valid_data() if data is None else data,
            files=files,
        )

    def test_application_routes_require_login(self):
        self.client.logout()
        urls = (
            reverse("main:form_list"),
            reverse("main:form_detail", args=[self.form.pk]),
            reverse("main:application_start", args=[self.form.pk]),
            reverse("main:application_list"),
            reverse("main:profile"),
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_form_list_context(self):
        response = self.client.get(reverse("main:form_list"))

        self.assertIn(self.form, response.context["forms"])

    def test_form_detail_context_allows_applying(self):
        response = self.client.get(reverse("main:form_detail", args=[self.form.pk]))

        self.assertTrue(response.context["can_apply"])
        self.assertIn(self.title_field, response.context["fields"])

    def test_form_detail_disables_applying_when_application_exists(self):
        application = self.make_application()

        response = self.client.get(reverse("main:form_detail", args=[self.form.pk]))

        self.assertFalse(response.context["can_apply"])
        self.assertEqual(response.context["existing_application"], application)

    def test_apply_page_renders_empty_form(self):
        response = self.client.get(
            reverse("main:application_start", args=[self.form.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("application_form", response.context)
        self.assertFalse(Application.objects.exists())

    def test_apply_post_creates_submitted_application(self):
        response = self.client.post(
            reverse("main:application_start", args=[self.form.pk]),
            self.valid_data(),
        )
        application = Application.objects.get(applicant=self.user, form=self.form)

        self.assertEqual(application.status, Application.Status.SUBMITTED)
        self.assertEqual(application.code, "BUG-2026-00001")
        self.assertRedirects(
            response,
            reverse("main:application_detail", args=[application.public_id]),
        )

    def test_apply_post_with_file(self):
        response = self.client.post(
            reverse("main:application_start", args=[self.form.pk]),
            {**self.valid_data(), "files": make_image()},
        )
        application = Application.objects.get(applicant=self.user, form=self.form)

        self.assertEqual(application.attachments.count(), 1)
        self.assertRedirects(
            response,
            reverse("main:application_detail", args=[application.public_id]),
        )

    def test_apply_post_with_invalid_data_rerenders(self):
        response = self.client.post(
            reverse("main:application_start", args=[self.form.pk]),
            {},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["application_form"].errors)
        self.assertFalse(Application.objects.exists())

    def test_apply_redirects_to_existing_application(self):
        application = self.make_application()

        response = self.client.get(
            reverse("main:application_start", args=[self.form.pk])
        )

        self.assertRedirects(
            response,
            reverse("main:application_detail", args=[application.public_id]),
        )

    def test_apply_redirects_when_form_is_closed(self):
        self.form.status = FormDefinition.Status.IN_REVIEW
        self.form.save()

        response = self.client.get(
            reverse("main:application_start", args=[self.form.pk])
        )

        self.assertRedirects(
            response,
            reverse("main:form_detail", args=[self.form.pk]),
        )

    def test_application_list_and_detail_context(self):
        application = self.make_application()

        listing = self.client.get(reverse("main:application_list"))
        detail = self.client.get(
            reverse("main:application_detail", args=[application.public_id])
        )

        self.assertIn(application, listing.context["applications"])
        self.assertTrue(detail.context["can_edit"])
        self.assertEqual(
            detail.context["field_answers"][0]["value"],
            "A bug report",
        )

    def test_other_user_cannot_access_application(self):
        application = self.make_application(user=self.other_user)

        response = self.client.get(
            reverse("main:application_detail", args=[application.public_id])
        )

        self.assertEqual(response.status_code, 404)

    def test_edit_get_exposes_stored_answers(self):
        application = self.make_application()

        response = self.client.get(
            reverse("main:application_edit", args=[application.public_id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["application_form"]["title"].value(),
            "A bug report",
        )
        self.assertTrue(response.context["can_add_attachment"])

    def test_edit_post_updates_application(self):
        application = self.make_application()

        response = self.client.post(
            reverse("main:application_edit", args=[application.public_id]),
            self.valid_data(title="Updated title"),
        )

        self.assertRedirects(
            response,
            reverse("main:application_detail", args=[application.public_id]),
        )
        self.assertEqual(
            ApplicationAnswer.objects.get(
                application=application,
                field=self.title_field,
            ).value,
            "Updated title",
        )

    def test_edit_post_with_file_adds_attachment(self):
        application = self.make_application()

        response = self.client.post(
            reverse("main:application_edit", args=[application.public_id]),
            {**self.valid_data(), "files": make_image()},
        )

        self.assertRedirects(
            response,
            reverse("main:application_detail", args=[application.public_id]),
        )
        self.assertEqual(application.attachments.count(), 1)

    def test_edit_post_with_invalid_choice_rerenders(self):
        application = self.make_application()

        response = self.client.post(
            reverse("main:application_edit", args=[application.public_id]),
            self.valid_data(level="unknown"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("level", response.context["application_form"].errors)

    def test_closed_form_blocks_edit_and_delete(self):
        application = self.make_application()
        self.form.status = FormDefinition.Status.IN_REVIEW
        self.form.save()

        edit = self.client.get(
            reverse("main:application_edit", args=[application.public_id])
        )
        delete = self.client.post(
            reverse("main:application_delete", args=[application.public_id])
        )

        self.assertRedirects(
            edit,
            reverse("main:application_detail", args=[application.public_id]),
        )
        self.assertRedirects(
            delete,
            reverse("main:application_detail", args=[application.public_id]),
        )
        self.assertTrue(Application.objects.filter(pk=application.pk).exists())

    def test_upload_and_delete_attachment(self):
        application = self.make_application()
        upload = self.client.post(
            reverse("main:attachment_upload", args=[application.public_id]),
            {"file": make_image()},
        )
        attachment = application.attachments.get()
        path = Path(attachment.file.path)

        delete = self.client.post(
            reverse(
                "main:attachment_delete",
                args=[application.public_id, attachment.pk],
            )
        )

        self.assertRedirects(
            upload,
            reverse("main:application_edit", args=[application.public_id]),
        )
        self.assertRedirects(
            delete,
            reverse("main:application_edit", args=[application.public_id]),
        )
        self.assertFalse(path.exists())

    def test_delete_application(self):
        application = self.make_application(files=[make_image()])
        attachment = application.attachments.get()
        path = Path(attachment.file.path)

        response = self.client.post(
            reverse("main:application_delete", args=[application.public_id])
        )

        self.assertRedirects(response, reverse("main:application_list"))
        self.assertFalse(Application.objects.filter(pk=application.pk).exists())
        self.assertFalse(path.exists())

    def test_preview_context(self):
        application = self.make_application()

        response = self.client.get(
            reverse("main:application_preview", args=[application.public_id])
        )

        self.assertEqual(
            response.context["field_answers"][0]["value"],
            "A bug report",
        )


class JuryTests(MediaTestCase):
    def setUp(self):
        self.applicant = get_user_model().objects.create_user(
            username="applicant",
            email="applicant@example.com",
            password="secret123",
        )
        self.jury = get_user_model().objects.create_user(
            username="jury",
            email="jury@example.com",
            password="secret123",
        )
        self.jury.groups.add(Group.objects.get(name="jury"))
        self.other_jury = get_user_model().objects.create_user(
            username="jury2",
            email="jury2@example.com",
            password="secret123",
        )
        self.other_jury.groups.add(Group.objects.get(name="jury"))
        self.admin = get_user_model().objects.create_user(
            username="admin",
            email="admin@example.com",
            password="secret123",
            is_staff=True,
        )

        self.year = CompetitionYear.objects.create(year=2026)
        self.category = Category.objects.get(slug="bug")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.category,
            title="Bug form",
            status=FormDefinition.Status.IN_REVIEW,
        )
        self.visible_field = FormField.objects.create(
            form=self.form,
            key="title",
            label="Title",
            field_type=FormField.FieldType.SHORT_TEXT,
            review_visibility=FormField.ReviewVisibility.VISIBLE,
            order=1,
        )
        self.hidden_field = FormField.objects.create(
            form=self.form,
            key="secret",
            label="Secret",
            field_type=FormField.FieldType.SHORT_TEXT,
            review_visibility=FormField.ReviewVisibility.HIDDEN,
            order=2,
        )
        self.application = Application.objects.create(
            applicant=self.applicant,
            form=self.form,
            year=self.year,
            category=self.category,
            status=Application.Status.SUBMITTED,
            code="BUG-2026-00001",
            submitted_at=timezone.now(),
        )
        ApplicationAnswer.objects.create(
            application=self.application,
            field=self.visible_field,
            value="Visible answer",
        )
        ApplicationAnswer.objects.create(
            application=self.application,
            field=self.hidden_field,
            value="Hidden answer",
        )
        self.client.force_login(self.jury)

    def make_application(self, code=None):
        user = get_user_model().objects.create_user(
            username=f"applicant-{Application.objects.count() + 1}",
            email=f"applicant{Application.objects.count() + 1}@example.com",
            password="secret123",
        )
        return Application.objects.create(
            applicant=user,
            form=self.form,
            year=self.year,
            category=self.category,
            status=Application.Status.SUBMITTED,
            code=code,
            submitted_at=timezone.now(),
        )

    def add_attachment(self):
        return Attachment.objects.create(
            application=self.application,
            file=SimpleUploadedFile("shot.png", b"image-bytes", content_type="image/png"),
            original_name="shot.png",
            content_type="image/png",
            size=11,
        )

    def test_jury_pages_require_login(self):
        self.client.logout()
        urls = (
            reverse("main:jury_dashboard"),
            reverse("main:jury_application_list", args=[self.form.pk]),
            reverse("main:jury_application_detail", args=[self.application.public_id]),
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_applicants_cannot_access_jury_pages(self):
        self.client.force_login(self.applicant)
        urls = (
            reverse("main:jury_dashboard"),
            reverse("main:jury_application_list", args=[self.form.pk]),
            reverse("main:jury_application_detail", args=[self.application.public_id]),
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_jury_can_access_jury_pages(self):
        self.assertEqual(self.client.get(reverse("main:jury_dashboard")).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("main:jury_application_list", args=[self.form.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "main:jury_application_detail",
                    args=[self.application.public_id],
                )
            ).status_code,
            200,
        )

    def test_admin_is_also_jury(self):
        self.client.force_login(self.admin)

        self.assertEqual(self.client.get(reverse("main:jury_dashboard")).status_code, 200)
        response = self.client.post(
            reverse(
                "main:jury_review_submit",
                args=[self.application.public_id],
            ),
            {"score": "90"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Review.objects.filter(
                application=self.application,
                juror=self.admin,
                score=90,
                completed_at__isnull=False,
            ).exists()
        )

    def test_dashboard_counts(self):
        response = self.client.get(reverse("main:jury_dashboard"))
        form = next(
            item for item in response.context["forms"] if item.pk == self.form.pk
        )

        self.assertEqual(form.application_count, 1)
        self.assertEqual(form.my_completed_count, 0)

        submit_review(self.application, self.jury, score=80)
        response = self.client.get(reverse("main:jury_dashboard"))
        form = next(
            item for item in response.context["forms"] if item.pk == self.form.pk
        )

        self.assertEqual(form.my_completed_count, 1)

    def test_list_mine_filter(self):
        url = reverse("main:jury_application_list", args=[self.form.pk])

        pending = self.client.get(url, {"mine": "pending"})
        completed = self.client.get(url, {"mine": "completed"})

        self.assertEqual(len(pending.context["rows"]), 1)
        self.assertEqual(len(completed.context["rows"]), 0)

        submit_review(self.application, self.jury, score=80)

        pending = self.client.get(url, {"mine": "pending"})
        completed = self.client.get(url, {"mine": "completed"})

        self.assertEqual(len(pending.context["rows"]), 0)
        self.assertEqual(len(completed.context["rows"]), 1)

    def test_list_files_filter(self):
        url = reverse("main:jury_application_list", args=[self.form.pk])

        without_files = self.client.get(url, {"files": "1"})
        self.add_attachment()
        with_files = self.client.get(url, {"files": "1"})

        self.assertEqual(len(without_files.context["rows"]), 0)
        self.assertEqual(len(with_files.context["rows"]), 1)

    def test_list_hides_average_until_my_review_is_completed(self):
        other_review = Review.objects.create(
            application=self.application,
            juror=self.other_jury,
            score=60,
            completed_at=timezone.now(),
        )
        url = reverse("main:jury_application_list", args=[self.form.pk])

        blind = self.client.get(url)
        self.assertIsNone(blind.context["rows"][0]["average"])

        submit_review(self.application, self.jury, score=80)
        revealed = self.client.get(url)
        self.assertEqual(revealed.context["rows"][0]["average"], 70.0)

    def test_list_search_by_code(self):
        url = reverse("main:jury_application_list", args=[self.form.pk])

        match = self.client.get(url, {"q": "BUG-2026-00001"})
        no_match = self.client.get(url, {"q": "nothing"})

        self.assertEqual(len(match.context["rows"]), 1)
        self.assertEqual(len(no_match.context["rows"]), 0)

    def test_detail_hides_others_until_review_is_completed(self):
        Review.objects.create(
            application=self.application,
            juror=self.other_jury,
            score=60,
            note="Other note",
            completed_at=timezone.now(),
        )
        url = reverse(
            "main:jury_application_detail",
            args=[self.application.public_id],
        )

        blind = self.client.get(url)
        self.assertTrue(blind.context["is_blind"])
        self.assertEqual(blind.context["other_reviews"], [])
        self.assertIsNone(blind.context["average_score"])

        submit_review(self.application, self.jury, score=80)
        revealed = self.client.get(url)
        self.assertFalse(revealed.context["is_blind"])
        self.assertEqual(len(revealed.context["other_reviews"]), 1)
        self.assertEqual(revealed.context["average_score"], 70.0)

    def test_detail_filters_hidden_fields_and_lists_attachments(self):
        attachment = self.add_attachment()

        response = self.client.get(
            reverse(
                "main:jury_application_detail",
                args=[self.application.public_id],
            )
        )

        values = [item["value"] for item in response.context["field_answers"]]
        self.assertIn("Visible answer", values)
        self.assertNotIn("Hidden answer", values)
        self.assertIn(attachment, response.context["attachments"])

    def test_detail_can_review_only_while_form_is_in_review(self):
        url = reverse(
            "main:jury_application_detail",
            args=[self.application.public_id],
        )

        self.assertTrue(self.client.get(url).context["can_review"])

        self.form.status = FormDefinition.Status.OPEN
        self.form.save()
        self.assertFalse(self.client.get(url).context["can_review"])

        self.form.status = FormDefinition.Status.CLOSED
        self.form.save()
        self.assertFalse(self.client.get(url).context["can_review"])

    def test_save_review_keeps_blind_view(self):
        response = self.client.post(
            reverse("main:jury_review_save", args=[self.application.public_id]),
            {"score": "75", "note": "Draft note"},
        )

        self.assertEqual(response.status_code, 302)
        review = Review.objects.get(application=self.application, juror=self.jury)
        self.assertEqual(review.score, 75)
        self.assertIsNone(review.completed_at)

    def test_submit_review_requires_score(self):
        response = self.client.post(
            reverse("main:jury_review_submit", args=[self.application.public_id]),
            {"note": "No score"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Review.objects.filter(juror=self.jury).exists())

    def test_submit_review_with_score_only_completes(self):
        response = self.client.post(
            reverse("main:jury_review_submit", args=[self.application.public_id]),
            {"score": "90"},
        )

        self.assertEqual(response.status_code, 302)
        review = Review.objects.get(application=self.application, juror=self.jury)
        self.assertEqual(review.score, 90)
        self.assertEqual(review.note, "")
        self.assertIsNotNone(review.completed_at)

    def test_score_must_be_between_zero_and_hundred(self):
        with self.assertRaises(ValidationError):
            save_review(self.application, self.jury, score=101)
        with self.assertRaises(ValidationError):
            save_review(self.application, self.jury, score="abc")

    def test_scoring_requires_in_review_form(self):
        self.form.status = FormDefinition.Status.OPEN
        self.form.save()

        with self.assertRaises(ValidationError):
            save_review(self.application, self.jury, score=80)

        self.form.status = FormDefinition.Status.CLOSED
        self.form.save()

        with self.assertRaises(ValidationError):
            save_review(self.application, self.jury, score=80)

    def test_review_is_updated_not_duplicated(self):
        save_review(self.application, self.jury, score=50, note="First")
        save_review(self.application, self.jury, score=70, note="Second")

        self.assertEqual(
            Review.objects.filter(application=self.application, juror=self.jury).count(),
            1,
        )
        review = Review.objects.get(application=self.application, juror=self.jury)
        self.assertEqual(review.score, 70)
        self.assertEqual(review.note, "Second")

    def test_completed_review_can_be_edited_while_in_review(self):
        review = submit_review(self.application, self.jury, score=50)
        completed_at = review.completed_at

        updated = submit_review(self.application, self.jury, score=70)

        self.assertEqual(updated.score, 70)
        self.assertEqual(updated.completed_at, completed_at)

    def test_jury_cannot_use_applicant_or_profile_routes(self):
        urls = (
            reverse("main:form_list"),
            reverse("main:form_detail", args=[self.form.pk]),
            reverse("main:application_list"),
            reverse("main:application_detail", args=[self.application.public_id]),
            reverse("main:profile"),
            reverse("main:profile_edit"),
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url),
                    reverse("main:jury_dashboard"),
                )

    def test_jury_cannot_start_application(self):
        response = self.client.post(
            reverse("main:application_start", args=[self.form.pk])
        )

        self.assertRedirects(response, reverse("main:jury_dashboard"))
        self.assertFalse(Application.objects.filter(applicant=self.jury).exists())

    def test_admin_cannot_use_applicant_or_profile_routes(self):
        self.client.force_login(self.admin)

        for url in (
            reverse("main:form_list"),
            reverse("main:application_list"),
            reverse("main:profile"),
        ):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url),
                    reverse("main:jury_dashboard"),
                )

    def test_applicant_is_not_redirected_from_applicant_routes(self):
        self.client.force_login(self.applicant)

        self.assertEqual(self.client.get(reverse("main:form_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("main:profile")).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse(
                    "main:application_detail",
                    args=[self.application.public_id],
                )
            ).status_code,
            200,
        )

    def test_application_services_reject_jury_accounts(self):
        with self.assertRaisesMessage(ValidationError, "Jury accounts"):
            submit_application(self.jury, self.form, {"title": "Nope"})
        with self.assertRaisesMessage(ValidationError, "Jury accounts"):
            submit_application(self.admin, self.form, {"title": "Nope"})

    def test_detail_masks_applicant_identity_when_enabled(self):
        self.applicant.first_name = "Ada"
        self.applicant.last_name = "Lovelace"
        self.applicant.save()
        self.form.mask_applicant_identity = True
        self.form.save()

        response = self.client.get(
            reverse(
                "main:jury_application_detail",
                args=[self.application.public_id],
            )
        )

        self.assertTrue(response.context["applicant_identity_masked"])
        self.assertEqual(response.context["applicant_name"], "Gizli başvuru sahibi")
        self.assertIsNone(response.context["applicant_email"])

    def test_detail_shows_applicant_identity_by_default(self):
        self.applicant.first_name = "Ada"
        self.applicant.last_name = "Lovelace"
        self.applicant.save()

        response = self.client.get(
            reverse(
                "main:jury_application_detail",
                args=[self.application.public_id],
            )
        )

        self.assertFalse(response.context["applicant_identity_masked"])
        self.assertEqual(response.context["applicant_name"], "Ada Lovelace")
        self.assertEqual(response.context["applicant_email"], self.applicant.email)

    def test_list_disables_email_search_when_identity_is_masked(self):
        url = reverse("main:jury_application_list", args=[self.form.pk])

        self.assertEqual(
            len(self.client.get(url, {"q": self.applicant.email}).context["rows"]),
            1,
        )

        self.form.mask_applicant_identity = True
        self.form.save()

        self.assertEqual(
            len(self.client.get(url, {"q": self.applicant.email}).context["rows"]),
            0,
        )
        self.assertEqual(
            len(self.client.get(url, {"q": "BUG-2026-00001"}).context["rows"]),
            1,
        )

    def test_masked_field_hides_value(self):
        masked_field = FormField.objects.create(
            form=self.form,
            key="private_note",
            label="Private note",
            field_type=FormField.FieldType.SHORT_TEXT,
            review_visibility=FormField.ReviewVisibility.MASKED,
            order=3,
        )
        ApplicationAnswer.objects.create(
            application=self.application,
            field=masked_field,
            value="Top secret",
        )

        response = self.client.get(
            reverse(
                "main:jury_application_detail",
                args=[self.application.public_id],
            )
        )

        items = {
            item["field"].key: item for item in response.context["field_answers"]
        }
        values = [item["value"] for item in response.context["field_answers"]]

        self.assertEqual(items["private_note"]["value"], MASKED_FIELD_MESSAGE)
        self.assertTrue(items["private_note"]["is_masked"])
        self.assertNotIn("Top secret", values)
        self.assertNotIn("Hidden answer", values)
        self.assertIn("Visible answer", values)
