import csv

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from .forms import FormDefinitionAdminForm, FormFieldAdminForm, ProfileAdminForm
from .models import (
    Application,
    ApplicationAnswer,
    Attachment,
    AuditEvent,
    Category,
    CategoryTranslation,
    CompetitionYear,
    FormDefinition,
    FormField,
    JuryAPIKey,
    Profile,
    Review,
    SiteSettings,
    SiteSettingsTranslation,
    User,
)
from .services import audit, workflow


class UserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class ProfileInline(admin.StackedInline):
    model = Profile
    form = ProfileAdminForm
    can_delete = False
    extra = 0
    fields = ("phone", "city", "institution", "education_level", "photo")
    readonly_fields = ("created_at", "updated_at")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    inlines = (ProfileInline,)
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Keycloak", {"fields": ("keycloak_id",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
    )
    list_display = ("username", "email", "first_name", "last_name", "is_staff")
    search_fields = ("username", "first_name", "last_name", "email", "keycloak_id")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    form = ProfileAdminForm
    list_display = ("user", "city", "institution", "education_level", "updated_at")
    list_filter = ("education_level",)
    search_fields = ("user__username", "user__email", "city", "institution")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CompetitionYear)
class CompetitionYearAdmin(admin.ModelAdmin):
    list_display = ("year", "is_active", "created_at")
    list_filter = ("is_active",)
    ordering = ("-year",)


class CategoryTranslationInline(admin.StackedInline):
    model = CategoryTranslation
    extra = 0
    fields = ("language", "name", "description", "home_description", "home_highlights")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    inlines = (CategoryTranslationInline,)
    list_display = ("name", "slug", "code_prefix", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


class FormFieldInline(admin.StackedInline):
    model = FormField
    form = FormFieldAdminForm
    extra = 0
    can_delete = True
    fields = (
        "key",
        "label",
        "field_type",
        "help_text",
        "is_required",
        ("min_length", "max_length"),
        "regex",
        "regex_error_message",
        "choices_text",
        ("order", "is_active", "review_visibility"),
    )


@admin.register(FormDefinition)
class FormDefinitionAdmin(admin.ModelAdmin):
    form = FormDefinitionAdminForm
    inlines = (FormFieldInline,)
    fields = (
        "category",
        "title",
        "description",
        "status",
        "mask_applicant_identity",
        "attachment_policy",
        "submission_override",
        "opens_at",
        "closes_at",
    )
    list_display = (
        "category",
        "status",
        "attachment_policy",
        "submission_override",
        "opens_at",
        "closes_at",
        "preview_link",
    )
    list_filter = ("status", "category")
    search_fields = ("title", "description")
    actions = ("mark_open", "mark_in_review", "mark_closed")

    def save_model(self, request, obj, form, change):
        if not obj.year_id:
            obj.year = CompetitionYear.current()
        super().save_model(request, obj, form, change)

    @admin.display(description="Preview")
    def preview_link(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("main:form_preview", args=[obj.pk])
        return format_html('<a href="{}">Preview</a>', url)

    def _change_form_status(self, request, queryset, status):
        changed = 0
        synced = 0
        for form in queryset:
            if form.status == status:
                continue
            old_status = form.status
            form.status = status
            form.save(update_fields=["status", "updated_at"])
            audit.record(
                AuditEvent.Action.FORM_STATUS_CHANGED,
                actor=request.user,
                form=form,
                old_status=old_status,
                new_status=status,
            )
            changed += 1
            if status == FormDefinition.Status.IN_REVIEW:
                synced += workflow.sync_form_applications(
                    form,
                    Application.Status.IN_REVIEW,
                    request.user,
                )
        return changed, synced

    @admin.action(description="Mark selected forms as open")
    def mark_open(self, request, queryset):
        changed, _ = self._change_form_status(
            request, queryset, FormDefinition.Status.OPEN
        )
        self.message_user(request, f"{changed} form(s) marked as open.")

    @admin.action(description="Put selected forms in review")
    def mark_in_review(self, request, queryset):
        changed, synced = self._change_form_status(
            request, queryset, FormDefinition.Status.IN_REVIEW
        )
        self.message_user(
            request,
            f"{changed} form(s) put in review; {synced} application(s) synced.",
        )

    @admin.action(description="Close selected forms")
    def mark_closed(self, request, queryset):
        changed, _ = self._change_form_status(
            request, queryset, FormDefinition.Status.CLOSED
        )
        self.message_user(request, f"{changed} form(s) closed.")


@admin.register(FormField)
class FormFieldAdmin(admin.ModelAdmin):
    form = FormFieldAdminForm
    list_display = (
        "label",
        "key",
        "form",
        "field_type",
        "is_required",
        "order",
        "is_active",
        "review_visibility",
    )
    list_filter = (
        "field_type",
        "is_active",
        "review_visibility",
        "form__year",
        "form__category",
    )
    search_fields = ("label", "key", "form__title")
    ordering = ("form", "order")


class ApplicationAnswerInline(admin.TabularInline):
    model = ApplicationAnswer
    extra = 0
    can_delete = False
    fields = ("field", "value")
    readonly_fields = fields


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    can_delete = False
    fields = ("original_name", "content_type", "size", "uploaded_at", "file")
    readonly_fields = fields


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    inlines = (ApplicationAnswerInline, AttachmentInline)
    list_display = ("code", "applicant", "category", "year", "status", "submitted_at")
    list_filter = ("status", "category", "year", "form")
    search_fields = ("code", "applicant__email", "applicant__username")
    readonly_fields = (
        "public_id",
        "code",
        "applicant",
        "form",
        "year",
        "category",
        "submitted_at",
        "created_at",
        "updated_at",
    )
    actions = ("start_review", "mark_evaluated", "reopen", "export_csv")

    def save_model(self, request, obj, form, change):
        old_status = None
        if change and "status" in form.changed_data:
            old_status = (
                Application.objects.filter(pk=obj.pk)
                .values_list("status", flat=True)
                .first()
            )

        super().save_model(request, obj, form, change)

        if old_status and old_status != obj.status:
            audit.record(
                AuditEvent.Action.APPLICATION_STATUS_CHANGED,
                actor=request.user,
                application=obj,
                form=obj.form,
                code=obj.code,
                old_status=old_status,
                new_status=obj.status,
            )

    def _set_status(self, request, queryset, status):
        changed = sum(
            workflow.set_application_status(application, status, request.user)
            for application in queryset
        )
        self.message_user(
            request,
            f"{changed} application(s) updated to {status}.",
        )

    @admin.action(description="Start review")
    def start_review(self, request, queryset):
        self._set_status(request, queryset, Application.Status.IN_REVIEW)

    @admin.action(description="Mark evaluated")
    def mark_evaluated(self, request, queryset):
        self._set_status(request, queryset, Application.Status.EVALUATED)

    @admin.action(description="Reopen for review")
    def reopen(self, request, queryset):
        self._set_status(request, queryset, Application.Status.IN_REVIEW)

    @admin.action(description="Export selected applications as CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="applications.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "code",
                "year",
                "category",
                "form",
                "applicant_email",
                "status",
                "submitted_at",
                "average_score",
                "review_count",
                "attachment_count",
            ]
        )

        applications = queryset.select_related(
            "applicant", "form", "year", "category"
        ).prefetch_related("reviews", "attachments")
        for application in applications:
            reviews = list(application.reviews.all())
            scores = [review.score for review in reviews if review.score is not None]
            average = round(sum(scores) / len(scores), 1) if scores else ""
            writer.writerow(
                [
                    application.code or "",
                    application.year.year,
                    application.category.name,
                    application.form.title,
                    application.applicant.email,
                    application.get_status_display(),
                    application.submitted_at.isoformat()
                    if application.submitted_at
                    else "",
                    average,
                    len(reviews),
                    len(list(application.attachments.all())),
                ]
            )

        return response


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("application", "juror", "score", "completed_at", "updated_at")
    list_filter = ("completed_at", "juror")
    search_fields = ("application__code", "juror__email", "juror__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(JuryAPIKey)
class JuryAPIKeyAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "name",
        "prefix",
        "status_display",
        "created_at",
        "expires_at",
        "last_used_at",
    )
    list_filter = ("created_at", "expires_at", "revoked_at")
    search_fields = ("user__username", "user__email", "name", "prefix")
    readonly_fields = (
        "user",
        "name",
        "prefix",
        "key_hash",
        "created_at",
        "expires_at",
        "revoked_at",
        "last_used_at",
    )
    actions = ("revoke_keys",)

    def has_add_permission(self, request):
        return False

    @admin.display(description="Status")
    def status_display(self, obj):
        return obj.status

    @admin.action(description="Revoke selected API keys")
    def revoke_keys(self, request, queryset):
        revoked = 0
        for key in queryset.filter(revoked_at__isnull=True):
            key.revoke()
            audit.record(
                AuditEvent.Action.API_KEY_REVOKED,
                actor=request.user,
                name=key.name,
                prefix=key.prefix,
            )
            revoked += 1
        self.message_user(request, f"{revoked} API key(s) revoked.")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "application", "form")
    list_filter = ("action", "created_at")
    search_fields = ("actor__email", "application__code", "form__title")
    list_select_related = ("actor", "application", "form")
    readonly_fields = ("actor", "application", "form", "action", "metadata", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SiteSettingsTranslationInline(admin.StackedInline):
    model = SiteSettingsTranslation
    extra = 0
    fields = (
        "language",
        "hero_eyebrow",
        "hero_title",
        "hero_lead",
        "announcement",
        "calendar_note",
        "footer_tagline",
    )


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    inlines = (SiteSettingsTranslationInline,)
    fieldsets = (
        (
            "General",
            {
                "fields": (
                    "site_title",
                    "competition_name",
                    "contact_email",
                    "footer_tagline",
                )
            },
        ),
        (
            "Application period",
            {
                "fields": (
                    "application_status",
                    "application_opens_at",
                    "application_closes_at",
                )
            },
        ),
        (
            "Home page",
            {
                "fields": (
                    "hero_eyebrow",
                    "hero_title",
                    "hero_lead",
                    "announcement_active",
                    "announcement",
                    "calendar_note",
                )
            },
        ),
        ("Meta", {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = SiteSettings.load()
        return HttpResponseRedirect(
            reverse("admin:main_sitesettings_change", args=[obj.pk])
        )
