from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """Applicant, jury member or administrator account.

    Keycloak is the source of identity; ``keycloak_id`` stores the OIDC
    ``sub`` claim. Local administrators may leave it empty.
    """

    keycloak_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("Keycloak ID"),
    )
    email = models.EmailField(unique=True)

    def __str__(self) -> str:
        return self.email or self.username


class Profile(models.Model):
    """Personal information an applicant completes after signing in."""

    class EducationLevel(models.TextChoices):
        PRIMARY = "primary", _("Primary school")
        MIDDLE = "middle", _("Middle school")
        HIGH = "high", _("High school")
        ASSOCIATE = "associate", _("Associate degree")
        BACHELOR = "bachelor", _("Bachelor's degree")
        MASTER = "master", _("Master's degree")
        DOCTORATE = "doctorate", _("Doctorate")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("User"),
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name=_("Phone"))
    city = models.CharField(max_length=64, blank=True, verbose_name=_("City"))
    institution = models.CharField(max_length=255, blank=True, verbose_name=_("Institution"))
    education_level = models.CharField(
        max_length=16,
        choices=EducationLevel.choices,
        blank=True,
        verbose_name=_("Education level"),
    )
    photo = models.ImageField(upload_to="profiles/%Y/", blank=True, verbose_name=_("Photo"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    REQUIRED_FIELDS = ("phone", "city", "institution", "education_level")

    def __str__(self) -> str:
        return f"{self.user} profile"

    class Meta:
        verbose_name = _("Profile")
        verbose_name_plural = _("Profiles")

    @property
    def is_complete(self) -> bool:
        return all(getattr(self, field) for field in self.REQUIRED_FIELDS)
