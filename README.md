# Pardus Teknofest Application Platform

A web application for running the application and evaluation process of the
**Pardus Teknofest Competition** (Pardus Hata Yakalama ve Öneri Yarışması).

Applicants apply to the competition through T3KYS. This platform covers the competition's
own process: collecting category-specific applications, reviewing uploaded files, and
scoring them with a jury.

## Roles

| Role | Description |
| --- | --- |
| Applicant | Signs in with Keycloak, completes their profile and KVKK consent, and submits or edits applications for the Bug/Suggestion and Development categories. |
| Jury | Sees the category they are assigned to, reviews applications, and submits scores and notes. |
| Admin | Manages competition years, opens and closes forms, and monitors the review process. |

Roles are determined by the Keycloak roles assigned to each account.

## Tech stack

- Python 3.15
- Django 6.1
- SQLite
- Keycloak for authentication and role management

## Project structure

```
.
├── LICENSE
├── README.md
├── requirements.txt
├── .gitignore
└── teknofest/
    ├── manage.py
    ├── main/
    │   ├── admin.py
    │   ├── dynamic_forms.py
    │   ├── forms.py
    │   ├── models/
    │   │   ├── accounts.py
    │   │   ├── applications.py
    │   │   └── competitions.py
    │   ├── services/
    │   │   └── applications.py
    │   ├── urls.py
    │   ├── views.py
    │   ├── migrations/
    │   └── templates/
    │       ├── main/
    │       └── registration/
    └── teknofest/
        ├── settings.py
        ├── urls.py
        ├── asgi.py
        └── wsgi.py
```

## User model

The project uses a custom user model, `main.User`, from the very first migration.
It extends `django.contrib.auth.models.AbstractUser` and adds a unique
`keycloak_id` field for the OIDC `sub` claim plus a unique e-mail address.
Personal information (phone, city, institution, education level and an optional
photo) lives in the related `main.Profile` model.
Swapping this model later is expensive, so it must not be reverted.

## Competition forms

Competition years, categories and form definitions are managed from the Django admin.
Each `FormDefinition` belongs to one year and category and is built from ordered
`FormField` definitions. The same definitions generate the applicant form and its
validation through `main.dynamic_forms`.

Forms can be opened, put in review or closed manually from the admin, and each field can
be hidden from reviewers. Staff members can preview a form before opening it.

## Applications

Applicants work on a draft and submit it while the form is open. On submission the
application receives a readable code such as `BUG-2026-00001` or
`DEVELOPMENT-2026-00001`. Drafts may be incomplete; submission validates all required
fields and requires a complete profile.

Attachments are category-specific:

- **Bug / Suggestion** requires at least one attachment.
- **Development** does not accept attachments.

Limits are 10 files maximum, 2 MB per file and 10 MB in total. Only real JPG and PNG
images are accepted, verified from their content rather than their extension.
Applications can be edited or deleted until the form closes.

## Applicant flow

All routes require login, and non-owners receive a 404.

| Route | Template | Purpose |
| --- | --- | --- |
| `/forms/` | `main/form_list.html` | Available forms |
| `/forms/<pk>/` | `main/form_detail.html` | Form details and apply action |
| `/forms/<pk>/apply/` | — | Start or reuse a draft (POST) |
| `/applications/` | `main/application_list.html` | My applications |
| `/applications/<uuid>/` | `main/application_detail.html` | Application detail |
| `/applications/<uuid>/edit/` | `main/application_edit.html` | Dynamic form and draft saving |
| `/applications/<uuid>/preview/` | `main/application_preview.html` | Submission preview |
| `/applications/<uuid>/submit/` | — | Submit (POST) |
| `/applications/<uuid>/delete/` | — | Delete (POST) |
| `/applications/<uuid>/attachments/upload/` | — | Upload an attachment (POST) |
| `/applications/<uuid>/attachments/<pk>/delete/` | — | Delete an attachment (POST) |

The frontend team owns the templates; empty placeholders are committed so the views
render while the interface is being built.

## Getting started

Requirements: Python 3.15 and [uv](https://docs.astral.sh/uv/) (or plain `venv` + `pip`).

```bash
uv venv --python 3.15 .venv
source .venv/bin/activate
uv pip install -r requirements.txt

python teknofest/manage.py migrate
python teknofest/manage.py createsuperuser
python teknofest/manage.py runserver
```

The development server runs at <http://127.0.0.1:8000/>.

If you prefer plain `venv`:

```bash
python3.15 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Settings are read from environment variables with development-friendly defaults:

| Variable | Default | Description |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | insecure development key | Secret key; must be set in production. |
| `DJANGO_DEBUG` | `1` | Set to `0` to disable debug mode. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list of allowed hosts. |

## Status

The Django project skeleton, the custom user model and the applicant profile are in
place, including login/logout and profile editing. Competition years, categories and
dynamic form definitions can be managed from the admin. Application drafts, submission,
attachment rules and readable application codes are implemented in the service layer.
Authentication currently uses Django's local login; Keycloak integration is planned.

Planned work includes KVKK consent, applicant and jury views, jury scoring, and Keycloak
roles.

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
