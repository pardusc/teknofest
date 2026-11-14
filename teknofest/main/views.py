from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView, UpdateView

from .dynamic_forms import build_form
from .forms import ProfileForm
from .models import Application, Category, FormDefinition, Profile
from .services import applications as application_service


def home(request):
    return render(request, "main/home.html")


class ProfileView(LoginRequiredMixin, DetailView):
    model = Profile
    template_name = "main/profile_detail.html"
    context_object_name = "profile"

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = Profile
    form_class = ProfileForm
    template_name = "main/profile_edit.html"
    success_url = reverse_lazy("main:profile")

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Profiliniz güncellendi.")
        return response


class FormListView(LoginRequiredMixin, ListView):
    template_name = "main/form_list.html"
    context_object_name = "forms"

    def get_queryset(self):
        return (
            FormDefinition.objects.select_related("year", "category")
            .filter(year__is_active=True, category__is_active=True)
            .order_by("-year__year", "category__order")
        )


class FormDetailView(LoginRequiredMixin, DetailView):
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


class ApplicationStartView(LoginRequiredMixin, View):
    def post(self, request, pk):
        form_definition = get_object_or_404(
            FormDefinition.objects.select_related("year", "category"),
            pk=pk,
        )

        try:
            application = application_service.start_application(
                request.user,
                form_definition,
            )
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
            return redirect("main:form_detail", pk=form_definition.pk)

        messages.success(request, "Başvuru taslağı hazır.")
        return redirect(
            "main:application_edit",
            public_id=application.public_id,
        )


class ApplicationListView(LoginRequiredMixin, ListView):
    template_name = "main/application_list.html"
    context_object_name = "applications"

    def get_queryset(self):
        return Application.objects.select_related("form", "year", "category").filter(
            applicant=self.request.user
        )


class ApplicationDetailView(LoginRequiredMixin, DetailView):
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


class ApplicationUpdateView(LoginRequiredMixin, View):
    template_name = "main/application_edit.html"

    def get(self, request, public_id):
        application = _get_owned_application(request, public_id)
        if not application.is_editable:
            messages.error(request, "Bu başvuru artık düzenlenemez.")
            return redirect(
                "main:application_detail",
                public_id=application.public_id,
            )

        form = build_form(
            application.form,
            initial=_initial_answers(application),
            enforce_required=False,
        )
        return TemplateResponse(
            request,
            self.template_name,
            _edit_context(application, form),
        )

    def post(self, request, public_id):
        application = _get_owned_application(request, public_id)
        if not application.is_editable:
            messages.error(request, "Bu başvuru artık düzenlenemez.")
            return redirect(
                "main:application_detail",
                public_id=application.public_id,
            )

        form = build_form(
            application.form,
            data=request.POST,
            enforce_required=False,
        )
        if not form.is_valid():
            return TemplateResponse(
                request,
                self.template_name,
                _edit_context(application, form),
            )

        try:
            application_service.save_draft(application, request.POST)
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
            return redirect(
                "main:application_edit",
                public_id=application.public_id,
            )

        messages.success(request, "Taslak kaydedildi.")
        return redirect(
            "main:application_detail",
            public_id=application.public_id,
        )


class ApplicationPreviewView(LoginRequiredMixin, DetailView):
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


class ApplicationSubmitView(LoginRequiredMixin, View):
    def post(self, request, public_id):
        application = _get_owned_application(request, public_id)

        try:
            result = application_service.submit(application)
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
            return redirect(
                "main:application_edit",
                public_id=application.public_id,
            )

        messages.success(
            request,
            f"Başvurunuz alındı. Başvuru kodunuz: {result.code}",
        )
        return redirect(
            "main:application_detail",
            public_id=result.public_id,
        )


class ApplicationDeleteView(LoginRequiredMixin, View):
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

        messages.success(request, "Başvuru silindi.")
        return redirect("main:application_list")


class AttachmentUploadView(LoginRequiredMixin, View):
    def post(self, request, public_id):
        application = _get_owned_application(request, public_id)
        upload = request.FILES.get("file")

        if upload is None:
            messages.error(request, "Yüklenecek bir dosya seçin.")
            return redirect(
                "main:application_edit",
                public_id=application.public_id,
            )

        try:
            application_service.add_attachment(application, upload)
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
        else:
            messages.success(request, "Dosya yüklendi.")

        return redirect(
            "main:application_edit",
            public_id=application.public_id,
        )


class AttachmentDeleteView(LoginRequiredMixin, View):
    def post(self, request, public_id, pk):
        application = _get_owned_application(request, public_id)
        attachment = get_object_or_404(application.attachments, pk=pk)

        try:
            application_service.delete_attachment(attachment)
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
        else:
            messages.success(request, "Dosya silindi.")

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
    return [
        {"field": field, "value": answers.get(field.pk, "")}
        for field in application.form.fields.filter(is_active=True)
    ]


def _initial_answers(application):
    return {
        answer.field.key: answer.value
        for answer in application.answers.select_related("field")
        if answer.field.is_active
    }


def _edit_context(application, application_form):
    return {
        "application": application,
        "application_form": application_form,
        "attachments": application.attachments.all(),
        "attachment_policy": application.category.attachment_policy,
        "can_add_attachment": (
            application.is_editable
            and application.category.attachment_policy
            != Category.AttachmentPolicy.NONE
        ),
    }


def _validation_message(error):
    if hasattr(error, "message_dict"):
        texts = []
        for field_messages in error.message_dict.values():
            texts.extend(field_messages)
        return " ".join(texts)
    return " ".join(error.messages)
