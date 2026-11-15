import mimetypes
import os
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.exceptions import SuspiciousFileOperation, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils._os import safe_join
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop
from django.views import View
from django.views.generic import DetailView, ListView, RedirectView, UpdateView

from .dynamic_forms import build_form
from .forms import JuryAPIKeyForm, ProfileForm
from .models import (
    Application,
    Attachment,
    AuditEvent,
    Category,
    FormDefinition,
    FormField,
    JuryAPIKey,
    Profile,
    SiteSettings,
)
from .permissions import ApplicantOnlyMixin, JuryRequiredMixin, is_jury
from .services import applications as application_service
from .services import audit as audit_service
from .services import reviews as review_service
from .services.jury import (
    REVIEWABLE_APPLICATION_STATUSES,
    jury_application_queue,
    jury_application_queryset,
    jury_form_queryset,
)
from .services.reviews import review_stats


def home(request):
    categories = Category.objects.filter(is_active=True).order_by("order", "name")
    return render(
        request,
        "main/home.html",
        {
            "home_categories": categories,
        },
    )


class ProfileView(ApplicantOnlyMixin, UpdateView):
    model = Profile
    form_class = ProfileForm
    template_name = "main/profile.html"
    success_url = reverse_lazy("main:profile")

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Your profile has been updated."))
        return response


class ProfileUpdateView(ApplicantOnlyMixin, RedirectView):
    pattern_name = "main:profile"
    permanent = False


class FormListView(ApplicantOnlyMixin, RedirectView):
    """Legacy URL: forms are now listed on the My Applications page."""

    pattern_name = "main:application_list"
    permanent = False


class FormDetailView(ApplicantOnlyMixin, View):
    """Legacy URL: send applicants straight into the form or their application."""

    def get(self, request, pk):
        settings = SiteSettings.load()
        form_definition = get_object_or_404(
            FormDefinition.objects.select_related("year", "category"),
            pk=pk,
            year__year=settings.current_year,
            category__is_active=True,
        )

        existing = Application.objects.filter(
            applicant=request.user,
            form=form_definition,
        ).first()
        if existing:
            return redirect(
                "main:application_detail",
                public_id=existing.public_id,
            )
        if form_definition.is_accepting_submissions:
            return redirect("main:application_start", pk=form_definition.pk)

        messages.error(request, _("This form is not accepting applications."))
        return redirect("main:application_list")


class ApplicationStartView(ApplicantOnlyMixin, View):
    template_name = "main/application_form.html"

    def get(self, request, pk):
        form_definition = get_object_or_404(
            FormDefinition.objects.select_related("year", "category"),
            pk=pk,
        )
        if not form_definition.is_accepting_submissions:
            messages.error(request, _("This form is not accepting applications."))
            return redirect("main:application_list")

        existing = Application.objects.filter(
            applicant=request.user,
            form=form_definition,
        ).first()
        if existing:
            return redirect(
                "main:application_detail",
                public_id=existing.public_id,
            )

        dynamic_form = build_form(form_definition)
        return TemplateResponse(
            request,
            self.template_name,
            _application_form_context(form_definition, dynamic_form),
        )

    def post(self, request, pk):
        form_definition = get_object_or_404(
            FormDefinition.objects.select_related("year", "category"),
            pk=pk,
        )

        try:
            application = application_service.submit_application(
                request.user,
                form_definition,
                request.POST,
                files=request.FILES.getlist("files"),
            )
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
            dynamic_form = build_form(form_definition, data=request.POST)
            return TemplateResponse(
                request,
                self.template_name,
                _application_form_context(form_definition, dynamic_form),
            )

        messages.success(
            request,
            _("Your application has been received. Application code: %(code)s")
            % {"code": application.code},
        )
        return redirect(
            "main:application_detail",
            public_id=application.public_id,
        )


class ApplicationListView(ApplicantOnlyMixin, ListView):
    template_name = "main/application_list.html"
    context_object_name = "applications"

    def get_queryset(self):
        return (
            Application.objects.select_related("form", "year", "category")
            .filter(applicant=self.request.user)
            .order_by("-updated_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings = SiteSettings.load()
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        applications = list(context["applications"])
        current_forms = list(
            FormDefinition.objects.select_related("year", "category")
            .filter(
                year__year=settings.current_year,
                category__is_active=True,
            )
            .order_by("category__order")
        )
        applications_by_form = {
            application.form_id: application for application in applications
        }
        context.update(
            {
                "profile": profile,
                "continue_application": applications[0] if applications else None,
                "form_rows": [
                    {
                        "form": form,
                        "application": applications_by_form.get(form.pk),
                    }
                    for form in current_forms
                ],
                "open_form_count": sum(
                    1 for form in current_forms if form.is_accepting_submissions
                ),
            }
        )
        return context


class ApplicationDetailView(ApplicantOnlyMixin, DetailView):
    model = Application
    template_name = "main/application_detail.html"
    context_object_name = "application"

    def get_queryset(self):
        return Application.objects.select_related("form", "year", "category").filter(
            applicant=self.request.user
        )

    def get_object(self, queryset=None):
        return _get_owned_application(self.request, self.kwargs["public_id"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "field_answers": _field_answers(self.object),
                "attachments": self.object.attachments.all(),
                "can_edit": self.object.is_editable,
            }
        )
        return context


class ApplicationUpdateView(ApplicantOnlyMixin, View):
    template_name = "main/application_form.html"

    def get(self, request, public_id):
        application = _get_owned_application(request, public_id)
        if not application.is_editable:
            messages.error(request, _("This application can no longer be edited."))
            return redirect(
                "main:application_detail",
                public_id=application.public_id,
            )

        form = build_form(
            application.form,
            initial=_initial_answers(application),
        )
        return TemplateResponse(
            request,
            self.template_name,
            _application_form_context(application.form, form, application),
        )

    def post(self, request, public_id):
        application = _get_owned_application(request, public_id)
        if not application.is_editable:
            messages.error(request, _("This application can no longer be edited."))
            return redirect(
                "main:application_detail",
                public_id=application.public_id,
            )

        form = build_form(application.form, data=request.POST)
        if not form.is_valid():
            return TemplateResponse(
                request,
                self.template_name,
                _application_form_context(application.form, form, application),
            )

        try:
            application_service.update_application(
                application,
                request.POST,
                files=request.FILES.getlist("files"),
            )
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
            return TemplateResponse(
                request,
                self.template_name,
                _application_form_context(application.form, form, application),
            )

        messages.success(request, _("Your application has been updated."))
        return redirect(
            "main:application_detail",
            public_id=application.public_id,
        )


class ApplicationPreviewView(ApplicantOnlyMixin, View):
    """The dedicated preview page was removed; keep old links working."""

    def get(self, request, public_id):
        application = _get_owned_application(request, public_id)
        return redirect(
            "main:application_edit",
            public_id=application.public_id,
        )


class ApplicationDeleteView(ApplicantOnlyMixin, View):
    def post(self, request, public_id):
        application = _get_owned_application(request, public_id)

        try:
            application_service.delete_application(application)
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
            return redirect(
                "main:application_detail",
                public_id=application.public_id,
            )

        messages.success(request, _("Application deleted."))
        return redirect("main:application_list")


class AttachmentUploadView(ApplicantOnlyMixin, View):
    def post(self, request, public_id):
        application = _get_owned_application(request, public_id)
        upload = request.FILES.get("file")

        if upload is None:
            messages.error(request, _("Choose a file to upload."))
            return redirect(
                "main:application_edit",
                public_id=application.public_id,
            )

        try:
            application_service.add_attachment(application, upload)
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
        else:
            messages.success(request, _("File uploaded."))

        return redirect(
            "main:application_edit",
            public_id=application.public_id,
        )


class AttachmentDeleteView(ApplicantOnlyMixin, View):
    def post(self, request, public_id, pk):
        application = _get_owned_application(request, public_id)
        attachment = get_object_or_404(application.attachments, pk=pk)

        try:
            application_service.delete_attachment(attachment)
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
        else:
            messages.success(request, _("File deleted."))

        return redirect(
            "main:application_edit",
            public_id=application.public_id,
        )


@staff_member_required
def form_preview(request, pk):
    definition = get_object_or_404(FormDefinition, pk=pk)
    return render(
        request,
        "main/form_preview.html",
        {"definition": definition, "form": build_form(definition)},
    )


def _get_owned_application(request, public_id):
    return get_object_or_404(
        Application.objects.select_related("form", "year", "category").filter(
            applicant=request.user
        ),
        public_id=public_id,
    )


def _field_answers(application):
    answers = {
        answer.field_id: answer.value
        for answer in application.answers.select_related("field")
    }
    result = []
    for field in application.form.fields.filter(is_active=True):
        value = answers.get(field.pk, "")
        result.append(
            {
                "field": field,
                "value": value,
                "display_value": ", ".join(map(str, value))
                if isinstance(value, list)
                else value,
            }
        )
    return result


def _initial_answers(application):
    return {
        answer.field.key: answer.value
        for answer in application.answers.select_related("field")
        if answer.field.is_active
    }


def _application_form_context(form_definition, application_form, application=None):
    policy = form_definition.attachment_policy
    return {
        "form_definition": form_definition,
        "application": application,
        "application_form": application_form,
        "required_keys": set(
            form_definition.fields.filter(is_active=True, is_required=True)
            .values_list("key", flat=True)
        ),
        "attachments": application.attachments.all() if application else [],
        "attachment_policy": policy,
        "accepts_files": policy != FormDefinition.AttachmentPolicy.NONE,
        "can_add_attachment": bool(
            application
            and application.is_editable
            and policy != FormDefinition.AttachmentPolicy.NONE
        ),
    }


def _validation_message(error):
    if hasattr(error, "message_dict"):
        return " ".join(
            str(message)
            for field_messages in error.message_dict.values()
            for message in field_messages
        )
    return " ".join(str(message) for message in error.messages)


class JuryDashboardView(JuryRequiredMixin, ListView):
    template_name = "jury/dashboard.html"
    context_object_name = "forms"

    def get_queryset(self):
        return jury_form_queryset(self.request.user)


class JuryApplicationListView(JuryRequiredMixin, ListView):
    template_name = "jury/application_list.html"
    context_object_name = "applications"
    paginate_by = 20

    def get_queryset(self):
        self.form_definition = get_object_or_404(
            FormDefinition.objects.select_related("year", "category"),
            pk=self.kwargs["pk"],
        )
        return jury_application_queryset(
            self.form_definition,
            self.request.user,
            self.request.GET,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page_query = self.request.GET.copy()
        page_query.pop("page", None)
        context["page_query"] = page_query.urlencode()
        context["form_definition"] = self.form_definition
        context["rows"] = [
            {
                "application": application,
                "my_score": application.my_score,
                "average": application.average,
                "my_completed": application.my_completed,
                "attachment_count": application.attachment_count,
            }
            for application in context["applications"]
        ]
        return context


class JuryApplicationDetailView(JuryRequiredMixin, DetailView):
    template_name = "jury/application_detail.html"
    context_object_name = "application"

    def get_queryset(self):
        return Application.objects.select_related("form", "year", "category", "applicant").filter(
            status__in=REVIEWABLE_APPLICATION_STATUSES
        )

    def get_object(self, queryset=None):
        return get_object_or_404(
            self.get_queryset(),
            public_id=self.kwargs["public_id"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application = self.object
        applicant = application.applicant
        masked = application.form.mask_applicant_identity

        queue = jury_application_queue(
            application.form,
            self.request.user,
            self.request.GET,
        )
        try:
            index = queue.index(application.public_id)
        except ValueError:
            previous_id = next_id = None
        else:
            previous_id = queue[index - 1] if index > 0 else None
            next_id = queue[index + 1] if index + 1 < len(queue) else None

        context.update(review_stats(application, self.request.user))
        context.update(
            {
                "form_definition": application.form,
                "field_answers": _review_field_answers(application),
                "attachments": application.attachments.all(),
                "can_review": (
                    application.form.status == FormDefinition.Status.IN_REVIEW
                ),
                "applicant_identity_masked": masked,
                "applicant_name": (
                    _("Hidden applicant")
                    if masked
                    else (applicant.get_full_name() or applicant.username)
                ),
                "applicant_email": None if masked else applicant.email,
                "previous_application_id": previous_id,
                "next_application_id": next_id,
                "queue_query": self.request.GET.urlencode(),
            }
        )
        return context


class JuryReviewSubmitView(JuryRequiredMixin, View):
    def post(self, request, public_id):
        application = _get_reviewable_application(request, public_id)
        queue = jury_application_queue(
            application.form,
            request.user,
            request.GET,
        )
        try:
            index = queue.index(application.public_id)
        except ValueError:
            in_queue = False
            next_id = None
        else:
            in_queue = True
            next_id = queue[index + 1] if index + 1 < len(queue) else None

        try:
            review_service.submit_review(
                application,
                request.user,
                score=request.POST.get("score"),
                note=request.POST.get("note", ""),
            )
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
            return redirect(
                _with_query(
                    reverse(
                        "main:jury_application_detail",
                        args=[application.public_id],
                    ),
                    request.GET.urlencode(),
                )
            )

        messages.success(request, _("Review submitted."))
        if next_id:
            return redirect(
                _with_query(
                    reverse(
                        "main:jury_application_detail",
                        args=[next_id],
                    ),
                    request.GET.urlencode(),
                )
            )

        if in_queue:
            messages.info(request, _("No more applications in this queue."))
        return redirect(
            _with_query(
                reverse(
                    "main:jury_application_list",
                    args=[application.form_id],
                ),
                request.GET.urlencode(),
            )
        )


def _with_query(url, query):
    return f"{url}?{query}" if query else url


class JuryAPIKeyListView(JuryRequiredMixin, ListView):
    template_name = "jury/api_keys.html"
    context_object_name = "api_keys"

    def get_queryset(self):
        return self.request.user.jury_api_keys.filter(
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("form", JuryAPIKeyForm())
        context.setdefault("new_key", None)

        token = self.request.GET.get("reveal")
        if token:
            cache_key = f"jury-api-key-reveal:{self.request.user.pk}:{token}"
            new_key = cache.get(cache_key)
            cache.delete(cache_key)
            if not new_key:
                new_key = self.request.session.pop("new_jury_api_key", None)
            else:
                self.request.session.pop("new_jury_api_key", None)
            context["new_key"] = new_key
        return context

    def post(self, request, *args, **kwargs):
        form = JuryAPIKeyForm(request.POST)
        if form.is_valid():
            key, raw_key = JuryAPIKey.create_key(
                request.user,
                form.cleaned_data["name"],
                form.cleaned_data["duration_days"],
            )
            audit_service.record(
                AuditEvent.Action.API_KEY_CREATED,
                actor=request.user,
                name=key.name,
                prefix=key.prefix,
                expires_at=key.expires_at.isoformat(),
            )
            token = secrets.token_urlsafe(16)
            request.session["new_jury_api_key"] = raw_key
            cache.set(
                f"jury-api-key-reveal:{request.user.pk}:{token}",
                raw_key,
                timeout=120,
            )
            return redirect(f"{reverse('main:jury_api_keys')}?reveal={token}")
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))


class JuryAPIKeyRevokeView(JuryRequiredMixin, View):
    def post(self, request, pk):
        key = get_object_or_404(JuryAPIKey, pk=pk, user=request.user)
        key.revoke()
        audit_service.record(
            AuditEvent.Action.API_KEY_REVOKED,
            actor=request.user,
            name=key.name,
            prefix=key.prefix,
        )
        messages.success(request, _("API key revoked."))
        return redirect("main:jury_api_keys")


def _get_reviewable_application(request, public_id):
    return get_object_or_404(
        Application.objects.select_related("form", "year", "category", "applicant").filter(
            status__in=REVIEWABLE_APPLICATION_STATUSES
        ),
        public_id=public_id,
    )


MASKED_FIELD_MESSAGE = gettext_noop("This field is hidden from jury review.")


def _review_field_answers(application):
    fields = application.form.fields.filter(
        review_visibility__in=[
            FormField.ReviewVisibility.VISIBLE,
            FormField.ReviewVisibility.MASKED,
        ]
    )
    answers = {
        answer.field_id: answer.value
        for answer in application.answers.filter(
            field__review_visibility=FormField.ReviewVisibility.VISIBLE
        ).select_related("field")
    }
    items = []
    for field in fields:
        if field.review_visibility == FormField.ReviewVisibility.MASKED:
            items.append(
                {
                    "field": field,
                    "value": _(MASKED_FIELD_MESSAGE),
                    "display_value": _(MASKED_FIELD_MESSAGE),
                    "is_masked": True,
                }
            )
        else:
            items.append(
                {
                    "field": field,
                    "value": answers.get(field.pk, ""),
                    "display_value": ", ".join(map(str, answers[field.pk]))
                    if isinstance(answers.get(field.pk, ""), list)
                    else answers.get(field.pk, ""),
                    "is_masked": False,
                }
            )
    return items


def protected_media(request, path):
    """Serve uploaded files only to users allowed to see them."""
    user = request.user
    if not user.is_authenticated:
        raise Http404

    try:
        full_path = safe_join(str(settings.MEDIA_ROOT), path)
    except (SuspiciousFileOperation, ValueError, OSError):
        raise Http404

    if not os.path.isfile(full_path):
        raise Http404

    attachment = (
        Attachment.objects.select_related("application").filter(file=path).first()
    )
    if attachment:
        if not (
            attachment.application.applicant_id == user.pk or is_jury(user)
        ):
            raise Http404
        return _media_response(
            attachment.file,
            attachment.original_name,
            attachment.content_type,
        )

    profile = Profile.objects.filter(photo=path).first()
    if profile:
        if not (profile.user_id == user.pk or user.is_staff):
            raise Http404
        return _media_response(
            profile.photo,
            os.path.basename(profile.photo.name),
            None,
        )

    raise Http404


def _media_response(field_file, filename, content_type):
    if content_type is None:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    response = FileResponse(
        field_file.open("rb"),
        content_type=content_type,
        filename=filename,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
