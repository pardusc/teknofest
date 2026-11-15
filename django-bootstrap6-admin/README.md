# django-bootstrap6-admin

A modern, responsive Bootstrap 6 skin for the Django admin. It replaces the
default admin templates and static assets without monkey-patching Django,
changing admin classes, adding database queries, or requiring migrations.

The package is designed to be installed as a normal Django app and to be
publishable to PyPI. It is intentionally a thin presentation layer: Django's
admin views, forms, permissions and JavaScript remain in charge.

## Features

- Bootstrap 6 markup and design tokens throughout the admin.
- Sticky top bar with a collapsible sidebar (desktop) and drawer navigation
  with a backdrop (mobile).
- Dashboard with application cards, model shortcuts and recent activity.
- Changelist with search, date hierarchy, collapsible filters, sortable
  headers, bulk actions and Bootstrap pagination.
- Change form with card-based fieldsets, collapsible sections, a clear save
  bar, tabular/stacked inlines and related-object popups.
- Modern login, logout and password change pages.
- Light, dark and system themes. The existing Django `theme` localStorage
  preference is synchronised with Bootstrap's `data-bs-theme` attribute.
- Accessible focus states, labels, table headers and aria attributes.
- All Django admin JavaScript hooks are preserved:
  `actions.js`, `filters.js`, `nav_sidebar.js`, inlines, Select2/autocomplete,
  calendar widgets and related-object lookups.
- Generic by design: no models, no migrations, no project-specific imports and
  no assumptions about the host project's branding. The default navy/gold
  palette is only a set of overridable CSS variables.

## Requirements

- Python 3.12+
- Django 6.1
- Bootstrap 6.0.0-alpha.1 (bundled with the package)

## Installation

```bash
pip install django-bootstrap6-admin
```

Add the app **before** `django.contrib.admin` so its `admin/` templates take
precedence:

```python
INSTALLED_APPS = [
    "django_bootstrap6_admin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # ...
]
```

That's it. There are no settings to add, no migrations and no URL changes.

For a local checkout:

```bash
pip install -e django-bootstrap6-admin
```

## What gets overridden

The app provides templates for the standard Django admin pages, including:

- `admin/base.html`, `base_site.html`, `index.html`, `app_list.html`
- `admin/change_list.html`, `change_form.html`, `delete_confirmation.html`
- `admin/edit_inline/stacked.html`, `edit_inline/tabular.html`
- `admin/login.html`, `admin/object_history.html`
- `admin/auth/user/add_form.html`, `admin/auth/user/change_password.html`
- `registration/logged_out.html`, `registration/password_change_form.html`
  and `registration/password_change_done.html`

Only the three auth templates used directly by the admin site are shipped.
They still live in Django's global `registration/` namespace, so they also
apply to those views if a project uses them outside the admin; override them
if you need separate public-site auth screens. Password reset templates are
intentionally left to the host project, because reset URLs and their branding
usually belong to the public site rather than to the admin package.

## Customisation

### Long change forms

The action bar sits at the end of the form by default. For long forms, enable
Django's standard top action bar on a `ModelAdmin`:

```python
class BookAdmin(admin.ModelAdmin):
    save_on_top = True
```

### Branding

Use Django's existing admin site settings:

```python
from django.contrib import admin

admin.site.site_header = "Acme administration"
admin.site.site_title = "Acme"
admin.site.index_title = "Operations"
```

### Templates

Every block from Django's admin base templates is preserved. Override any
template normally, for example `templates/admin/base_site.html`, or extend the
provided template:

```django
{% extends "admin/base_site.html" %}

{% block branding %}
  {{ block.super }}
  <span class="badge badge-subtle theme-info">Internal</span>
{% endblock %}
```

### Colours

The skin uses Bootstrap 6 design tokens (`--bs-*`) and a small set of
`--ba-*` variables. Override them after the admin stylesheet, for example in a
custom admin CSS file:

```css
:root {
    --ba-topbar-bg: #1f2937;
    --ba-gold: #f59e0b;
    --ba-sidebar-width: 300px;
}
```

The default primary and danger colours are deliberately deeper than Bootstrap
6's defaults so white button text meets WCAG AA contrast. The select controls
use small `data:` SVG arrows; if you enable a strict CSP, allow
`img-src 'self' data:` (or replace the arrows in your own CSS).

### Turning it off

Remove `django_bootstrap6_admin` from `INSTALLED_APPS` (or move it after
`django.contrib.admin`) and the default Django admin returns immediately.
There is no runtime state to clean up.

## How it works

- The app only contributes templates and static files.
- Django's admin views and forms are untouched.
- Django's own JavaScript remains the source of truth for the sidebar state,
  filters, bulk actions and inlines.
- The bundled `theme.js` reads and writes Django's `theme` localStorage key and
  mirrors it to `data-bs-theme`; it does not replace Django's admin behaviour.
- Bootstrap 6 is pinned as `6.0.0-alpha.1` in
  `static/django_bootstrap6_admin/vendor/bootstrap/` to keep the visual result
  stable. Its MIT licence is included next to the assets. SHA-256 of the
  bundled files:
  - `bootstrap.min.css`: `678508b198d9b1b8877e338f419fdada00024be2bcc638a539dd724856095112`
  - `bootstrap.bundle.min.js`: `47ea447f46e288dd9d3e83147b7ba539c6df5192c047b8f91739cd56a5721148`

## Development

The package lives in `django-bootstrap6-admin/` in this repository. The test
suite uses an isolated settings module and a small demo app:

```bash
cd django-bootstrap6-admin
PYTHONPATH=src:. ../.venv/bin/python -m django test --settings=tests.settings
```

Or, from the repository root:

```bash
cd teknofest
../.venv/bin/python manage.py check
../.venv/bin/python manage.py test
```

## Licence

GPL-3.0-or-later. Bootstrap is distributed under the MIT licence; see
`static/django_bootstrap6_admin/vendor/bootstrap/LICENSE`. The admin templates
are derived from Django's BSD-licensed admin templates; see `NOTICE`.
