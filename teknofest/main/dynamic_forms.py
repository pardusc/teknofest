import unicodedata

from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .models import FormField
from .validators import (
    APPLICATION_TITLE_KEY,
    APPLICATION_TITLE_MAX_LENGTH,
    APPLICATION_TITLE_MIN_LENGTH,
    validate_application_title,
)

_TITLE_REPLACEMENTS = str.maketrans(
    {
        "’": "'",
        "‘": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "–": "-",
        "—": "-",
        "−": "-",
        "‑": "-",
        "\u00a0": " ",
    }
)


class ApplicationTitleField(forms.CharField):
    """Normalised title field with a strict character whitelist."""

    default_error_messages = {
        "min_length": gettext_lazy(
            "Application titles must be at least %(limit_value)s characters."
        ),
        "max_length": gettext_lazy(
            "Application titles can be at most %(limit_value)s characters."
        ),
    }

    def to_python(self, value):
        value = super().to_python(value)
        if value:
            value = unicodedata.normalize("NFC", value)
            value = value.translate(_TITLE_REPLACEMENTS)
            value = " ".join(value.split())
        return value


def _placeholder(field: FormField) -> str:
    if field.placeholder:
        return field.placeholder
    if field.key == APPLICATION_TITLE_KEY:
        return _("e.g. Login page crashes after update")
    match field.field_type:
        case FormField.FieldType.SHORT_TEXT:
            return _("Type your answer")
        case FormField.FieldType.LONG_TEXT:
            return _("Type your answer in detail")
        case FormField.FieldType.NUMBER:
            return _("e.g. 3")
        case FormField.FieldType.EMAIL:
            return _("name@example.com")
        case FormField.FieldType.URL:
            return _("https://example.com")
    return ""


def _text_attrs(field: FormField) -> dict[str, str]:
    attrs = {"class": "form-control"}
    placeholder = _placeholder(field)
    if placeholder:
        attrs["placeholder"] = placeholder
    if field.short_description:
        attrs["aria-describedby"] = f"id_{field.key}_description"
    if field.field_type in (FormField.FieldType.SHORT_TEXT, FormField.FieldType.LONG_TEXT):
        if field.max_length:
            attrs["data-maxlength"] = str(field.max_length)
        if field.min_length:
            attrs["data-minlength"] = str(field.min_length)
            attrs["data-minlength-message"] = _(
                "This field must be at least %(min)s characters."
            ) % {"min": field.min_length}
    return attrs


class YesNoRadioSelect(forms.RadioSelect):
    """Radio group used for yes/no fields."""

    yes_no = True


class ThemedDateInput(forms.DateInput):
    """Date input with a themed calendar trigger next to it."""

    template_name = "main/widgets/date_input.html"


def _application_title_field(field: FormField) -> ApplicationTitleField:
    max_length = min(
        field.max_length or APPLICATION_TITLE_MAX_LENGTH,
        APPLICATION_TITLE_MAX_LENGTH,
    )
    min_length = min(
        max(field.min_length or 0, APPLICATION_TITLE_MIN_LENGTH),
        max_length,
    )
    attrs = {
        "class": "form-control",
        "placeholder": _placeholder(field),
        "maxlength": str(max_length),
        "data-maxlength": str(max_length),
        "data-minlength": str(min_length),
        "data-minlength-message": _(
            "This field must be at least %(min)s characters."
        )
        % {"min": min_length},
    }
    if field.short_description:
        attrs["aria-describedby"] = f"id_{field.key}_description"

    validators = [validate_application_title]
    if field.regex:
        validators.append(
            RegexValidator(
                field.regex,
                message=field.regex_error_message or "Enter a valid value.",
            )
        )

    return ApplicationTitleField(
        label=field.label,
        help_text=field.short_description
        or _("Give your application a short, descriptive title."),
        required=True,
        min_length=min_length,
        max_length=max_length,
        widget=forms.TextInput(attrs=attrs),
        validators=validators,
    )


def to_django_field(field: FormField, required: bool | None = None) -> forms.Field:
    """Build the Django form field for a stored ``FormField`` definition."""
    if field.key == APPLICATION_TITLE_KEY:
        return _application_title_field(field)

    common = {
        "label": field.label,
        "help_text": field.short_description,
        "required": field.is_required if required is None else required,
    }
    text_kwargs = dict(common)
    if field.max_length:
        text_kwargs["max_length"] = field.max_length
    if field.min_length:
        text_kwargs["min_length"] = field.min_length
    if field.regex:
        text_kwargs["validators"] = [
            RegexValidator(
                field.regex,
                message=field.regex_error_message or "Enter a valid value.",
            )
        ]

    match field.field_type:
        case FormField.FieldType.SHORT_TEXT:
            return forms.CharField(
                widget=forms.TextInput(attrs=_text_attrs(field)),
                **text_kwargs,
            )
        case FormField.FieldType.LONG_TEXT:
            return forms.CharField(
                widget=forms.Textarea(attrs={"rows": 4, **_text_attrs(field)}),
                **text_kwargs,
            )
        case FormField.FieldType.MARKDOWN:
            return forms.CharField(widget=forms.Textarea(attrs={"rows": 10}), **text_kwargs)
        case FormField.FieldType.SELECT:
            return forms.ChoiceField(
                choices=field.choice_pairs,
                widget=forms.RadioSelect(attrs={"class": "radio"}),
                **common,
            )
        case FormField.FieldType.MULTI_SELECT:
            return forms.MultipleChoiceField(
                choices=field.choice_pairs,
                widget=forms.CheckboxSelectMultiple(attrs={"class": "check"}),
                **common,
            )
        case FormField.FieldType.NUMBER:
            return forms.IntegerField(
                widget=forms.NumberInput(attrs=_text_attrs(field)),
                **common,
            )
        case FormField.FieldType.EMAIL:
            return forms.EmailField(
                widget=forms.EmailInput(attrs=_text_attrs(field)),
                **common,
            )
        case FormField.FieldType.URL:
            return forms.URLField(
                widget=forms.URLInput(attrs=_text_attrs(field)),
                **common,
            )
        case FormField.FieldType.BOOLEAN:
            return forms.BooleanField(
                widget=YesNoRadioSelect(
                    choices=((True, _("Yes")), (False, _("No"))),
                    attrs={"class": "radio"},
                ),
                **common,
            )
        case FormField.FieldType.DATE:
            return forms.DateField(
                widget=ThemedDateInput(
                    attrs={
                        "type": "date",
                        "class": "form-control",
                        **(
                            {"aria-describedby": f"id_{field.key}_description"}
                            if field.short_description
                            else {}
                        ),
                    }
                ),
                **common,
            )

    raise ValueError(f"Unsupported field type: {field.field_type}")


def build_form(definition, data=None, files=None, enforce_required=True, initial=None):
    """Create a Django form class from a ``FormDefinition`` and its active fields."""
    fields = {
        field.key: to_django_field(
            field,
            required=field.is_required if enforce_required else False,
        )
        for field in definition.fields.filter(is_active=True)
    }
    form_class = type("DynamicApplicationForm", (forms.Form,), fields)
    return form_class(data=data, files=files, initial=initial)
