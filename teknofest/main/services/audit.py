from ..models import AuditEvent


def record(
    action,
    *,
    actor=None,
    application=None,
    form=None,
    **metadata,
) -> AuditEvent:
    return AuditEvent.objects.create(
        action=action,
        actor=actor,
        application=application,
        form=form,
        metadata=metadata,
    )
