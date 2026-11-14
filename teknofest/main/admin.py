from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm
from django.urls import reverse
from django.utils.html import format_html

from .forms import FormFieldAdminForm
from .models import (
    Application,
    ApplicationAnswer,
    Attachment,
    Category,
    CompetitionYear,
    FormDefinition,
    FormField,
    Profile,
    User,
)


class UserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class ProfileInline(admin.StackedInline):
    model = Profile
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
    list_display = ("user", "city", "institution", "education_level", "updated_at")
    list_filter = ("education_level",)
    search_fields = ("user__username", "user__email", "city", "institution")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CompetitionYear)
class CompetitionYearAdmin(admin.ModelAdmin):
    list_display = ("year", "is_active", "created_at")
    list_filter = ("is_active",)
    ordering = ("-year",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "code_prefix", "attachment_policy", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("is_active", "attachment_policy")
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
        ("order", "is_active", "is_visible_in_review"),
    )


@admin.register(FormDefinition)
class FormDefinitionAdmin(admin.ModelAdmin):
    inlines = (FormFieldInline,)
    list_display = (
        "year",
        "category",
        "status",
        "opens_at",
        "closes_at",
        "preview_link",
    )
    list_filter = ("status", "year", "category")
    search_fields = ("title", "description")
    actions = ("mark_open", "mark_in_review", "mark_closed")

    @admin.display(description="Preview")
    def preview_link(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("main:form_preview", args=[obj.pk])
        return format_html('<a href="{}">Preview</a>', url)

    @admin.action(description="Mark selected forms as open")
    def mark_open(self, request, queryset):
        updated = queryset.update(status=FormDefinition.Status.OPEN)
        self.message_user(request, f"{updated} form(s) marked as open.")

    @admin.action(description="Put selected forms in review")
    def mark_in_review(self, request, queryset):
        updated = queryset.update(status=FormDefinition.Status.IN_REVIEW)
        self.message_user(request, f"{updated} form(s) put in review.")

    @admin.action(description="Close selected forms")
    def mark_closed(self, request, queryset):
        updated = queryset.update(status=FormDefinition.Status.CLOSED)
        self.message_user(request, f"{updated} form(s) closed.")


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
        "is_visible_in_review",
    )
    list_filter = (
        "field_type",
        "is_active",
        "is_visible_in_review",
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
