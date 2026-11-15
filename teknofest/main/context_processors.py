from .permissions import is_jury


def account_navigation(request):
    """Expose the account area that should be shown in the shared navigation."""
    return {"is_jury_member": is_jury(getattr(request, "user", None))}
