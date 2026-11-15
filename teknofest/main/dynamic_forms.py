from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext as _

from .models import FormField

DEFAULT_PLACEHOLDERS = {
    FormField.FieldType.SHORT_TEXT: "Type your answer",
    FormField.FieldType.LONG_TEXT: "Type your answer in detail",
    FormField.FieldType.NUMBER: "e.g. 3",
    FormField.FieldType.EMAIL: "name@example.com",
    FormField.FieldType.URL: "https://example.com",
}


def _placeholder(field: FormField) -> str:
    if field.placeholder:
        return field.placeholder
    default = DEFAULT_PLACEHOLDERS.get(field.field_type)
    return _(default) if default else ""


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


def to_django_field(field: FormField, required: bool | None = None) -> forms.Field:
    """Build the Django form field for a stored ``FormField`` definition."""
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
                widget=forms.DateInput(
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
