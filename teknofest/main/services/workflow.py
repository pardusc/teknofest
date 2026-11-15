from ..models import Application, AuditEvent
from .audit import record


def set_application_status(application, new_status, actor=None) -> bool:
    """Change an application's status and write an audit event."""
    if application.status == new_status:
        return False

    old_status = application.status
    application.status = new_status
    application.save(update_fields=["status", "updated_at"])

    record(
        AuditEvent.Action.APPLICATION_STATUS_CHANGED,
        actor=actor,
        application=application,
        form=application.form,
        code=application.code,
        old_status=old_status,
        new_status=new_status,
    )
    return True


def sync_form_applications(form, new_status, actor=None) -> int:
    """Move submitted applications of a form to the given status."""
    updated = 0
    applications = form.applications.filter(status=Application.Status.SUBMITTED)
    for application in applications:
        if set_application_status(application, new_status, actor):
            updated += 1
    return updated
