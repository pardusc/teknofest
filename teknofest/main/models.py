from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


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
        verbose_name="Keycloak ID",
    )
    email = models.EmailField(unique=True)

    def __str__(self) -> str:
        return self.email or self.username


class Profile(models.Model):
    """Personal information an applicant completes after signing in."""

    class EducationLevel(models.TextChoices):
        PRIMARY = "primary", "Primary school"
        MIDDLE = "middle", "Middle school"
        HIGH = "high", "High school"
        ASSOCIATE = "associate", "Associate degree"
        BACHELOR = "bachelor", "Bachelor's degree"
        MASTER = "master", "Master's degree"
        DOCTORATE = "doctorate", "Doctorate"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    phone = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=64, blank=True)
    institution = models.CharField(max_length=255, blank=True)
    education_level = models.CharField(
        max_length=16,
        choices=EducationLevel.choices,
        blank=True,
    )
    photo = models.ImageField(upload_to="profiles/%Y/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_FIELDS = ("phone", "city", "institution", "education_level")

    def __str__(self) -> str:
        return f"{self.user} profile"

    @property
    def is_complete(self) -> bool:
        return all(getattr(self, field) for field in self.REQUIRED_FIELDS)
