import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import Profile


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
