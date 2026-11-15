"""Tests for the Keycloak OIDC authentication backend.

The backend methods are exercised directly (no network, no JWKS); only the
``get_or_create_user`` wiring test patches ``get_userinfo``.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import SuspiciousOperation
from django.test import RequestFactory, TestCase, override_settings

from .auth import KeycloakOIDCBackend
from .permissions import JURY_GROUP_NAME

# Minimal settings required by OIDCAuthenticationBackend.__init__.
OIDC_TEST_SETTINGS = {
    "OIDC_OP_TOKEN_ENDPOINT": "https://keycloak.example/realms/test/protocol/openid-connect/token",
    "OIDC_OP_USER_ENDPOINT": "https://keycloak.example/realms/test/protocol/openid-connect/userinfo",
    "OIDC_RP_CLIENT_ID": "teknofest-test",
    "OIDC_RP_CLIENT_SECRET": "test-secret",
    "OIDC_RP_SIGN_ALGO": "HS256",
}


@override_settings(**OIDC_TEST_SETTINGS)
class KeycloakOIDCBackendTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.backend = KeycloakOIDCBackend()
        self.request = RequestFactory().get(
            "/accounts/oidc/callback/", {"code": "code", "state": "state"}
        )
        self.backend.request = self.request

    def claims(self, **overrides):
        claims = {
            "sub": "kc-123",
            "email": "ada@example.com",
            "preferred_username": "Ada.Lovelace",
            "given_name": "Ada",
            "family_name": "Lovelace",
            "groups": [],
        }
        claims.update(overrides)
        return claims

    # -- provisioning ----------------------------------------------------

    def test_create_user_from_new_identity(self):
        user = self.backend.create_user(self.claims())

        self.assertEqual(self.user_model.objects.count(), 1)
        self.assertEqual(user.email, "ada@example.com")
        self.assertEqual(user.username, "ada.lovelace")
        self.assertEqual(user.keycloak_id, "kc-123")
        self.assertEqual(user.first_name, "Ada")
        self.assertEqual(user.last_name, "Lovelace")
        self.assertFalse(user.has_usable_password())

    def test_create_user_sanitises_and_limits_username(self):
        user = self.backend.create_user(
            self.claims(preferred_username="  Ada Lovelace!  ")
        )
        self.assertEqual(user.username, "ada-lovelace")

        long_user = self.backend.create_user(
            self.claims(sub="kc-long", email="long@example.com", preferred_username="A" * 200)
        )
        self.assertEqual(len(long_user.username), 150)

    def test_create_user_falls_back_when_username_is_empty(self):
        user = self.backend.create_user(
            self.claims(
                email="empty@example.com",
                preferred_username="!!!",
                given_name="",
                family_name="",
            )
        )
        self.assertEqual(user.username, "user")

    def test_create_user_falls_back_to_email_local_part(self):
        user = self.backend.create_user(
            self.claims(
                email="local.part@example.com",
                preferred_username="",
                given_name="",
                family_name="",
            )
        )
        self.assertEqual(user.username, "local.part")

    def test_username_collision_gets_numeric_suffix(self):
        self.user_model.objects.create_user(
            username="ada.lovelace", email="someone-else@example.com"
        )

        first = self.backend.create_user(self.claims())
        second = self.backend.create_user(
            self.claims(sub="kc-456", email="grace@example.com")
        )

        self.assertEqual(first.username, "ada.lovelace-2")
        self.assertEqual(second.username, "ada.lovelace-3")

    def test_names_fall_back_to_full_name(self):
        user = self.backend.create_user(
            self.claims(
                email="grace@example.com",
                given_name="",
                family_name="",
                name="Grace Brewster Hopper",
            )
        )
        self.assertEqual(user.first_name, "Grace")
        self.assertEqual(user.last_name, "Brewster Hopper")

    def test_get_username_matches_created_username(self):
        claims = self.claims()
        self.assertEqual(self.backend.get_username(claims), "ada.lovelace")

        self.backend.create_user(claims)
        self.assertEqual(self.backend.get_username(claims), "ada.lovelace-2")

    # -- repeat logins ---------------------------------------------------

    def test_second_login_updates_same_user(self):
        user = self.backend.create_user(self.claims())

        updated = self.backend.update_user(
            user,
            self.claims(
                email="ada.new@example.com",
                preferred_username="augusta",
                given_name="Augusta",
                family_name="King",
            ),
        )

        self.assertEqual(self.user_model.objects.count(), 1)
        self.assertEqual(updated.pk, user.pk)
        self.assertEqual(updated.email, "ada.new@example.com")
        self.assertEqual(updated.first_name, "Augusta")
        self.assertEqual(updated.last_name, "King")
        self.assertEqual(updated.username, "ada.lovelace")
        self.assertFalse(updated.has_usable_password())

        updated.refresh_from_db()
        self.assertEqual(updated.email, "ada.new@example.com")

    def test_filter_users_by_claims_ignores_email(self):
        user = self.backend.create_user(self.claims())

        matches = list(
            self.backend.filter_users_by_claims(
                self.claims(email="changed@example.com")
            )
        )
        self.assertEqual(matches, [user])

        legacy = self.user_model.objects.create_user(
            username="legacy", email="legacy@example.com"
        )
        self.assertEqual(
            list(
                self.backend.filter_users_by_claims(
                    {"sub": "other-sub", "email": legacy.email}
                )
            ),
            [],
        )

    def test_update_user_rejects_email_owned_by_another_account(self):
        user = self.backend.create_user(self.claims())
        self.user_model.objects.create_user(
            username="other", email="taken@example.com"
        )

        with self.assertRaises(SuspiciousOperation):
            self.backend.update_user(user, self.claims(email="taken@example.com"))

    def test_update_user_rejects_relinking_to_another_identity(self):
        user = self.backend.create_user(self.claims())

        with self.assertRaises(SuspiciousOperation):
            self.backend.update_user(user, self.claims(sub="kc-other"))

    # -- legacy accounts -------------------------------------------------

    def test_legacy_local_account_is_attached(self):
        legacy = self.user_model.objects.create_user(
            username="legacy",
            email="legacy@example.com",
            password="secret123",
            first_name="Old",
            last_name="Name",
        )
        self.assertTrue(legacy.has_usable_password())

        user = self.backend.create_user(
            self.claims(email="legacy@example.com", given_name="Ada")
        )

        self.assertEqual(self.user_model.objects.count(), 1)
        self.assertEqual(user.pk, legacy.pk)
        self.assertEqual(user.keycloak_id, "kc-123")
        self.assertEqual(user.username, "legacy")
        self.assertEqual(user.first_name, "Ada")
        self.assertFalse(user.has_usable_password())

    def test_legacy_account_linked_to_another_identity_is_rejected(self):
        self.user_model.objects.create_user(
            username="linked",
            email="linked@example.com",
            keycloak_id="kc-someone-else",
        )

        with self.assertRaises(SuspiciousOperation):
            self.backend.create_user(self.claims(email="linked@example.com"))

    def test_staff_email_collision_raises(self):
        self.user_model.objects.create_user(
            username="admin",
            email="admin@example.com",
            is_staff=True,
        )

        with self.assertRaises(SuspiciousOperation):
            self.backend.create_user(self.claims(email="admin@example.com"))

        self.assertEqual(self.user_model.objects.count(), 1)
        self.assertIsNone(
            self.user_model.objects.get(email="admin@example.com").keycloak_id
        )

    def test_superuser_email_collision_raises(self):
        self.user_model.objects.create_user(
            username="root",
            email="root@example.com",
            is_superuser=True,
        )

        with self.assertRaises(SuspiciousOperation):
            self.backend.create_user(self.claims(email="root@example.com"))

    # -- claims ----------------------------------------------------------

    def test_verify_claims_requires_sub_and_email(self):
        self.assertTrue(self.backend.verify_claims(self.claims()))

        invalid = [
            {"email": "ada@example.com"},
            {"sub": "kc-123"},
            {"sub": "", "email": "ada@example.com"},
            {"sub": "kc-123", "email": ""},
            {"sub": "   ", "email": "ada@example.com"},
            {"sub": "kc-123", "email": "   "},
        ]
        for claims in invalid:
            with self.subTest(claims=claims):
                self.assertFalse(self.backend.verify_claims(claims))

    # -- group sync ------------------------------------------------------

    def test_group_sync_adds_jury_for_short_name(self):
        user = self.backend.create_user(self.claims())

        self.backend.sync_user_groups(user, self.claims(groups=["jury"]))

        self.assertTrue(user.groups.filter(name=JURY_GROUP_NAME).exists())
        self.assertTrue(Group.objects.filter(name=JURY_GROUP_NAME).exists())

    def test_group_sync_accepts_leading_slash_and_mixed_groups(self):
        user = self.backend.create_user(self.claims())

        self.backend.sync_user_groups(user, self.claims(groups=["/jury"]))
        self.assertTrue(user.groups.filter(name=JURY_GROUP_NAME).exists())

        self.backend.sync_user_groups(
            user, self.claims(groups=["/applicants", "/teknofest/jury"])
        )
        self.assertTrue(user.groups.filter(name=JURY_GROUP_NAME).exists())

    def test_group_sync_removes_jury_when_claim_disappears(self):
        user = self.backend.create_user(self.claims())
        self.backend.sync_user_groups(user, self.claims(groups=["jury"]))
        self.assertTrue(user.groups.filter(name=JURY_GROUP_NAME).exists())

        self.backend.sync_user_groups(user, self.claims(groups=["/applicants"]))
        self.assertFalse(user.groups.filter(name=JURY_GROUP_NAME).exists())

        self.backend.sync_user_groups(user, self.claims(groups=[]))
        self.assertFalse(user.groups.filter(name=JURY_GROUP_NAME).exists())

    def test_group_sync_never_sets_staff_flags(self):
        user = self.backend.create_user(self.claims())

        self.backend.sync_user_groups(
            user,
            self.claims(groups=["jury"], is_staff=True, is_superuser=True),
        )

        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_group_sync_runs_during_login_flow(self):
        claims = self.claims(groups=["/jury"])

        with patch.object(self.backend, "get_userinfo", return_value=claims):
            user = self.backend.get_or_create_user("access-token", "id-token", claims)

        self.assertIsNotNone(user)
        self.assertEqual(user.keycloak_id, "kc-123")
        self.assertTrue(user.groups.filter(name=JURY_GROUP_NAME).exists())
        self.assertFalse(user.is_staff)
