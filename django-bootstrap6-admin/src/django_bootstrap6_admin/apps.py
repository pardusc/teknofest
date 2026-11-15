from django.apps import AppConfig


class Bootstrap6AdminConfig(AppConfig):
    """Application config for the Bootstrap 6 admin skin.

    The app contains no models and does not monkey-patch Django. It only
    provides admin templates and static assets.
    """

    name = "django_bootstrap6_admin"
    verbose_name = "Bootstrap 6 Admin"
    default_auto_field = "django.db.models.BigAutoField"
