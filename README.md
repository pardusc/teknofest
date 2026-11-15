# Pardus Teknofest Application Platform

A web application for running the application and evaluation process of the
**Pardus Teknofest Competition** (Pardus Hata Yakalama ve Öneri Yarışması).

Applicants apply to the competition through T3KYS. This platform covers the competition's
own process: collecting category-specific applications, reviewing uploaded files, and
scoring them with a jury.

## Tech stack

- Python 3.15
- Django 6.1
- SQLite
- Keycloak for authentication and role management

## Competition forms

Competition years, categories and form definitions are managed from the Django admin.
Each `FormDefinition` belongs to one year and category and is built from ordered
`FormField` definitions. The same definitions generate the applicant form and its
validation through `main.dynamic_forms`.

Forms can be opened, put in review or closed manually from the admin, and each field can
be hidden from reviewers. Staff members can preview a form before opening it.

## Getting started

Requirements: Python 3.15 and [uv](https://docs.astral.sh/uv/) (or plain `venv` + `pip`).

```bash
uv venv --python 3.15 .venv
source .venv/bin/activate
uv pip install -r requirements.txt

python teknofest/manage.py migrate
python teknofest/manage.py compilemessages -l tr
python teknofest/manage.py createsuperuser
python teknofest/manage.py runserver
```

The development server runs at <http://127.0.0.1:8000/>.

`compilemessages` requires gettext (`msgfmt`). It is only needed after editing
`locale/tr/LC_MESSAGES/django.po`; the compiled `.mo` file is committed.

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

## Localization

Backend messages use Django's standard gettext catalogs. Turkish is the default
language (`LANGUAGE_CODE = "tr"`); untranslated strings fall back to their English
msgid.

- Translations live in `teknofest/locale/tr/LC_MESSAGES/django.po`
- After adding or changing strings, regenerate and compile the catalog:

```bash
cd teknofest
../.venv/bin/python manage.py makemessages -l tr --no-wrap
../.venv/bin/python manage.py compilemessages -l tr
```

Commit both `django.po` and `django.mo`.

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
