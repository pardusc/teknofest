import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import FormDefinition, FormField, JuryAPIKey, Profile
from .validators import validate_image_upload

MAX_PHOTO_SIZE = 1 * 1024 * 1024


def _validate_profile_photo(photo):
    # An unchanged field returns the stored file, which has no content_type.
    if not photo or not hasattr(photo, "content_type"):
        return photo
    if photo.size > MAX_PHOTO_SIZE:
        raise ValidationError(_("The photo must be 1 MB or smaller."))
    validate_image_upload(photo)
    return photo


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("phone", "city", "institution", "education_level", "photo")
        widgets = {
            "phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "+90 5xx xxx xx xx"}
            ),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": _("e.g. Ankara")}),
            "institution": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("e.g. Gazi University")}
            ),
            "education_level": forms.Select(attrs={"class": "form-control"}),
            "photo": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/png,image/jpeg,.png,.jpg,.jpeg",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in Profile.REQUIRED_FIELDS:
            self.fields[field].required = True

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        normalized = re.sub(r"[\s\-()]", "", phone)
        if not re.fullmatch(r"\+?\d{10,15}", normalized):
            raise ValidationError(_("Enter a valid phone number."))
        return phone

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        return _validate_profile_photo(photo)


class ProfileAdminForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = "__all__"

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        return _validate_profile_photo(photo)


class JuryAPIKeyForm(forms.ModelForm):
    duration_days = forms.TypedChoiceField(
        choices=JuryAPIKey.Duration.choices,
        coerce=int,
        initial=JuryAPIKey.Duration.THIRTY_DAYS,
        label=_("Duration"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = JuryAPIKey
        fields = ("name",)
        labels = {"name": _("Key name")}
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("e.g. Review script"),
                }
            ),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise ValidationError(_("Enter a name for this key."))
        return name


class FormDefinitionAdminForm(forms.ModelForm):
    """Admin form for form definitions; the closing date is optional."""

    class Meta:
        model = FormDefinition
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["closes_at"].required = False
        self.fields["closes_at"].help_text = _(
            "Optional. Leave empty to use the global application deadline, if configured."
        )


class FormFieldAdminForm(forms.ModelForm):
    """Admin form that edits the JSON ``choices`` list as one option per line."""

    choices_text = forms.CharField(
        required=False,
        label="Choices",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One option per line, used by single and multiple choice fields.",
    )

    class Meta:
        model = FormField
        fields = (
            "form",
            "key",
            "label",
            "field_type",
            "help_text",
            "is_required",
            "min_length",
            "max_length",
            "regex",
            "regex_error_message",
            "order",
            "is_active",
            "review_visibility",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["choices_text"].initial = "\n".join(
                value for value, _label in self.instance.choice_pairs
            )

    def clean_choices_text(self):
        text = self.cleaned_data.get("choices_text", "")
        values = [line.strip() for line in text.splitlines() if line.strip()]
        if len(values) != len(set(values)):
            raise ValidationError(_("Choices must be unique."))
        if self.cleaned_data.get("field_type") in FormField.CHOICE_TYPES and not values:
            raise ValidationError(_("Choose at least one option for this field type."))
        return values

    def clean(self):
        cleaned_data = super().clean()
        # Set choices before ModelForm._post_clean() runs model validation.
        if "choices_text" in cleaned_data:
            self.instance.choices = [
                {"value": value, "label": value}
                for value in cleaned_data["choices_text"]
            ]
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if "choices_text" in self.cleaned_data:
            instance.choices = [
                {"value": value, "label": value}
                for value in self.cleaned_data["choices_text"]
            ]
        if commit:
            instance.save()
            self.save_m2m()
        return instance
