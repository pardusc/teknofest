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
