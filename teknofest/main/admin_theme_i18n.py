"""Message ids that only the vendored admin theme templates use.

``django-bootstrap6-admin`` ships its templates inside ``site-packages``,
outside the directory tree that ``makemessages`` scans.  Django's core
admin catalogs already translate the shared strings; the ones below are
unique to the theme, so listing them here keeps them in the project's
catalog and available to the template translation layer.

The module is never imported at runtime; ``gettext_noop`` only marks the
strings for extraction.
"""

from django.utils.translation import gettext_noop

ADMIN_THEME_MESSAGES = (
    gettext_noop("Account access"),
    gettext_noop("Back to dashboard"),
    gettext_noop("By %(filter_title)s"),
    gettext_noop("Clear search and filters"),
    gettext_noop("Close filters"),
    gettext_noop("Close navigation"),
    gettext_noop("Confirm deletion"),
    gettext_noop("Control permissions"),
    gettext_noop("Enter your administrator credentials to continue."),
    gettext_noop("Manage your data"),
    gettext_noop("Navigation"),
    gettext_noop("No results found."),
    gettext_noop("Page %(page)s of %(total)s"),
    gettext_noop("Password changed"),
    gettext_noop("Powered by Django"),
    gettext_noop("Server Error"),
    gettext_noop("Sign in to manage content, users and site settings."),
    gettext_noop("Toggle theme"),
    gettext_noop("Track recent activity"),
    gettext_noop("User menu"),
    gettext_noop("ago"),
)
