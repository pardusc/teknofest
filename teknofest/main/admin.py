import csv

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

admin.site.site_header = _("Pardus Teknofest Administration")
admin.site.site_title = "Pardus Teknofest"
admin.site.index_title = _("Administration")

ADMIN_FIELD_LABELS = {
    "user": "Kullanıcı",
    "phone": "Telefon",
    "city": "Şehir",
    "institution": "Kurum",
    "education_level": "Eğitim seviyesi",
    "photo": "Fotoğraf",
    "name": "Ad",
    "prefix": "Ön ek",
    "key_hash": "Anahtar özeti",
    "created_at": "Oluşturulma",
    "expires_at": "Bitiş",
    "revoked_at": "İptal edilme",
    "last_used_at": "Son kullanım",
    "public_id": "Genel kimlik",
    "code": "Kod",
    "applicant": "Başvuru sahibi",
    "form": "Form",
    "year": "Yıl",
    "category": "Kategori",
    "status": "Durum",
    "submitted_at": "Gönderilme",
    "updated_at": "Son güncelleme",
    "application": "Başvuru",
    "field": "Alan",
    "value": "Değer",
    "file": "Dosya",
    "original_name": "Özgün ad",
    "content_type": "İçerik türü",
    "size": "Boyut",
    "uploaded_at": "Yüklenme",
    "last_number": "Son numara",
    "actor": "İşlemi yapan",
    "action": "İşlem",
    "metadata": "Meta veri",
    "is_active": "Etkin",
    "slug": "Kısa ad",
    "description": "Açıklama",
    "home_description": "Ana sayfa açıklaması",
    "home_highlights": "Ana sayfa maddeleri",
    "code_prefix": "Kod ön eki",
    "order": "Sıra",
    "language": "Dil",
    "title": "Başlık",
    "mask_applicant_identity": "Başvuru sahibi kimliğini gizle",
    "attachment_policy": "Ek dosya politikası",
    "submission_override": "Gönderim istisnası",
    "opens_at": "Açılış",
    "closes_at": "Kapanış",
    "key": "Anahtar",
    "label": "Etiket",
    "field_type": "Alan türü",
    "short_description": "Kısa açıklama",
    "placeholder": "Yer tutucu",
    "help_text": "Yardım metni",
    "is_required": "Zorunlu",
    "min_length": "En az uzunluk",
    "max_length": "En fazla uzunluk",
    "regex": "Düzenli ifade",
    "regex_error_message": "Düzenli ifade hata mesajı",
    "choices": "Seçenekler",
    "review_visibility": "İnceleme görünürlüğü",
    "juror": "Jüri üyesi",
    "score": "Puan",
    "note": "Not",
    "completed_at": "Tamamlanma",
    "site_title": "Site başlığı",
    "competition_name": "Yarışma adı",
    "application_status": "Başvuru durumu",
    "application_opens_at": "Başvuru açılışı",
    "application_closes_at": "Başvuru kapanışı",
    "hero_eyebrow": "Hero üst etiketi",
    "hero_title": "Hero başlığı",
    "hero_lead": "Hero açıklaması",
    "announcement": "Duyuru",
    "announcement_active": "Duyuru etkin",
    "calendar_note": "Takvim notu",
    "contact_email": "İletişim e-postası",
    "footer_tagline": "Alt bilgi sloganı",
    "settings": "Ayarlar",
}

ADMIN_CHOICE_LABELS = {
    "Application submitted": "Başvuru gönderildi",
    "Application updated": "Başvuru güncellendi",
    "Application deleted": "Başvuru silindi",
    "Application status changed": "Başvuru durumu değişti",
    "Attachment added": "Ek dosya eklendi",
    "Attachment removed": "Ek dosya kaldırıldı",
    "Review submitted": "Değerlendirme gönderildi",
    "Review updated": "Değerlendirme güncellendi",
    "Form status changed": "Form durumu değişti",
    "API key created": "API anahtarı oluşturuldu",
    "API key revoked": "API anahtarı iptal edildi",
    "Submitted": "Gönderildi",
    "In review": "İncelemede",
    "Evaluated": "Değerlendirildi",
    "Open": "Açık",
    "Closed": "Kapalı",
    "Upcoming": "Yaklaşan",
    "No attachments": "Ek dosya yok",
    "Optional": "İsteğe bağlı",
    "Required": "Zorunlu",
    "Short text": "Kısa metin",
    "Long text": "Uzun metin",
    "Markdown": "Markdown",
    "Single choice": "Tek seçim",
    "Multiple choice": "Çoklu seçim",
    "Number": "Sayı",
    "E-mail": "E-posta",
    "URL": "URL",
    "Yes / No": "Evet / Hayır",
    "Date": "Tarih",
    "Visible": "Görünür",
    "Masked": "Gizli",
    "Hidden": "Gizli",
}

ADMIN_HELP_TEXT_LABELS = {
    "Assigned when the application is submitted.": (
        "Başvuru gönderildiğinde atanır."
    ),
    "One item per line, shown on the home page.": (
        "Ana sayfada gösterilecek maddeler, her satıra bir tane."
    ),
    "Prefix used in application codes, for example BUG.": (
        "Başvuru kodlarında kullanılan ön ek, örneğin BUG."
    ),
    "Hide the applicant's name and e-mail from the jury.": (
        "Başvuru sahibinin adını ve e-postasını jüriden gizle."
    ),
    "Allow submissions even when the global application period is closed. "
    "The form's own dates still apply.": (
        "Genel başvuru dönemi kapalı olsa bile başvuru kabul et. "
        "Formun kendi tarihleri yine uygulanır."
    ),
    "Identifier used in submitted data, for example steps_to_reproduce.": (
        "Gönderilen veride kullanılan tanımlayıcı, örneğin steps_to_reproduce."
    ),
    "Optional regular expression the answer must match.": (
        "Yanıtın uyması gereken isteğe bağlı düzenli ifade."
    ),
    'List of objects like {"value": "low", "label": "Low"}.': (
        '{"value": "low", "label": "Low"} gibi nesnelerden oluşan liste.'
    ),
    "What the jury can see for this field.": (
        "Jürinin bu alanda neleri görebileceği."
    ),
    "Shown under the question title.": (
        "Soru başlığının altında gösterilir."
    ),
    "Hint shown inside empty text fields. "
    "Leave blank to use a default hint.": (
        "Boş metin alanlarında gösterilen ipucu. "
        "Varsayılan ipucu için boş bırakın."
    ),
}


def _apply_admin_labels(fields):
    for name, field in fields.items():
        label = ADMIN_FIELD_LABELS.get(name)
        if label:
            field.label = label
        if (
            not isinstance(field, forms.ModelChoiceField)
            and getattr(field, "choices", None)
        ):
            field.choices = [
                (value, ADMIN_CHOICE_LABELS.get(str(choice), choice))
                for value, choice in field.choices
            ]
        if field.help_text:
            field.help_text = ADMIN_HELP_TEXT_LABELS.get(
                str(field.help_text),
                field.help_text,
            )


class AdminFieldLabelsMixin:
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        _apply_admin_labels(form.base_fields)
        return form


class AdminFormsetLabelsMixin:
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        _apply_admin_labels(formset.form.base_fields)
        return formset

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


class ProfileInline(AdminFormsetLabelsMixin, admin.StackedInline):
    model = Profile
    form = ProfileAdminForm
    can_delete = False
    extra = 0
    fields = ("phone", "city", "institution", "education_level", "photo")
    readonly_fields = ("created_at", "updated_at")


@admin.register(User)
class UserAdmin(AdminFieldLabelsMixin, BaseUserAdmin):
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
class ProfileAdmin(AdminFieldLabelsMixin, admin.ModelAdmin):
    form = ProfileAdminForm
    list_display = ("user", "city", "institution", "education_level", "updated_at")
    list_filter = ("education_level",)
    search_fields = ("user__username", "user__email", "city", "institution")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CompetitionYear)
class CompetitionYearAdmin(AdminFieldLabelsMixin, admin.ModelAdmin):
    list_display = ("year", "is_active", "created_at")
    list_filter = ("is_active",)
    ordering = ("-year",)


class CategoryTranslationInline(AdminFormsetLabelsMixin, admin.StackedInline):
    model = CategoryTranslation
    extra = 0
    fields = ("language", "name", "description", "home_description", "home_highlights")


@admin.register(Category)
class CategoryAdmin(AdminFieldLabelsMixin, admin.ModelAdmin):
    inlines = (CategoryTranslationInline,)
    list_display = ("name", "slug", "code_prefix", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


class FormFieldInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        active_fields = [
            form
            for form in self.forms
            if form.cleaned_data
            and not form.cleaned_data.get("DELETE")
            and form.cleaned_data.get("is_active")
            and form.cleaned_data.get("key")
        ]
        if not active_fields:
            raise ValidationError(
                _("Add at least one active field to the form.")
            )


class FormFieldInline(AdminFormsetLabelsMixin, admin.StackedInline):
    model = FormField
    form = FormFieldAdminForm
    formset = FormFieldInlineFormSet
    extra = 0
    can_delete = True
    fields = (
        "key",
        "label",
        "field_type",
        "short_description",
        "placeholder",
        "is_required",
        ("min_length", "max_length"),
        "regex",
        "regex_error_message",
        "choices_text",
        ("order", "is_active", "review_visibility"),
    )


@admin.register(FormDefinition)
class FormDefinitionAdmin(AdminFieldLabelsMixin, admin.ModelAdmin):
    form = FormDefinitionAdminForm
    inlines = (FormFieldInline,)
    fields = (
        "year",
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
        "year",
        "category",
        "status",
        "attachment_policy",
        "submission_override",
        "opens_at",
        "closes_at",
        "preview_link",
    )
    list_filter = ("status", "year", "category")
    search_fields = ("title", "description")
    actions = ("mark_open", "mark_in_review", "mark_closed")

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("year", CompetitionYear.current().pk)
        return initial

    def save_model(self, request, obj, form, change):
        if not obj.year_id:
            obj.year = CompetitionYear.current()
        super().save_model(request, obj, form, change)

    @admin.display(description=_("Preview"))
    def preview_link(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("main:form_preview", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, _("Preview"))

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

    @admin.action(description=_("Mark selected forms as open"))
    def mark_open(self, request, queryset):
        changed, _ = self._change_form_status(
            request, queryset, FormDefinition.Status.OPEN
        )
        self.message_user(
            request,
            _("%(count)s form(s) marked as open.") % {"count": changed},
        )

    @admin.action(description=_("Put selected forms in review"))
    def mark_in_review(self, request, queryset):
        changed, synced = self._change_form_status(
            request, queryset, FormDefinition.Status.IN_REVIEW
        )
        self.message_user(
            request,
            _(
                "%(changed)s form(s) put in review; %(synced)s application(s) synced."
            )
            % {"changed": changed, "synced": synced},
        )

    @admin.action(description=_("Close selected forms"))
    def mark_closed(self, request, queryset):
        changed, _ = self._change_form_status(
            request, queryset, FormDefinition.Status.CLOSED
        )
        self.message_user(
            request,
            _("%(count)s form(s) closed.") % {"count": changed},
        )


@admin.register(FormField)
class FormFieldAdmin(AdminFieldLabelsMixin, admin.ModelAdmin):
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


class ApplicationAnswerInline(AdminFormsetLabelsMixin, admin.TabularInline):
    model = ApplicationAnswer
    extra = 0
    can_delete = False
    fields = ("field", "value")
    readonly_fields = fields


class AttachmentInline(AdminFormsetLabelsMixin, admin.TabularInline):
    model = Attachment
    extra = 0
    can_delete = False
    fields = ("original_name", "content_type", "size", "uploaded_at", "file")
    readonly_fields = fields


@admin.register(Application)
class ApplicationAdmin(AdminFieldLabelsMixin, admin.ModelAdmin):
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
        status_label = dict(Application.Status.choices).get(status, status)
        status_label = ADMIN_CHOICE_LABELS.get(status_label, status_label)
        self.message_user(
            request,
            _("%(count)s application(s) updated to %(status)s.")
            % {"count": changed, "status": status_label},
        )

    @admin.action(description=_("Start review"))
    def start_review(self, request, queryset):
        self._set_status(request, queryset, Application.Status.IN_REVIEW)

    @admin.action(description=_("Mark evaluated"))
    def mark_evaluated(self, request, queryset):
        self._set_status(request, queryset, Application.Status.EVALUATED)

    @admin.action(description=_("Reopen for review"))
    def reopen(self, request, queryset):
        self._set_status(request, queryset, Application.Status.IN_REVIEW)

    @admin.action(description=_("Export selected applications as CSV"))
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
class ReviewAdmin(AdminFieldLabelsMixin, admin.ModelAdmin):
    list_display = ("application", "juror", "score", "completed_at", "updated_at")
    list_filter = ("completed_at", "juror")
    search_fields = ("application__code", "juror__email", "juror__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(JuryAPIKey)
class JuryAPIKeyAdmin(AdminFieldLabelsMixin, admin.ModelAdmin):
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

    @admin.display(description=_("Status"))
    def status_display(self, obj):
        return obj.status

    @admin.action(description=_("Revoke selected API keys"))
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
        self.message_user(
            request,
            _("%(count)s API key(s) revoked.") % {"count": revoked},
        )


@admin.register(AuditEvent)
class AuditEventAdmin(AdminFieldLabelsMixin, admin.ModelAdmin):
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


class SiteSettingsTranslationInline(AdminFormsetLabelsMixin, admin.StackedInline):
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
class SiteSettingsAdmin(AdminFieldLabelsMixin, admin.ModelAdmin):
    inlines = (SiteSettingsTranslationInline,)
    fieldsets = (
        (
            _("General"),
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
            _("Application period"),
            {
                "fields": (
                    "application_status",
                    "application_opens_at",
                    "application_closes_at",
                )
            },
        ),
        (
            _("Home page"),
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
        (_("Meta"), {"fields": ("updated_at",)}),
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
