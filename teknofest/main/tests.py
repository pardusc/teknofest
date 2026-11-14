import shutil
import tempfile
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .dynamic_forms import build_form
from .models import Category, CompetitionYear, FormDefinition, FormField, Profile


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


class ProfileTests(TestCase):
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
            response.context["form"], "photo", "Upload a JPG, PNG or WebP image."
        )

    @patch("main.forms.MAX_PHOTO_SIZE", 10)
    def test_oversized_photo_is_rejected(self):
        data = self.valid_data()
        data["photo"] = make_image()

        response = self.client.post(reverse("main:profile_edit"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "photo", "The photo must be 5 MB or smaller."
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
                "is_visible_in_review": "on",
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
