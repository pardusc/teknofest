from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.translation import gettext as _

JURY_GROUP_NAME = "jury"


def is_jury(user) -> bool:
    """Admins are jurors as well; other jurors belong to the jury group."""
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or user.groups.filter(name=JURY_GROUP_NAME).exists()


class JuryRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return is_jury(self.request.user)

    def handle_no_permission(self):
        # Anonymous users go to the login page; authenticated non-jurors get 403.
        if self.request.user.is_authenticated:
            raise PermissionDenied
        return super().handle_no_permission()


class ApplicantOnlyMixin(LoginRequiredMixin):
    """Applicant and profile pages are closed to jury and admin accounts."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and is_jury(request.user):
            messages.error(request, _("Jury accounts cannot apply."))
            return redirect("main:jury_dashboard")
        return super().dispatch(request, *args, **kwargs)
