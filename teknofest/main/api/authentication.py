from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from ..models import JuryAPIKey
from ..permissions import is_jury


class JuryAPIKeyAuthentication(BaseAuthentication):
    """Authenticate jury API requests using a personal bearer key."""

    keyword = b"bearer"

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if header[0].lower() != self.keyword:
            return None
        if len(header) != 2:
            raise AuthenticationFailed(_("Invalid Authorization header."))

        try:
            raw_key = header[1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed(_("Invalid API key.")) from exc

        key = (
            JuryAPIKey.objects.select_related("user")
            .filter(key_hash=JuryAPIKey.hash_key(raw_key))
            .first()
        )
        if key is None or not key.is_active:
            raise AuthenticationFailed(_("Invalid or expired API key."))
        if not key.user.is_active or not is_jury(key.user):
            raise AuthenticationFailed(_("This API key does not have jury access."))

        now = timezone.now()
        if key.last_used_at is None or now - key.last_used_at > timedelta(minutes=1):
            key.last_used_at = now
            JuryAPIKey.objects.filter(pk=key.pk).update(last_used_at=now)

        return key.user, key

    def authenticate_header(self, request):
        return "Bearer"
