from django import template

register = template.Library()

# Django message tags are not identical to Bootstrap theme names.
_MESSAGE_THEMES = {
    "debug": "secondary",
    "info": "info",
    "success": "success",
    "warning": "warning",
    "error": "danger",
}

_MESSAGE_ICONS = {
    "debug": "ba-info",
    "info": "ba-info",
    "success": "ba-check",
    "warning": "ba-alert",
    "error": "ba-alert",
}


@register.filter
def message_theme(tags):
    """Map a Django message tag string to a Bootstrap 6 theme name."""
    for tag in (tags or "").split():
        if tag in _MESSAGE_THEMES:
            return _MESSAGE_THEMES[tag]
    return "info"


@register.filter
def message_icon(tags):
    """Return the SVG symbol id for a Django message tag string."""
    for tag in (tags or "").split():
        if tag in _MESSAGE_ICONS:
            return _MESSAGE_ICONS[tag]
    return "ba-info"
