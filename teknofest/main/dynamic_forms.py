from django import forms
from django.core.validators import RegexValidator

from .models import FormField


def to_django_field(field: FormField, required: bool | None = None) -> forms.Field:
    """Build the Django form field for a stored ``FormField`` definition."""
    common = {
        "label": field.label,
        "help_text": field.help_text,
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
            return forms.CharField(widget=forms.TextInput, **text_kwargs)
        case FormField.FieldType.LONG_TEXT:
            return forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), **text_kwargs)
        case FormField.FieldType.MARKDOWN:
            return forms.CharField(widget=forms.Textarea(attrs={"rows": 10}), **text_kwargs)
        case FormField.FieldType.SELECT:
            return forms.ChoiceField(choices=field.choice_pairs, **common)
        case FormField.FieldType.MULTI_SELECT:
            return forms.MultipleChoiceField(
                choices=field.choice_pairs,
                widget=forms.CheckboxSelectMultiple,
                **common,
            )
        case FormField.FieldType.NUMBER:
            return forms.IntegerField(**common)
        case FormField.FieldType.EMAIL:
            return forms.EmailField(**common)
        case FormField.FieldType.URL:
            return forms.URLField(**common)
        case FormField.FieldType.BOOLEAN:
            return forms.BooleanField(**common)
        case FormField.FieldType.DATE:
            return forms.DateField(
                widget=forms.DateInput(attrs={"type": "date"}),
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
