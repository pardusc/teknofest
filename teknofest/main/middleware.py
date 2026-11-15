from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import translation
from django.utils.translation import get_supported_language_variant

from .permissions import is_jury


class DefaultLocaleMiddleware(LocaleMiddleware):
    """Use the site language unless the visitor explicitly picked one.

    Django's stock LocaleMiddleware also negotiates with Accept-Language. That
    makes the UI English for English browsers while the competition content is
    usually authored in Turkish, producing a mixed-language page. Here only an
    explicit language cookie (set by the language switcher) changes the locale.
    """

    def process_request(self, request):
        language = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if language:
            try:
                language = get_supported_language_variant(language)
            except LookupError:
                language = settings.LANGUAGE_CODE
        else:
            language = settings.LANGUAGE_CODE

        translation.activate(language)
        request.LANGUAGE_CODE = translation.get_language()


class ProfileCompletionMiddleware:
    """Send applicants to their profile until all required fields are filled."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = {
            reverse("main:profile"),
            reverse("main:profile_edit"),
            reverse("login"),
            reverse("logout"),
            "/favicon.ico",
        }
        self.exempt_prefixes = (
            "/static/",
            "/media/",
            "/attachments/",
            "/i18n/",
            "/admin/",
            "/jury/",
            "/staff/",
            "/api/",
        )

    def __call__(self, request):
        if self._needs_profile(request):
            return redirect("main:profile")
        return self.get_response(request)

    def _needs_profile(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or is_jury(user):
            return False

        path = request.path_info
        if path in self.exempt_paths or path.startswith(self.exempt_prefixes):
            return False

        profile = getattr(user, "profile", None)
        return profile is None or not profile.is_complete
