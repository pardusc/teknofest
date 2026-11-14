import re

from django import forms
from django.core.exceptions import ValidationError

from .models import Profile

MAX_PHOTO_SIZE = 5 * 1024 * 1024
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("phone", "city", "institution", "education_level", "photo")
        widgets = {
            "phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "+90 5xx xxx xx xx"}
            ),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": "Örn. Ankara"}),
            "institution": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Örn. Ankara Üniversitesi"}
            ),
            "education_level": forms.Select(attrs={"class": "form-control"}),
            "photo": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in Profile.REQUIRED_FIELDS:
            self.fields[field].required = True

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        normalized = re.sub(r"[\s\-()]", "", phone)
        if not re.fullmatch(r"\+?\d{10,15}", normalized):
            raise ValidationError("Enter a valid phone number.")
        return phone

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        # An unchanged field returns the stored file, which has no content_type.
        if not photo or not hasattr(photo, "content_type"):
            return photo
        if photo.size > MAX_PHOTO_SIZE:
            raise ValidationError("The photo must be 5 MB or smaller.")
        if photo.content_type not in ALLOWED_PHOTO_TYPES:
            raise ValidationError("Upload a JPG, PNG or WebP image.")
        return photo
