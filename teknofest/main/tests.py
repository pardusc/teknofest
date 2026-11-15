import json
import os
import re
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
from django.contrib.admin.sites import site as admin_site
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from PIL import Image

from .dynamic_forms import build_form
from .models import (
    Application,
    ApplicationAnswer,
    Attachment,
    AuditEvent,
    Category,
    CategoryTranslation,
    CompetitionYear,
    FormDefinition,
    FormField,
    JuryAPIKey,
    Profile,
    Review,
    SiteSettings,
    SiteSettingsTranslation,
)
from .services.applications import (
    add_attachment,
    delete_application,
    delete_attachment,
    submit_application,
    update_application,
)
from .services.reviews import submit_review
from .admin import (
    ApplicationAdmin,
    AuditEventAdmin,
    FormDefinitionAdmin,
    ProfileAdmin,
    ProfileInline,
    SiteSettingsAdmin,
)
from .forms import FormDefinitionAdminForm, ProfileAdminForm
from .views import (
    MASKED_FIELD_MESSAGE,
    ApplicationDetailView,
    ApplicationListView,
    ApplicationPreviewView,
    ApplicationUpdateView,
    FormDetailView,
    FormListView,
    _validation_message,
)


def make_image(name="photo.png", image_format="PNG", content_type=None):
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format=image_format)
    content_type = content_type or {
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

    def test_home_hero_has_no_login_or_category_cta(self):
        response = self.client.get(reverse("main:home"))

        self.assertNotContains(response, 'class="quick-actions')
        self.assertNotContains(response, 'href="#kategoriler"')

    def test_home_calendar_is_hidden_without_setting(self):
        SiteSettings.objects.filter(pk=1).update(calendar_note="")

        response = self.client.get(reverse("main:home"))

        self.assertNotContains(response, "Takvim")

    def test_home_calendar_uses_site_setting(self):
        SiteSettings.objects.filter(pk=1).update(
            calendar_note="Etkinlik takvimi"
        )

        response = self.client.get(reverse("main:home"))

        self.assertContains(response, "Takvim")
        self.assertContains(response, "Etkinlik takvimi")


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

    def test_incomplete_profile_redirects_applicant_to_profile(self):
        for url in (
            reverse("main:home"),
            reverse("main:form_list"),
            reverse("main:application_list"),
        ):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url),
                    reverse("main:profile"),
                )

    def test_complete_profile_allows_applicant_pages(self):
        Profile.objects.create(
            user=self.user,
            phone="+90 555 111 22 33",
            city="Ankara",
            institution="Pardus University",
            education_level=Profile.EducationLevel.BACHELOR,
        )

        self.assertEqual(self.client.get(reverse("main:home")).status_code, 200)

    def test_profile_page_and_logout_are_always_accessible(self):
        self.assertEqual(self.client.get(reverse("main:profile")).status_code, 200)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("main:home"))

    def test_profile_edit_redirect_does_not_loop(self):
        response = self.client.get(reverse("main:profile_edit"))

        self.assertRedirects(response, reverse("main:profile"))

    def test_jury_without_profile_is_not_redirected(self):
        jury = get_user_model().objects.create_user(
            username="jury-without-profile",
            email="jury-without-profile@example.com",
            password="secret123",
        )
        jury.groups.add(Group.objects.get(name="jury"))
        self.client.force_login(jury)

        self.assertEqual(
            self.client.get(reverse("main:jury_dashboard")).status_code,
            200,
        )

    def test_profile_is_required_until_it_is_completed(self):
        response = self.client.get(reverse("main:home"))

        self.assertRedirects(response, reverse("main:profile"))

        self.client.post(reverse("main:profile"), self.valid_data())

        self.assertEqual(self.client.get(reverse("main:home")).status_code, 200)

    def test_profile_page_creates_and_displays_profile(self):
        response = self.client.get(reverse("main:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Profile.objects.filter(user=self.user).exists())
        self.assertContains(response, self.user.email)

    def test_profile_update_saves_required_fields(self):
        response = self.client.post(reverse("main:profile"), self.valid_data())

        self.assertRedirects(response, reverse("main:profile"))
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.city, "Ankara")
        self.assertEqual(profile.education_level, Profile.EducationLevel.BACHELOR)
        self.assertTrue(profile.is_complete)

    def test_photo_is_optional(self):
        response = self.client.post(reverse("main:profile"), self.valid_data())

        self.assertRedirects(response, reverse("main:profile"))
        self.assertFalse(Profile.objects.get(user=self.user).photo)

    def test_valid_photo_is_uploaded(self):
        data = self.valid_data()
        data["photo"] = make_image()

        response = self.client.post(reverse("main:profile"), data)

        self.assertRedirects(response, reverse("main:profile"))
        self.assertTrue(Profile.objects.get(user=self.user).photo.name.startswith("profiles/"))

    def test_invalid_photo_type_is_rejected(self):
        data = self.valid_data()
        data["photo"] = make_image(name="photo.gif", image_format="GIF")

        response = self.client.post(reverse("main:profile"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "photo", _("Upload a JPG or PNG image.")
        )

    def test_spoofed_photo_type_is_rejected(self):
        data = self.valid_data()
        data["photo"] = make_image(
            name="photo.png",
            image_format="GIF",
            content_type="image/png",
        )

        response = self.client.post(reverse("main:profile"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "photo", _("Upload a JPG or PNG image.")
        )

    def test_jpeg_photo_is_accepted(self):
        data = self.valid_data()
        data["photo"] = make_image(name="photo.jpg", image_format="JPEG")

        response = self.client.post(reverse("main:profile"), data)

        self.assertRedirects(response, reverse("main:profile"))
        self.assertTrue(
            Profile.objects.get(user=self.user).photo.name.endswith(".jpg")
        )

    def test_profile_photo_input_limits_accept_types(self):
        response = self.client.get(reverse("main:profile"))

        self.assertContains(
            response,
            'accept="image/png,image/jpeg,.png,.jpg,.jpeg"',
        )

    @patch("main.forms.MAX_PHOTO_SIZE", 10)
    def test_oversized_photo_is_rejected(self):
        data = self.valid_data()
        data["photo"] = make_image()

        response = self.client.post(reverse("main:profile"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "photo", _("The photo must be 1 MB or smaller.")
        )

    def test_missing_required_field_is_rejected(self):
        data = self.valid_data()
        del data["city"]

        response = self.client.post(reverse("main:profile"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "city", _("This field is required."))

    def test_invalid_phone_is_rejected(self):
        response = self.client.post(
            reverse("main:profile"),
            self.valid_data(phone="not-a-phone"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "phone", _("Enter a valid phone number.")
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

        self.assertRedirects(
            response,
            reverse("main:home"),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(reverse("main:home")),
            reverse("main:profile"),
        )
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
            defaults={"name": "Hata / Öneri", "order": 1},
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

    def test_admin_profile_forms_validate_photo_type(self):
        self.assertIs(ProfileAdmin.form, ProfileAdminForm)
        self.assertIs(ProfileInline.form, ProfileAdminForm)

    def test_admin_form_definition_requires_deadline(self):
        self.assertIs(FormDefinitionAdmin.form, FormDefinitionAdminForm)
        add_url = reverse("admin:main_formdefinition_add")
        response = self.client.get(add_url)
        prefix = response.context["inline_admin_formsets"][0].formset.prefix
        self.assertTrue(response.context["adminform"].form.fields["closes_at"].required)
        category = Category.objects.create(slug="deadline", name="Deadline")
        data = {
            "year": self.year.pk,
            "category": category.pk,
            "title": "Deadline required",
            "description": "",
            "status": FormDefinition.Status.OPEN,
            "attachment_policy": FormDefinition.AttachmentPolicy.OPTIONAL,
            "opens_at_0": "",
            "opens_at_1": "",
            "closes_at_0": "",
            "closes_at_1": "",
            f"{prefix}-TOTAL_FORMS": "0",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }

        response = self.client.post(add_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("closes_at", response.context["adminform"].form.errors)
        self.assertFalse(
            FormDefinition.objects.filter(title="Deadline required").exists()
        )

        closes_at = timezone.localtime() + timedelta(days=5)
        data["closes_at_0"] = closes_at.strftime("%d/%m/%Y")
        data["closes_at_1"] = closes_at.strftime("%H:%M")
        response = self.client.post(add_url, data)
        self.assertEqual(response.status_code, 302)
        form = FormDefinition.objects.get(title="Deadline required")
        self.assertIsNotNone(form.closes_at)

    def test_admin_form_definition_deadline_optional_with_global_deadline(self):
        settings = SiteSettings.load()
        settings.application_closes_at = timezone.now() + timedelta(days=30)
        settings.save(update_fields=["application_closes_at"])

        add_url = reverse("admin:main_formdefinition_add")
        response = self.client.get(add_url)
        prefix = response.context["inline_admin_formsets"][0].formset.prefix
        self.assertFalse(
            response.context["adminform"].form.fields["closes_at"].required
        )

        category = Category.objects.create(slug="global-deadline", name="Global")
        data = {
            "year": self.year.pk,
            "category": category.pk,
            "title": "Deadline optional",
            "description": "",
            "status": FormDefinition.Status.OPEN,
            "attachment_policy": FormDefinition.AttachmentPolicy.OPTIONAL,
            "opens_at_0": "",
            "opens_at_1": "",
            "closes_at_0": "",
            "closes_at_1": "",
            f"{prefix}-TOTAL_FORMS": "0",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }

        response = self.client.post(add_url, data)
        self.assertEqual(response.status_code, 302)
        form = FormDefinition.objects.get(title="Deadline optional")
        self.assertIsNone(form.closes_at)

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

        with self.assertRaisesMessage(ValidationError, _("Complete your profile before submitting.")):
            self.submit_application()

    def test_required_attachment_policy(self):
        self.form.attachment_policy = FormDefinition.AttachmentPolicy.REQUIRED
        self.form.save()

        with self.assertRaisesMessage(ValidationError, _("At least one attachment is required for this form.")):
            self.submit_application()

        application = self.submit_application(files=[make_image()])
        self.assertEqual(application.attachments.count(), 1)

    def test_no_attachment_policy(self):
        self.form.attachment_policy = FormDefinition.AttachmentPolicy.NONE
        self.form.save()

        with self.assertRaisesMessage(ValidationError, _("This form does not accept attachments.")):
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

        with self.assertRaisesMessage(ValidationError, _("You already have an application for this form.")):
            self.submit_application()

        self.assertEqual(Application.objects.count(), 1)

    def test_application_is_editable_only_while_form_accepts(self):
        application = self.submit_application()
        self.form.status = FormDefinition.Status.IN_REVIEW
        self.form.save()
        application.refresh_from_db()

        with self.assertRaisesMessage(ValidationError, _("This application can no longer be edited.")):
            update_application(application, self.valid_data())
        with self.assertRaisesMessage(ValidationError, _("This application can no longer be edited.")):
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
                with self.assertRaisesMessage(ValidationError, _("Upload a JPG or PNG image.")):
                    self.submit_application(files=[upload])

        self.assertFalse(Application.objects.exists())

    @patch("main.services.applications.MAX_FILE_SIZE", 10)
    def test_per_file_size_limit(self):
        with self.assertRaisesMessage(ValidationError, _("Each file must be 2 MB or smaller.")):
            self.submit_application(files=[make_image()])

    @patch("main.services.applications.MAX_TOTAL_SIZE", 1)
    def test_total_size_limit(self):
        with self.assertRaisesMessage(ValidationError, _("Total attachment size must be 10 MB or smaller.")):
            self.submit_application(files=[make_image()])

    @patch("main.services.applications.MAX_ATTACHMENTS", 1)
    def test_attachment_count_limit(self):
        with self.assertRaisesMessage(ValidationError, _("At most %(limit)s files can be uploaded per application.") % {"limit": 1}):
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

        with self.assertRaisesMessage(ValidationError, _("At least one attachment is required for this form.")):
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

    def test_dashboard_calendar_follows_site_setting(self):
        settings = SiteSettings.load()
        settings.calendar_note = ""
        settings.save(update_fields=["calendar_note"])

        response = self.client.get(reverse("main:home"))
        self.assertNotContains(response, "Takvim")

        settings.calendar_note = "Etkinlik takvimi"
        settings.save(update_fields=["calendar_note"])

        response = self.client.get(reverse("main:home"))
        self.assertContains(response, "Takvim")
        self.assertContains(response, "Etkinlik takvimi")

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

    def test_form_detail_redirects_to_application_form(self):
        response = self.client.get(reverse("main:form_detail", args=[self.form.pk]))

        self.assertRedirects(
            response,
            reverse("main:application_start", args=[self.form.pk]),
        )

    def test_form_detail_redirects_to_existing_application(self):
        application = self.make_application()

        response = self.client.get(reverse("main:form_detail", args=[self.form.pk]))

        self.assertRedirects(
            response,
            reverse("main:application_detail", args=[application.public_id]),
        )

    def test_apply_page_renders_empty_form(self):
        response = self.client.get(
            reverse("main:application_start", args=[self.form.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("application_form", response.context)
        self.assertContains(response, self.title_field.label)
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

        self.assertRedirects(response, reverse("main:form_list"))

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

    def test_applicant_pages_do_not_expose_internal_status(self):
        application = self.make_application()

        for status in Application.Status.values:
            application.status = status
            application.save(update_fields=["status"])

            urls = [
                reverse("main:home"),
                reverse("main:form_list"),
                reverse("main:application_list"),
                reverse("main:application_detail", args=[application.public_id]),
            ]
            if application.is_editable:
                urls.append(
                    reverse("main:application_edit", args=[application.public_id])
                )

            for url in urls:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, f"{status} {url}")
                content = response.content.decode()
                for label in ("Submitted", "In review", "Evaluated"):
                    self.assertNotIn(
                        label, content, f"{label} leaked on {url} ({status})"
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

    def test_preview_redirects_to_edit(self):
        application = self.make_application()

        response = self.client.get(
            reverse("main:application_preview", args=[application.public_id])
        )

        self.assertRedirects(
            response,
            reverse("main:application_edit", args=[application.public_id]),
        )


class JuryTests(MediaTestCase):
    def setUp(self):
        self.applicant = get_user_model().objects.create_user(
            username="applicant",
            email="applicant@example.com",
            password="secret123",
        )
        Profile.objects.create(
            user=self.applicant,
            phone="+90 555 111 22 33",
            city="Ankara",
            institution="Pardus University",
            education_level=Profile.EducationLevel.BACHELOR,
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

    def test_list_shows_average_before_my_review(self):
        Review.objects.create(
            application=self.application,
            juror=self.other_jury,
            score=60,
            completed_at=timezone.now(),
        )
        url = reverse("main:jury_application_list", args=[self.form.pk])

        before = self.client.get(url)
        self.assertEqual(before.context["rows"][0]["average"], 60.0)

        submit_review(self.application, self.jury, score=80)
        after = self.client.get(url)
        self.assertEqual(after.context["rows"][0]["average"], 70.0)

    def test_list_search_by_code(self):
        url = reverse("main:jury_application_list", args=[self.form.pk])

        match = self.client.get(url, {"q": "BUG-2026-00001"})
        no_match = self.client.get(url, {"q": "nothing"})

        self.assertEqual(len(match.context["rows"]), 1)
        self.assertEqual(len(no_match.context["rows"]), 0)

    def test_detail_shows_other_reviews_and_average_before_my_review(self):
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

        before = self.client.get(url)
        self.assertEqual(len(before.context["other_reviews"]), 1)
        self.assertEqual(before.context["other_reviews"][0].note, "Other note")
        self.assertEqual(before.context["other_reviews"][0].juror_name, "jury2")
        self.assertContains(before, "jury2")
        self.assertEqual(before.context["average_score"], 60.0)

        submit_review(self.application, self.jury, score=80)
        after = self.client.get(url)
        self.assertEqual(len(after.context["other_reviews"]), 1)
        self.assertEqual(after.context["average_score"], 70.0)

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

    def test_detail_navigation_follows_current_queue(self):
        newer = self.make_application(code="BUG-2026-00002")
        Application.objects.filter(pk=newer.pk).update(
            submitted_at=timezone.now() + timedelta(minutes=5)
        )
        older = self.make_application(code="BUG-2026-00003")
        Application.objects.filter(pk=older.pk).update(
            submitted_at=timezone.now() - timedelta(minutes=5)
        )

        response = self.client.get(
            reverse(
                "main:jury_application_detail",
                args=[self.application.public_id],
            )
        )

        self.assertEqual(
            response.context["previous_application_id"],
            newer.public_id,
        )
        self.assertEqual(
            response.context["next_application_id"],
            older.public_id,
        )
        self.assertEqual(
            response.content.decode().count('class="jury-detail-nav"'),
            1,
        )

    def test_detail_navigation_keeps_queue_filters(self):
        response = self.client.get(
            reverse(
                "main:jury_application_detail",
                args=[self.application.public_id],
            ),
            {"mine": "pending", "ordering": "submitted_at"},
        )

        self.assertEqual(
            response.context["queue_query"],
            "mine=pending&ordering=submitted_at",
        )

    def test_list_links_keep_filters_for_detail_navigation(self):
        response = self.client.get(
            reverse("main:jury_application_list", args=[self.form.pk]),
            {"mine": "pending", "ordering": "submitted_at"},
        )

        self.assertContains(response, "mine=pending")
        self.assertContains(response, "ordering=submitted_at")

    def test_submit_review_moves_to_next_application(self):
        next_application = self.make_application(code="BUG-2026-00002")
        Application.objects.filter(pk=next_application.pk).update(
            submitted_at=timezone.now() - timedelta(minutes=5)
        )

        response = self.client.post(
            reverse(
                "main:jury_review_submit",
                args=[self.application.public_id],
            )
            + "?mine=pending&ordering=-submitted_at",
            {"score": "90"},
        )

        self.assertRedirects(
            response,
            reverse(
                "main:jury_application_detail",
                args=[next_application.public_id],
            )
            + "?mine=pending&ordering=-submitted_at",
        )

    def test_submit_review_returns_to_list_when_queue_is_finished(self):
        response = self.client.post(
            reverse(
                "main:jury_review_submit",
                args=[self.application.public_id],
            ),
            {"score": "90"},
        )

        self.assertRedirects(
            response,
            reverse("main:jury_application_list", args=[self.form.pk]),
        )
        self.assertTrue(
            Review.objects.filter(
                application=self.application,
                juror=self.jury,
            ).exists()
        )

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
            submit_review(self.application, self.jury, score=101)
        with self.assertRaises(ValidationError):
            submit_review(self.application, self.jury, score="abc")

    def test_scoring_requires_in_review_form(self):
        self.form.status = FormDefinition.Status.OPEN
        self.form.save()

        with self.assertRaises(ValidationError):
            submit_review(self.application, self.jury, score=80)

        self.form.status = FormDefinition.Status.CLOSED
        self.form.save()

        with self.assertRaises(ValidationError):
            submit_review(self.application, self.jury, score=80)

    def test_review_is_updated_not_duplicated(self):
        submit_review(self.application, self.jury, score=50, note="First")
        submit_review(self.application, self.jury, score=70, note="Second")

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
            reverse("main:profile"),
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
        with self.assertRaisesMessage(ValidationError, _("Jury accounts cannot submit applications.")):
            submit_application(self.jury, self.form, {"title": "Nope"})
        with self.assertRaisesMessage(ValidationError, _("Jury accounts cannot submit applications.")):
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
        self.assertEqual(response.context["applicant_name"], _("Hidden applicant"))
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

        self.assertEqual(items["private_note"]["value"], _(MASKED_FIELD_MESSAGE))
        self.assertTrue(items["private_note"]["is_masked"])
        self.assertNotIn("Top secret", values)
        self.assertNotIn("Hidden answer", values)
        self.assertIn("Visible answer", values)


class JuryAPITests(MediaTestCase):
    def setUp(self):
        self.jury = get_user_model().objects.create_user(
            username="api-jury",
            email="api-jury@example.com",
            password="secret123",
        )
        self.jury.groups.add(Group.objects.get(name="jury"))
        self.other_jury = get_user_model().objects.create_user(
            username="api-jury-2",
            email="api-jury-2@example.com",
            password="secret123",
        )
        self.other_jury.groups.add(Group.objects.get(name="jury"))
        self.applicant = get_user_model().objects.create_user(
            username="api-applicant",
            email="api-applicant@example.com",
            password="secret123",
            first_name="Ada",
            last_name="Lovelace",
        )

        self.year = CompetitionYear.objects.create(year=2026)
        self.category = Category.objects.get(slug="bug")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.category,
            title="API form",
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
        self.masked_field = FormField.objects.create(
            form=self.form,
            key="secret",
            label="Secret",
            field_type=FormField.FieldType.SHORT_TEXT,
            review_visibility=FormField.ReviewVisibility.MASKED,
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
            field=self.masked_field,
            value="Hidden answer",
        )

        self.key, self.raw_key = JuryAPIKey.create_key(
            self.jury,
            "CLI key",
            JuryAPIKey.Duration.THIRTY_DAYS,
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_session_auth_is_not_enough(self):
        self.client.force_login(self.jury)

        response = self.client.get(reverse("jury_api_me"))

        self.assertEqual(response.status_code, 401)

    def test_valid_key_returns_identity_and_updates_last_used(self):
        response = self.client.get(reverse("jury_api_me"), **self.auth)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["user"]["username"], "api-jury")
        self.assertEqual(data["api_key"]["name"], "CLI key")
        self.key.refresh_from_db()
        self.assertIsNotNone(self.key.last_used_at)

    def test_invalid_expired_and_revoked_keys_are_rejected(self):
        invalid = {"HTTP_AUTHORIZATION": "Bearer not-a-real-key"}
        self.assertEqual(
            self.client.get(reverse("jury_api_me"), **invalid).status_code,
            401,
        )

        expired = JuryAPIKey.objects.create(
            user=self.jury,
            name="Expired",
            prefix="ptj_expired",
            key_hash=JuryAPIKey.hash_key("expired-key"),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        expired_auth = {"HTTP_AUTHORIZATION": "Bearer expired-key"}
        self.assertEqual(
            self.client.get(reverse("jury_api_me"), **expired_auth).status_code,
            401,
        )

        self.key.revoke()
        self.assertEqual(
            self.client.get(reverse("jury_api_me"), **self.auth).status_code,
            401,
        )

    def test_non_jury_key_is_rejected(self):
        _, raw_key = JuryAPIKey.create_key(
            self.applicant,
            "Applicant key",
            JuryAPIKey.Duration.ONE_DAY,
        )

        response = self.client.get(
            reverse("jury_api_me"),
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )

        self.assertEqual(response.status_code, 401)

    def test_forms_endpoint_lists_jury_forms(self):
        response = self.client.get(reverse("jury_api_forms"), **self.auth)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], self.form.pk)
        self.assertEqual(data[0]["application_count"], 1)
        self.assertEqual(data[0]["my_completed_count"], 0)

    def test_applications_endpoint_filters_by_my_review(self):
        url = reverse("jury_api_applications", args=[self.form.pk])

        all_rows = self.client.get(url, **self.auth).json()
        self.assertEqual(all_rows["count"], 1)
        self.assertEqual(all_rows["results"][0]["code"], "BUG-2026-00001")

        pending = self.client.get(url, {"mine": "pending"}, **self.auth).json()
        self.assertEqual(pending["count"], 1)

        completed = self.client.get(
            url, {"mine": "completed"}, **self.auth
        ).json()
        self.assertEqual(completed["count"], 0)

        submit_review(self.application, self.jury, score=80)

        completed = self.client.get(
            url, {"mine": "completed"}, **self.auth
        ).json()
        self.assertEqual(completed["count"], 1)

    def test_application_detail_masks_identity_and_fields(self):
        self.form.mask_applicant_identity = True
        self.form.save()

        response = self.client.get(
            reverse("jury_api_application", args=[self.application.public_id]),
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["applicant"]["masked"])
        self.assertIsNone(data["applicant"]["email"])
        values = {item["key"]: item["value"] for item in data["answers"]}
        self.assertEqual(values["title"], "Visible answer")
        self.assertIsNone(values["secret"])
        self.assertTrue(data["can_review"])

    def test_review_can_be_created_and_updated(self):
        url = reverse("jury_api_review", args=[self.application.public_id])

        response = self.client.post(
            url,
            data=json.dumps({"score": 90, "note": "Good"}),
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        review = Review.objects.get(application=self.application, juror=self.jury)
        self.assertEqual(review.score, 90)
        self.assertEqual(review.note, "Good")

        response = self.client.post(
            url,
            data=json.dumps({"score": 95, "note": "Updated"}),
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        review.refresh_from_db()
        self.assertEqual(review.score, 95)
        self.assertEqual(review.note, "Updated")

        detail = self.client.get(
            reverse("jury_api_application", args=[self.application.public_id]),
            **self.auth,
        ).json()
        self.assertEqual(detail["my_review"]["score"], 95)

    def test_review_validation_errors_return_400(self):
        url = reverse("jury_api_review", args=[self.application.public_id])

        for payload in ({"note": "No score"}, {"score": 101}):
            with self.subTest(payload=payload):
                response = self.client.post(
                    url,
                    data=json.dumps(payload),
                    content_type="application/json",
                    **self.auth,
                )
                self.assertEqual(response.status_code, 400)

    def test_attachment_download_requires_key(self):
        attachment = Attachment.objects.create(
            application=self.application,
            file=SimpleUploadedFile(
                "attachment.png",
                b"image-bytes",
                content_type="image/png",
            ),
            original_name="attachment.png",
            content_type="image/png",
            size=11,
        )
        url = reverse(
            "jury_api_attachment",
            args=[self.application.public_id, attachment.pk],
        )

        self.assertEqual(self.client.get(url).status_code, 401)
        response = self.client.get(url, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_jury_can_create_and_revoke_key_in_ui(self):
        self.client.force_login(self.jury)

        response = self.client.post(
            reverse("main:jury_api_keys"),
            {"name": "UI key", "duration_days": "7"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        key = JuryAPIKey.objects.get(user=self.jury, name="UI key")
        self.assertContains(response, "UI key")
        match = re.search(
            r'<code id="new-api-key">([^<]+)</code>',
            response.content.decode(),
        )
        self.assertIsNotNone(match)
        raw_key = match.group(1)

        response = self.client.get(reverse("main:jury_api_keys"))
        self.assertNotContains(response, raw_key)

        revoke = self.client.post(
            reverse("main:jury_api_key_revoke", args=[key.pk])
        )
        self.assertRedirects(revoke, reverse("main:jury_api_keys"))
        key.refresh_from_db()
        self.assertIsNotNone(key.revoked_at)

        response = self.client.get(reverse("main:jury_api_keys"))
        self.assertNotContains(response, "UI key")

    def test_expired_key_is_hidden_in_ui(self):
        self.client.force_login(self.jury)
        expired, _ = JuryAPIKey.create_key(
            self.jury,
            "Expired UI",
            JuryAPIKey.Duration.ONE_DAY,
        )
        JuryAPIKey.objects.filter(pk=expired.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        response = self.client.get(reverse("main:jury_api_keys"))

        self.assertNotContains(response, "Expired UI")
        self.assertContains(response, "CLI key")

    def test_juror_cannot_revoke_another_jurors_key(self):
        self.client.force_login(self.other_jury)

        response = self.client.post(
            reverse("main:jury_api_key_revoke", args=[self.key.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.key.refresh_from_db()
        self.assertIsNone(self.key.revoked_at)

    def test_applicant_cannot_access_key_management(self):
        self.client.force_login(self.applicant)

        response = self.client.get(reverse("main:jury_api_keys"))

        self.assertEqual(response.status_code, 403)


class TranslationTests(TestCase):
    def test_service_message_is_translated_in_turkish(self):
        with translation.override("tr"):
            error = ValidationError(
                {"title": [_("This form is not accepting applications.")]}
            )

            self.assertEqual(
                _validation_message(error),
                "Bu form şu anda başvuru kabul etmiyor.",
            )

    def test_service_message_falls_back_to_english(self):
        with translation.override("en"):
            error = ValidationError(
                {"title": [_("This form is not accepting applications.")]}
            )

            self.assertEqual(
                _validation_message(error),
                "This form is not accepting applications.",
            )

    def test_non_field_messages_are_flattened_and_translated(self):
        with translation.override("tr"):
            error = ValidationError(
                _("Jury accounts cannot submit applications.")
            )

            self.assertEqual(
                _validation_message(error),
                "Jüri hesapları başvuru gönderemez.",
            )

    def test_plain_messages_are_not_remapped(self):
        error = ValidationError("Plain message")

        self.assertEqual(_validation_message(error), "Plain message")


class LanguageSwitcherTests(TestCase):
    def test_browser_language_is_ignored_by_default(self):
        response = self.client.get(
            reverse("main:home"),
            HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9",
        )

        self.assertContains(response, "Ana sayfa")
        self.assertNotContains(response, "Home")
        self.assertContains(response, 'class="language-switcher"')
        self.assertContains(response, 'name="language" value="en"')

    def test_language_switcher_sets_and_persists_language(self):
        response = self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("main:home")},
        )

        self.assertRedirects(response, reverse("main:home"))
        self.assertEqual(response.cookies["django_language"].value, "en")

        response = self.client.get(reverse("main:home"))
        self.assertContains(response, "Home")
        self.assertContains(response, "Log in")

        self.client.post(
            reverse("set_language"),
            {"language": "tr", "next": reverse("main:home")},
        )
        response = self.client.get(reverse("main:home"))
        self.assertContains(response, "Ana sayfa")

    def test_invalid_language_cookie_falls_back_to_turkish(self):
        self.client.cookies["django_language"] = "xx"

        response = self.client.get(reverse("main:home"))

        self.assertContains(response, "Ana sayfa")


class AuditWorkflowTests(MediaTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="audit-user",
            email="audit@example.com",
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
        self.category = Category.objects.get(slug="bug")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.category,
            title="Audit form",
            attachment_policy=FormDefinition.AttachmentPolicy.OPTIONAL,
        )
        FormField.objects.create(
            form=self.form,
            key="title",
            label="Title",
            field_type=FormField.FieldType.SHORT_TEXT,
        )

    def submit(self, files=None):
        return submit_application(
            self.user,
            self.form,
            {"title": "Audit application"},
            files=files,
        )

    def test_submission_and_attachment_are_audited(self):
        application = self.submit(files=[make_image()])

        submitted = AuditEvent.objects.get(
            action=AuditEvent.Action.APPLICATION_SUBMITTED
        )
        attached = AuditEvent.objects.get(
            action=AuditEvent.Action.ATTACHMENT_ADDED
        )

        self.assertEqual(submitted.actor, self.user)
        self.assertEqual(submitted.application, application)
        self.assertEqual(submitted.metadata["code"], application.code)
        self.assertEqual(attached.actor, self.user)
        self.assertEqual(attached.metadata["name"], "photo.png")

    def test_update_is_audited(self):
        application = self.submit()

        update_application(application, {"title": "Updated title"})

        event = AuditEvent.objects.get(
            action=AuditEvent.Action.APPLICATION_UPDATED
        )
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.application, application)

    def test_delete_is_audited_and_keeps_metadata(self):
        application = self.submit()
        code = application.code

        delete_application(application)

        event = AuditEvent.objects.get(
            action=AuditEvent.Action.APPLICATION_DELETED
        )
        self.assertIsNone(event.application)
        self.assertEqual(event.metadata["code"], code)
        self.assertEqual(event.actor, self.user)

    def test_attachment_removal_is_audited(self):
        application = self.submit()
        attachment = add_attachment(application, make_image())

        delete_attachment(attachment)

        event = AuditEvent.objects.get(
            action=AuditEvent.Action.ATTACHMENT_REMOVED
        )
        self.assertEqual(event.metadata["name"], "photo.png")


class ReviewAuditTests(MediaTestCase):
    def setUp(self):
        self.jury = get_user_model().objects.create_user(
            username="audit-jury",
            email="audit-jury@example.com",
            password="secret123",
        )
        self.jury.groups.add(Group.objects.get(name="jury"))
        self.applicant = get_user_model().objects.create_user(
            username="audit-applicant",
            email="audit-applicant@example.com",
            password="secret123",
        )
        self.year = CompetitionYear.objects.create(year=2026)
        self.category = Category.objects.get(slug="bug")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.category,
            title="Audit review form",
            status=FormDefinition.Status.IN_REVIEW,
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

    def test_review_submission_is_audited(self):
        submit_review(self.application, self.jury, score=80, note="Good")

        event = AuditEvent.objects.get(action=AuditEvent.Action.REVIEW_SUBMITTED)
        self.assertEqual(event.actor, self.jury)
        self.assertEqual(event.application, self.application)
        self.assertEqual(event.metadata["score"], 80)

    def test_review_edit_audits_previous_score(self):
        submit_review(self.application, self.jury, score=50)
        submit_review(self.application, self.jury, score=70, note="Changed")

        event = AuditEvent.objects.get(action=AuditEvent.Action.REVIEW_UPDATED)
        self.assertEqual(event.metadata["score"], 70)
        self.assertEqual(event.metadata["previous_score"], 50)
        self.assertTrue(event.metadata["note_changed"])


class AdminWorkflowTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="workflow-admin",
            email="workflow-admin@example.com",
            password="secret123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.staff)
        self.year = CompetitionYear.objects.create(year=2026)
        self.category = Category.objects.create(slug="workflow", name="Workflow")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.category,
            title="Workflow form",
        )
        self.applicant = get_user_model().objects.create_user(
            username="workflow-applicant",
            email="workflow-applicant@example.com",
            password="secret123",
        )
        self.application = Application.objects.create(
            applicant=self.applicant,
            form=self.form,
            year=self.year,
            category=self.category,
            status=Application.Status.SUBMITTED,
            code="WORK-2026-00001",
            submitted_at=timezone.now(),
        )

    def test_form_review_action_syncs_applications(self):
        response = self.client.post(
            reverse("admin:main_formdefinition_changelist"),
            {
                "action": "mark_in_review",
                "_selected_action": [str(self.form.pk)],
                "select_across": "0",
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.form.refresh_from_db()
        self.application.refresh_from_db()
        self.assertEqual(self.form.status, FormDefinition.Status.IN_REVIEW)
        self.assertEqual(self.application.status, Application.Status.IN_REVIEW)
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditEvent.Action.FORM_STATUS_CHANGED,
                actor=self.staff,
                form=self.form,
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditEvent.Action.APPLICATION_STATUS_CHANGED,
                actor=self.staff,
                application=self.application,
            ).exists()
        )

    def test_application_bulk_action_marks_evaluated(self):
        self.application.status = Application.Status.IN_REVIEW
        self.application.save(update_fields=["status"])

        response = self.client.post(
            reverse("admin:main_application_changelist"),
            {
                "action": "mark_evaluated",
                "_selected_action": [str(self.application.pk)],
                "select_across": "0",
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.EVALUATED)
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditEvent.Action.APPLICATION_STATUS_CHANGED,
                application=self.application,
                actor=self.staff,
            ).exists()
        )

    def test_editable_status_change_is_audited(self):
        model_admin = ApplicationAdmin(Application, admin_site)
        request = RequestFactory().post("/admin/")
        request.user = self.staff
        self.application.status = Application.Status.IN_REVIEW
        dummy_form = type("DummyForm", (), {"changed_data": ["status"]})()

        model_admin.save_model(request, self.application, dummy_form, change=True)

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.IN_REVIEW)
        event = AuditEvent.objects.get(
            action=AuditEvent.Action.APPLICATION_STATUS_CHANGED,
            application=self.application,
        )
        self.assertEqual(
            event.metadata["old_status"],
            Application.Status.SUBMITTED,
        )
        self.assertEqual(
            event.metadata["new_status"],
            Application.Status.IN_REVIEW,
        )

    def test_csv_export_contains_application_and_average(self):
        Review.objects.create(
            application=self.application,
            juror=self.staff,
            score=80,
            completed_at=timezone.now(),
        )
        model_admin = ApplicationAdmin(Application, admin_site)
        request = RequestFactory().get("/admin/")
        request.user = self.staff

        response = model_admin.export_csv(request, Application.objects.all())
        content = response.content.decode()

        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("code,year,category", content)
        self.assertIn(self.application.code, content)
        self.assertIn("80.0", content)

    def test_audit_admin_is_read_only(self):
        model_admin = AuditEventAdmin(AuditEvent, admin_site)
        request = RequestFactory().get("/admin/")
        request.user = self.staff

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ProtectedMediaTests(MediaTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="media-owner",
            email="media-owner@example.com",
            password="secret123",
        )
        Profile.objects.create(
            user=self.user,
            phone="+90 555 111 22 33",
            city="Ankara",
            institution="Pardus University",
            education_level=Profile.EducationLevel.BACHELOR,
        )
        self.other = get_user_model().objects.create_user(
            username="media-other",
            email="media-other@example.com",
            password="secret123",
        )
        self.jury = get_user_model().objects.create_user(
            username="media-jury",
            email="media-jury@example.com",
            password="secret123",
        )
        self.jury.groups.add(Group.objects.get(name="jury"))
        self.staff = get_user_model().objects.create_user(
            username="media-staff",
            email="media-staff@example.com",
            password="secret123",
            is_staff=True,
        )
        self.year = CompetitionYear.objects.create(year=2026)
        self.category = Category.objects.get(slug="bug")
        self.form = FormDefinition.objects.create(
            year=self.year,
            category=self.category,
            title="Media form",
            attachment_policy=FormDefinition.AttachmentPolicy.OPTIONAL,
        )
        FormField.objects.create(
            form=self.form,
            key="title",
            label="Title",
            field_type=FormField.FieldType.SHORT_TEXT,
        )
        self.application = submit_application(
            self.user,
            self.form,
            {"title": "Media application"},
            files=[make_image()],
        )
        self.attachment = self.application.attachments.get()

    def test_owner_can_download_attachment(self):
        self.client.force_login(self.user)

        response = self.client.get(self.attachment.file.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_other_applicant_cannot_download_attachment(self):
        self.client.force_login(self.other)

        self.assertEqual(self.client.get(self.attachment.file.url).status_code, 404)

    def test_jury_and_staff_can_download_attachment(self):
        for user in (self.jury, self.staff):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get(self.attachment.file.url).status_code,
                    200,
                )

    def test_anonymous_cannot_download_attachment(self):
        self.client.logout()

        self.assertEqual(self.client.get(self.attachment.file.url).status_code, 404)

    def test_unknown_media_path_is_not_found(self):
        self.client.force_login(self.user)

        self.assertEqual(
            self.client.get("/media/applications/2026/missing/file.png").status_code,
            404,
        )

    def test_profile_photo_is_owner_and_staff_only(self):
        profile = self.user.profile
        profile.photo = make_image(name="avatar.png")
        profile.save()
        url = profile.photo.url

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 200)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SiteSettingsTests(TestCase):
    def setUp(self):
        self.settings = SiteSettings.load()
        self.settings.application_status = SiteSettings.ApplicationStatus.OPEN
        self.settings.application_opens_at = None
        self.settings.application_closes_at = None
        self.settings.save()

        self.year = CompetitionYear.objects.create(year=timezone.localdate().year)
        self.category = Category.objects.create(
            slug="settings",
            name="Settings",
            home_description="Home description",
            home_highlights="First\nSecond",
        )

    def make_form(self, **overrides):
        data = {
            "year": self.year,
            "category": self.category,
            "title": "Settings form",
        }
        data.update(overrides)
        return FormDefinition.objects.create(**data)

    def test_load_returns_single_row(self):
        self.assertEqual(SiteSettings.load().pk, self.settings.pk)
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_global_status_controls_form_acceptance(self):
        form = self.make_form()
        self.assertTrue(form.is_accepting_submissions)

        self.settings.application_status = SiteSettings.ApplicationStatus.CLOSED
        self.settings.save()
        self.assertFalse(form.is_accepting_submissions)

    def test_override_ignores_only_global_period(self):
        self.settings.application_status = SiteSettings.ApplicationStatus.CLOSED
        self.settings.save()
        form = self.make_form(submission_override=True)

        self.assertTrue(form.is_accepting_submissions)

        form.closes_at = timezone.now() - timedelta(days=1)
        form.save()
        form.refresh_from_db()
        self.assertFalse(form.is_accepting_submissions)

    def test_closed_form_status_beats_override(self):
        form = self.make_form(
            status=FormDefinition.Status.CLOSED,
            submission_override=True,
        )

        self.assertFalse(form.is_accepting_submissions)

    def test_year_mismatch_blocks_submissions(self):
        other_year = CompetitionYear.objects.create(
            year=timezone.localdate().year + 1
        )
        form = self.make_form(year=other_year, submission_override=True)

        self.assertFalse(form.is_accepting_submissions)

    def test_global_date_window(self):
        now = timezone.now()
        self.settings.application_opens_at = now + timedelta(days=1)
        self.settings.save()
        self.assertFalse(self.settings.is_application_open)

        self.settings.application_opens_at = now - timedelta(days=1)
        self.settings.application_closes_at = now + timedelta(days=1)
        self.settings.save()
        self.assertTrue(self.settings.is_application_open)

        self.settings.application_closes_at = now - timedelta(days=1)
        self.settings.save()
        self.assertFalse(self.settings.is_application_open)

    def test_category_highlights(self):
        self.assertEqual(self.category.highlight_list, ["First", "Second"])

    def test_submission_blocked_by_global_period(self):
        user = get_user_model().objects.create_user(
            username="settings-applicant",
            email="settings-applicant@example.com",
            password="secret123",
        )
        Profile.objects.create(
            user=user,
            phone="+90 555 111 22 33",
            city="Ankara",
            institution="Pardus University",
            education_level=Profile.EducationLevel.BACHELOR,
        )
        form = self.make_form()
        FormField.objects.create(
            form=form,
            key="title",
            label="Title",
            field_type=FormField.FieldType.SHORT_TEXT,
        )
        self.settings.application_status = SiteSettings.ApplicationStatus.CLOSED
        self.settings.save()

        with self.assertRaisesMessage(
            ValidationError,
            _("This form is not accepting applications."),
        ):
            submit_application(user, form, {"title": "Blocked"})

        form.submission_override = True
        form.save()
        application = submit_application(user, form, {"title": "Allowed"})
        self.assertEqual(application.status, Application.Status.SUBMITTED)

    def test_home_uses_settings(self):
        self.settings.hero_title = "Custom hero title"
        self.settings.hero_lead = "Custom hero lead"
        self.settings.announcement = "Custom announcement"
        self.settings.announcement_active = True
        self.settings.footer_tagline = "Custom footer"
        self.settings.save()

        response = self.client.get(reverse("main:home"))

        self.assertContains(response, str(timezone.localdate().year))
        self.assertContains(response, "Custom hero title")
        self.assertContains(response, "Custom hero lead")
        self.assertContains(response, "Custom announcement")
        self.assertContains(response, "Custom footer")
        self.assertContains(response, "Home description")
        self.assertContains(response, "First")
        self.assertContains(response, "Second")

    def test_form_list_shows_only_current_year(self):
        user = get_user_model().objects.create_user(
            username="settings-viewer",
            email="settings-viewer@example.com",
            password="secret123",
        )
        Profile.objects.create(
            user=user,
            phone="+90 555 111 22 33",
            city="Ankara",
            institution="Pardus University",
            education_level=Profile.EducationLevel.BACHELOR,
        )
        other_year = CompetitionYear.objects.create(year=timezone.localdate().year + 1)
        current_form = self.make_form(title="Current year form")
        self.make_form(year=other_year, title="Next year form")
        self.client.force_login(user)

        response = self.client.get(reverse("main:form_list"))

        self.assertIn(current_form, response.context["forms"])
        self.assertNotIn("Next year form", [
            form.title for form in response.context["forms"]
        ])

    def test_admin_singleton(self):
        staff = get_user_model().objects.create_user(
            username="settings-admin",
            email="settings-admin@example.com",
            password="secret123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(staff)
        request = RequestFactory().get("/admin/")
        request.user = staff

        model_admin = SiteSettingsAdmin(SiteSettings, admin_site)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertRedirects(
            self.client.get(reverse("admin:main_sitesettings_changelist")),
            reverse("admin:main_sitesettings_change", args=[self.settings.pk]),
        )
        self.assertEqual(
            self.client.get(
                reverse("admin:main_sitesettings_change", args=[self.settings.pk])
            ).status_code,
            200,
        )

    def test_localized_uses_translation_and_falls_back_to_base(self):
        self.settings.hero_lead = "Base lead"
        self.settings.save()
        SiteSettingsTranslation.objects.update_or_create(
            settings=self.settings,
            language="en",
            defaults={
                "hero_eyebrow": "",
                "hero_title": "English hero",
                "hero_lead": "",
            },
        )

        localized = self.settings.localized("en")

        self.assertEqual(localized["hero_title"], "English hero")
        self.assertEqual(localized["hero_lead"], "Base lead")
        self.assertEqual(
            localized["hero_eyebrow"],
            self.settings.hero_eyebrow,
        )

    def test_home_uses_english_translation(self):
        SiteSettingsTranslation.objects.update_or_create(
            settings=self.settings,
            language="en",
            defaults={
                "hero_title": "English hero",
                "hero_lead": "English lead",
            },
        )
        self.settings.hero_title = "Turkish hero"
        self.settings.hero_lead = "Turkish lead"
        self.settings.save()

        self.client.cookies["django_language"] = "en"
        response = self.client.get(reverse("main:home"))

        self.assertContains(response, "English hero")
        self.assertContains(response, "English lead")
        self.assertNotContains(response, "Turkish hero")

    def test_category_translation_overrides_display(self):
        CategoryTranslation.objects.update_or_create(
            category=self.category,
            language="en",
            defaults={
                "name": "English category",
                "description": "English description",
                "home_description": "English home",
                "home_highlights": "One\nTwo",
            },
        )

        from django.utils import translation

        with translation.override("en"):
            self.assertEqual(self.category.display_name, "English category")
            self.assertEqual(
                self.category.display_description,
                "English description",
            )
            self.assertEqual(
                self.category.display_home_description,
                "English home",
            )
            self.assertEqual(self.category.highlight_list, ["One", "Two"])

    def test_category_translation_falls_back_to_base(self):
        CategoryTranslation.objects.update_or_create(
            category=self.category,
            language="en",
            defaults={
                "name": "",
                "description": "",
                "home_description": "",
                "home_highlights": "",
            },
        )

        from django.utils import translation

        with translation.override("en"):
            self.assertEqual(self.category.display_name, self.category.name)
            self.assertEqual(
                self.category.display_description,
                self.category.description,
            )
            self.assertEqual(
                self.category.highlight_list,
                ["First", "Second"],
            )

    def test_home_uses_category_translation(self):
        CategoryTranslation.objects.update_or_create(
            category=self.category,
            language="en",
            defaults={
                "name": "English category",
                "home_description": "English category description",
            },
        )

        self.client.cookies["django_language"] = "en"
        response = self.client.get(reverse("main:home"))

        self.assertContains(response, "English category")
        self.assertContains(response, "English category description")
