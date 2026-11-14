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
    │   ├── models.py
    │   ├── urls.py
    │   ├── views.py
    │   ├── migrations/
    │   └── templates/main/
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
Swapping this model later is expensive, so it must not be reverted.

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

The Django project skeleton and the custom user model are in place, with a
placeholder home page and admin integration. Planned work includes Keycloak
authentication, applicant profiles and consent, yearly application forms with
file uploads, and jury scoring.

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
