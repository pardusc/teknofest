from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Immutable record of an important application or review action."""

    class Action(models.TextChoices):
        APPLICATION_SUBMITTED = "application_submitted", "Application submitted"
        APPLICATION_UPDATED = "application_updated", "Application updated"
        APPLICATION_DELETED = "application_deleted", "Application deleted"
        APPLICATION_STATUS_CHANGED = (
            "application_status_changed",
            "Application status changed",
        )
        ATTACHMENT_ADDED = "attachment_added", "Attachment added"
        ATTACHMENT_REMOVED = "attachment_removed", "Attachment removed"
        REVIEW_SUBMITTED = "review_submitted", "Review submitted"
        REVIEW_UPDATED = "review_updated", "Review updated"
        FORM_STATUS_CHANGED = "form_status_changed", "Form status changed"
        API_KEY_CREATED = "api_key_created", "API key created"
        API_KEY_REVOKED = "api_key_revoked", "API key revoked"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    application = models.ForeignKey(
        "Application",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    form = models.ForeignKey(
        "FormDefinition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("application", "created_at")),
            models.Index(fields=("action", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} · {self.created_at:%Y-%m-%d %H:%M}"
