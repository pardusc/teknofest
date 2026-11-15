from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Immutable record of an important application or review action."""

    class Action(models.TextChoices):
        APPLICATION_SUBMITTED = "application_submitted", "Başvuru gönderildi"
        APPLICATION_UPDATED = "application_updated", "Başvuru güncellendi"
        APPLICATION_DELETED = "application_deleted", "Başvuru silindi"
        APPLICATION_STATUS_CHANGED = (
            "application_status_changed",
            "Başvuru durumu değişti",
        )
        ATTACHMENT_ADDED = "attachment_added", "Ek dosya eklendi"
        ATTACHMENT_REMOVED = "attachment_removed", "Ek dosya kaldırıldı"
        REVIEW_SUBMITTED = "review_submitted", "Değerlendirme gönderildi"
        REVIEW_UPDATED = "review_updated", "Değerlendirme güncellendi"
        FORM_STATUS_CHANGED = "form_status_changed", "Form durumu değişti"
        API_KEY_CREATED = "api_key_created", "API anahtarı oluşturuldu"
        API_KEY_REVOKED = "api_key_revoked", "API anahtarı iptal edildi"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        verbose_name="İşlemi yapan",
    )
    application = models.ForeignKey(
        "Application",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        verbose_name="Başvuru",
    )
    form = models.ForeignKey(
        "FormDefinition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        verbose_name="Form",
    )
    action = models.CharField(
        max_length=32,
        choices=Action.choices,
        verbose_name="İşlem",
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Meta veri")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Denetim kaydı"
        verbose_name_plural = "Denetim kayıtları"
        indexes = [
            models.Index(fields=("application", "created_at")),
            models.Index(fields=("action", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} · {self.created_at:%Y-%m-%d %H:%M}"
