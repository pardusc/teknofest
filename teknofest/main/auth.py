"""Keycloak-backed OIDC authentication for the main app.

The project uses ``mozilla-django-oidc`` for the authorization-code flow and
delegates identity matching to this backend. Keycloak (the OIDC ``sub`` claim)
is the source of identity; the local ``email`` column is only used to attach a
pre-existing legacy account the first time a user signs in.
"""

import re
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import SuspiciousOperation
from django.urls import reverse
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from .permissions import JURY_GROUP_NAME

#: Matches the ``username`` max_length of ``AbstractUser``.
USERNAME_MAX_LENGTH = 150

#: Matches the ``first_name``/``last_name`` max_length of ``AbstractUser``.
NAME_MAX_LENGTH = 150

#: Used when neither ``preferred_username`` nor the email local part is usable.
USERNAME_FALLBACK = "user"

#: Characters that are not allowed in a generated username. Runs of them are
#: collapsed into a single dash so "Ada Lovelace!" becomes "ada-lovelace".
_INVALID_USERNAME_CHARS = re.compile(r"[^a-z0-9._-]+")


class KeycloakOIDCBackend(OIDCAuthenticationBackend):
    """Authenticate users by their Keycloak ``sub`` claim.

    Matching is intentionally done on ``keycloak_id`` only. Email is a unique
    field locally, so it is consulted during provisioning as a legacy
    collision safety net, never as an identity match.
    """

    def describe_user_by_claims(self, claims):
        return f"Keycloak sub {claims.get('sub')!r}"

    def verify_claims(self, claims):
        """Require the claims needed to provision an account."""
        sub = str(claims.get("sub") or "").strip()
        email = str(claims.get("email") or "").strip()
        return bool(sub and email)

    def filter_users_by_claims(self, claims):
        """Return users linked to this Keycloak identity, never by email."""
        sub = str(claims.get("sub") or "").strip()
        if not sub:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(keycloak_id=sub)

    def get_username(self, claims):
        """Build a sanitised, unique username from the available claims."""
        return self._unique_username(self._username_base(claims))

    def create_user(self, claims):
        """Provision a local account for a Keycloak identity."""
        sub, email = self._identity_from_claims(claims)

        # Legacy collision safety net: a local account may already own this
        # email. Reusing it keeps the unique email constraint happy and lets
        # existing applicants keep their applications and profile.
        existing = self.UserModel.objects.filter(email__iexact=email).first()
        if existing is not None:
            if existing.is_staff or existing.is_superuser:
                raise SuspiciousOperation(
                    "Refusing to link a Keycloak identity to a staff account."
                )
            if existing.keycloak_id and existing.keycloak_id != sub:
                raise SuspiciousOperation(
                    "Email already belongs to another Keycloak identity."
                )
            return self._apply_claims(existing, claims)

        user = self.UserModel(
            username=self.get_username(claims),
            email=email,
            keycloak_id=sub,
        )
        self._set_names(user, claims)
        user.set_unusable_password()
        user.save()
        return user

    def update_user(self, user, claims):
        """Refresh Keycloak-managed fields on every login.

        The username stays stable so links, logs and audit records keep
        pointing at the same account. No password is granted: Keycloak users
        authenticate through the IdP only.
        """
        sub, email = self._identity_from_claims(claims)

        conflict = (
            self.UserModel.objects.filter(email__iexact=email)
            .exclude(pk=user.pk)
            .first()
        )
        if conflict is not None:
            raise SuspiciousOperation(
                "Refusing to move an account onto an email owned by another user."
            )

        if user.keycloak_id and user.keycloak_id != sub:
            raise SuspiciousOperation(
                "Refusing to relink an account to a different Keycloak identity."
            )

        return self._apply_claims(user, claims)

    def get_or_create_user(self, access_token, id_token, payload):
        """Run the regular mdo flow, then mirror Keycloak group membership.

        ``payload`` is the verified ID token, where Keycloak's group-membership
        mapper emits the ``groups`` claim. This hook has both the user and the
        claims, so it is the safest place to sync roles.
        """
        user = super().get_or_create_user(access_token, id_token, payload)
        if user is not None:
            self.sync_user_groups(user, payload)
        return user

    def sync_user_groups(self, user, claims):
        """Mirror the Keycloak ``jury`` group onto the local group.

        Only ``main.permissions.JURY_GROUP_NAME`` is managed here; other local
        groups are left untouched. Staff/superuser flags are never derived from
        claims.
        """
        group = Group.objects.filter(name=JURY_GROUP_NAME).first()
        if JURY_GROUP_NAME in self._claim_group_names(claims):
            if group is None:
                group = Group.objects.create(name=JURY_GROUP_NAME)
            user.groups.add(group)
        elif group is not None:
            user.groups.remove(group)

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _identity_from_claims(claims):
        sub = str(claims.get("sub") or "").strip()
        email = str(claims.get("email") or "").strip()
        if not sub or not email:
            raise SuspiciousOperation(
                "Keycloak claims must contain a non-empty sub and email."
            )
        return sub, email

    @staticmethod
    def _username_base(claims):
        raw = claims.get("preferred_username")
        if raw is None or not str(raw).strip():
            email = str(claims.get("email") or "").strip()
            raw = email.split("@", 1)[0] if "@" in email else email
        username = _INVALID_USERNAME_CHARS.sub("-", str(raw).lower())
        username = username.strip(".-_")[:USERNAME_MAX_LENGTH]
        return username or USERNAME_FALLBACK

    def _unique_username(self, base):
        base = (base or USERNAME_FALLBACK)[:USERNAME_MAX_LENGTH]
        users = self.UserModel.objects
        if not users.filter(username=base).exists():
            return base

        suffix = 2
        while True:
            suffix_text = f"-{suffix}"
            prefix = base[: USERNAME_MAX_LENGTH - len(suffix_text)]
            candidate = f"{prefix.rstrip('.-_') or USERNAME_FALLBACK}{suffix_text}"
            if not users.filter(username=candidate).exists():
                return candidate
            suffix += 1

    @staticmethod
    def _set_names(user, claims):
        first_name = str(claims.get("given_name") or "").strip()
        last_name = str(claims.get("family_name") or "").strip()

        if not first_name or not last_name:
            name_parts = str(claims.get("name") or "").strip().split()
            if not first_name and name_parts:
                first_name = name_parts.pop(0)
            elif (
                first_name
                and name_parts
                and name_parts[0].lower() == first_name.lower()
            ):
                name_parts.pop(0)
            if not last_name and name_parts:
                last_name = " ".join(name_parts)

        user.first_name = first_name[:NAME_MAX_LENGTH]
        user.last_name = last_name[:NAME_MAX_LENGTH]

    def _apply_claims(self, user, claims):
        """Write the Keycloak-managed fields and persist the user."""
        sub, email = self._identity_from_claims(claims)
        user.keycloak_id = sub
        user.email = email
        self._set_names(user, claims)
        user.set_unusable_password()
        user.save()
        return user

    @staticmethod
    def _claim_group_names(claims):
        """Normalise ``groups`` entries such as ``jury``, ``/jury`` or ``/a/jury``."""
        groups = claims.get("groups") or []
        if isinstance(groups, str):
            groups = [groups]
        elif not isinstance(groups, (list, tuple, set)):
            return set()

        names = set()
        for group in groups:
            if not isinstance(group, str):
                continue
            name = group.strip().strip("/").rsplit("/", 1)[-1].strip().lower()
            if name:
                names.add(name)
        return names


def keycloak_logout_url(request):
    """End the Keycloak SSO session together with the local Django session.

    ``mozilla_django_oidc`` calls this through ``OIDC_OP_LOGOUT_URL_METHOD``.
    Local admin sessions have no ID token, so they keep the normal redirect.
    """
    redirect_url = reverse("main:home")
    id_token = request.session.get("oidc_id_token")
    if not id_token:
        return redirect_url

    params = {
        "id_token_hint": id_token,
        "post_logout_redirect_uri": request.build_absolute_uri(redirect_url),
    }
    return f"{settings.OIDC_OP_LOGOUT_ENDPOINT}?{urlencode(params)}"
