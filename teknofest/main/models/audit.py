from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditEvent(models.Model):
    """Immutable record of an important application or review action."""

    class Action(models.TextChoices):
        APPLICATION_SUBMITTED = "application_submitted", _("Application submitted")
        APPLICATION_UPDATED = "application_updated", _("Application updated")
        APPLICATION_DELETED = "application_deleted", _("Application deleted")
        APPLICATION_STATUS_CHANGED = (
            "application_status_changed",
            _("Application status changed"),
        )
        ATTACHMENT_ADDED = "attachment_added", _("Attachment added")
        ATTACHMENT_REMOVED = "attachment_removed", _("Attachment removed")
        REVIEW_SUBMITTED = "review_submitted", _("Review submitted")
        REVIEW_UPDATED = "review_updated", _("Review updated")
        FORM_STATUS_CHANGED = "form_status_changed", _("Form status changed")
        API_KEY_CREATED = "api_key_created", _("API key created")
        API_KEY_REVOKED = "api_key_revoked", _("API key revoked")

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        verbose_name=_("Actor"),
    )
    application = models.ForeignKey(
        "Application",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        verbose_name=_("Application"),
    )
    form = models.ForeignKey(
        "FormDefinition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        verbose_name=_("Form"),
    )
    action = models.CharField(
        max_length=32,
        choices=Action.choices,
        verbose_name=_("Action"),
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_("Metadata"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = _("Audit event")
        verbose_name_plural = _("Audit events")
        indexes = [
            models.Index(fields=("application", "created_at")),
            models.Index(fields=("action", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} · {self.created_at:%Y-%m-%d %H:%M}"
