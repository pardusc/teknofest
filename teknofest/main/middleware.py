from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.utils import translation
from django.utils.translation import get_supported_language_variant


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
