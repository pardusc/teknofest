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
        PRIMARY = "primary", "İlkokul"
        MIDDLE = "middle", "Ortaokul"
        HIGH = "high", "Lise"
        ASSOCIATE = "associate", "Ön lisans"
        BACHELOR = "bachelor", "Lisans"
        MASTER = "master", "Yüksek lisans"
        DOCTORATE = "doctorate", "Doktora"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Kullanıcı",
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    city = models.CharField(max_length=64, blank=True, verbose_name="Şehir")
    institution = models.CharField(max_length=255, blank=True, verbose_name="Kurum")
    education_level = models.CharField(
        max_length=16,
        choices=EducationLevel.choices,
        blank=True,
        verbose_name="Eğitim seviyesi",
    )
    photo = models.ImageField(upload_to="profiles/%Y/", blank=True, verbose_name="Fotoğraf")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Son güncelleme")

    REQUIRED_FIELDS = ("phone", "city", "institution", "education_level")

    def __str__(self) -> str:
        return f"{self.user} profile"

    class Meta:
        verbose_name = "Profil"
        verbose_name_plural = "Profiller"

    @property
    def is_complete(self) -> bool:
        return all(getattr(self, field) for field in self.REQUIRED_FIELDS)
