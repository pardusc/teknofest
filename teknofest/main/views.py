from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count, Exists, FloatField, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop
from django.views import View
from django.views.generic import DetailView, ListView, UpdateView

from .dynamic_forms import build_form
from .forms import ProfileForm
from .models import Application, FormDefinition, FormField, Profile, Review
from .permissions import ApplicantOnlyMixin, JuryRequiredMixin
from .services import applications as application_service
from .services import reviews as review_service
from .services.reviews import review_stats


def home(request):
    return render(request, "main/home.html")


class ProfileView(ApplicantOnlyMixin, DetailView):
    model = Profile
    template_name = "main/profile_detail.html"
    context_object_name = "profile"

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile


class ProfileUpdateView(ApplicantOnlyMixin, UpdateView):
    model = Profile
    form_class = ProfileForm
    template_name = "main/profile_edit.html"
    success_url = reverse_lazy("main:profile")

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Your profile has been updated."))
        return response


class FormListView(ApplicantOnlyMixin, ListView):
    template_name = "main/form_list.html"
    context_object_name = "forms"

    def get_queryset(self):
        return (
            FormDefinition.objects.select_related("year", "category")
            .filter(year__is_active=True, category__is_active=True)
            .order_by("-year__year", "category__order")
        )


class FormDetailView(ApplicantOnlyMixin, DetailView):
    model = FormDefinition
    template_name = "main/form_detail.html"
    context_object_name = "form_definition"

    def get_queryset(self):
        return FormDefinition.objects.select_related("year", "category").filter(
            year__is_active=True,
            category__is_active=True,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form_definition = self.object
        existing = Application.objects.filter(
            applicant=self.request.user,
            form=form_definition,
        ).first()

        context.update(
            {
                "fields": form_definition.fields.filter(is_active=True),
                "existing_application": existing,
                "can_apply": (
                    form_definition.is_accepting_submissions and existing is None
                ),
            }
        )
        return context


class ApplicationStartView(ApplicantOnlyMixin, View):
    template_name = "main/application_form.html"

    def get(self, request, pk):
        form_definition = get_object_or_404(
            FormDefinition.objects.select_related("year", "category"),
            pk=pk,
        )
        if not form_definition.is_accepting_submissions:
            messages.error(request, _("This form is not accepting applications."))
            return redirect("main:form_detail", pk=form_definition.pk)

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
        return Application.objects.select_related("form", "year", "category").filter(
            applicant=self.request.user
        )


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
    template_name = "main/application_edit.html"

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
            _edit_context(application, form),
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
                _edit_context(application, form),
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
                _edit_context(application, form),
            )

        messages.success(request, _("Your application has been updated."))
        return redirect(
            "main:application_detail",
            public_id=application.public_id,
        )


class ApplicationPreviewView(ApplicantOnlyMixin, DetailView):
    model = Application
    template_name = "main/application_preview.html"
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
            }
        )
        return context


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


def _edit_context(application, application_form):
    policy = application.form.attachment_policy
    return {
        "application": application,
        "application_form": application_form,
        "required_keys": set(
            application.form.fields.filter(is_active=True, is_required=True)
            .values_list("key", flat=True)
        ),
        "attachments": application.attachments.all(),
        "attachment_policy": policy,
        "accepts_files": policy != FormDefinition.AttachmentPolicy.NONE,
        "can_add_attachment": (
            application.is_editable
            and policy != FormDefinition.AttachmentPolicy.NONE
        ),
    }


def _application_form_context(form_definition, application_form):
    policy = form_definition.attachment_policy
    return {
        "form_definition": form_definition,
        "application_form": application_form,
        "required_keys": set(
            form_definition.fields.filter(is_active=True, is_required=True)
            .values_list("key", flat=True)
        ),
        "attachments": [],
        "attachment_policy": policy,
        "accepts_files": policy != FormDefinition.AttachmentPolicy.NONE,
        "can_add_attachment": False,
    }


def _validation_message(error):
    if hasattr(error, "message_dict"):
        return " ".join(
            str(message)
            for field_messages in error.message_dict.values()
            for message in field_messages
        )
    return " ".join(str(message) for message in error.messages)


REVIEWABLE_APPLICATION_STATUSES = (
    Application.Status.SUBMITTED,
    Application.Status.IN_REVIEW,
    Application.Status.EVALUATED,
)

REVIEW_ORDERING = {
    "submitted_at",
    "-submitted_at",
    "my_score",
    "-my_score",
    "average",
    "-average",
}


class JuryDashboardView(JuryRequiredMixin, ListView):
    template_name = "jury/dashboard.html"
    context_object_name = "forms"

    def get_queryset(self):
        user = self.request.user
        return (
            FormDefinition.objects.select_related("year", "category")
            .filter(year__is_active=True, category__is_active=True)
            .annotate(
                application_count=Count(
                    "applications",
                    filter=Q(
                        applications__status__in=REVIEWABLE_APPLICATION_STATUSES
                    ),
                    distinct=True,
                ),
                my_completed_count=Count(
                    "applications__reviews",
                    filter=Q(
                        applications__reviews__juror=user,
                        applications__reviews__completed_at__isnull=False,
                    ),
                    distinct=True,
                ),
            )
            .order_by("-year__year", "category__order")
        )


class JuryApplicationListView(JuryRequiredMixin, ListView):
    template_name = "jury/application_list.html"
    context_object_name = "applications"
    paginate_by = 20

    def get_queryset(self):
        self.form_definition = get_object_or_404(
            FormDefinition.objects.select_related("year", "category"),
            pk=self.kwargs["pk"],
        )

        my_reviews = Review.objects.filter(
            application=OuterRef("pk"),
            juror=self.request.user,
        )
        average_reviews = (
            Review.objects.filter(
                application=OuterRef("pk"),
                completed_at__isnull=False,
            )
            .values("application")
            .annotate(value=Avg("score"))
            .values("value")
        )

        queryset = (
            Application.objects.select_related("form", "year", "category")
            .filter(
                form=self.form_definition,
                status__in=REVIEWABLE_APPLICATION_STATUSES,
            )
            .annotate(
                my_score=Subquery(my_reviews.values("score")[:1]),
                my_completed=Exists(
                    my_reviews.filter(completed_at__isnull=False)
                ),
                average=Subquery(average_reviews, output_field=FloatField()),
                attachment_count=Count("attachments", distinct=True),
            )
        )

        mine = self.request.GET.get("mine")
        if mine == "completed":
            queryset = queryset.filter(my_completed=True)
        elif mine == "pending":
            queryset = queryset.filter(my_completed=False)

        if self.request.GET.get("files") == "1":
            queryset = queryset.filter(attachment_count__gt=0)

        query = self.request.GET.get("q", "").strip()
        if query:
            conditions = Q(code__icontains=query)
            if not self.form_definition.mask_applicant_identity:
                conditions |= Q(applicant__email__icontains=query)
            queryset = queryset.filter(conditions)

        ordering = self.request.GET.get("ordering", "-submitted_at")
        if ordering not in REVIEW_ORDERING:
            ordering = "-submitted_at"
        return queryset.order_by(ordering)

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
                "average": application.average if application.my_completed else None,
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
            }
        )
        return context


class JuryReviewSaveView(JuryRequiredMixin, View):
    def post(self, request, public_id):
        application = _get_reviewable_application(request, public_id)

        try:
            review_service.save_review(
                application,
                request.user,
                score=request.POST.get("score"),
                note=request.POST.get("note", ""),
            )
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
        else:
            messages.success(request, _("Review draft saved."))

        return redirect(
            "main:jury_application_detail",
            public_id=application.public_id,
        )


class JuryReviewSubmitView(JuryRequiredMixin, View):
    def post(self, request, public_id):
        application = _get_reviewable_application(request, public_id)

        try:
            review_service.submit_review(
                application,
                request.user,
                score=request.POST.get("score"),
                note=request.POST.get("note", ""),
            )
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
        else:
            messages.success(request, _("Review submitted."))

        return redirect(
            "main:jury_application_detail",
            public_id=application.public_id,
        )


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
