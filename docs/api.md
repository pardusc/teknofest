# Jury API

The jury API exposes the same review flow as the jury web interface.

Base URL: `/api/jury/`

## Endpoint summary

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/jury/forms/` | List forms available to the jury |
| `GET` | `/api/jury/forms/{form_id}/applications/` | List applications with filters and pagination |
| `GET` | `/api/jury/applications/{public_id}/` | Read one application in detail |
| `POST` | `/api/jury/applications/{public_id}/review/` | Create or update the current juror's review |
| `GET` | `/api/jury/applications/{public_id}/attachments/{attachment_id}/download/` | Download an attachment |
| `GET` | `/api/jury/me/` | Show the current juror and API-key metadata |

## Authentication

Create a personal key at `/jury/api-keys/`. Only jury members can open this page.
A key is shown once, expires after **1, 7, 30 or 90 days**, and can be revoked at
any time.

Send the key with every request:

```http
Authorization: Bearer ptj_...
```

Keys are personal: scores and notes submitted through the API are recorded under
the key owner's account.

### Quick start after creating a key

Copy the key shown on the creation screen, then test it with:

```bash
KEY="ptj_..."

curl -s -H "Authorization: Bearer $KEY" \
  "http://127.0.0.1:8000/api/jury/me/"
```

A valid key returns the juror and key metadata. To list the available forms:

```bash
curl -s -H "Authorization: Bearer $KEY" \
  "http://127.0.0.1:8000/api/jury/forms/"
```

## Endpoints

### List forms

```http
GET /api/jury/forms/
```

Returns forms linked to active competition years and categories, with
`application_count` and `my_completed_count`.

### List applications

```http
GET /api/jury/forms/{form_id}/applications/
```

Optional query parameters:

| Parameter | Values | Description |
| --- | --- | --- |
| `q` | text | Application code, or applicant e-mail when identity is not masked |
| `mine` | `pending`, `completed` | Filter by the current juror's review state |
| `files` | `1` | Only applications with attachments |
| `ordering` | `submitted_at`, `-submitted_at`, `my_score`, `-my_score`, `average`, `-average` | Sort order |
| `page` | integer | Page number |
| `page_size` | integer | Page size, maximum 100 |

Response:

```json
{
  "count": 12,
  "next": "http://127.0.0.1:8000/api/jury/forms/1/applications/?page=2",
  "previous": null,
  "results": [
    {
      "public_id": "107fa2c5-76f0-40e6-8edd-d974ba05f356",
      "code": "BUG-2026-00001",
      "status": "submitted",
      "submitted_at": "2026-11-15T06:51:00+00:00",
      "updated_at": "2026-11-15T06:51:00+00:00",
      "category": {"id": 1, "slug": "bug", "name": "Hata Yakalama"},
      "attachment_count": 0,
      "my_score": null,
      "my_completed": false,
      "average": null
    }
  ]
}
```

### Application detail

```http
GET /api/jury/applications/{public_id}/
```

Returns the application, form summary, applicant information (masked when the
form requires it), visible answers, attachments, the current juror's review,
other reviews, the average score and whether reviews are currently open.

Attachment `download_url` values point to the API download endpoint and require
the same Bearer key.

### Submit or update a review

```http
POST /api/jury/applications/{public_id}/review/
Content-Type: application/json
Authorization: Bearer ptj_...

{
  "score": 90,
  "note": "Optional evaluation note"
}
```

The score is required and must be an integer from `0` to `100`. Repeating the
request updates the same juror's review; it never creates a duplicate.

Response:

```json
{
  "review": {
    "id": 4,
    "score": 90,
    "note": "Optional evaluation note",
    "completed_at": "2026-11-15T09:30:00+00:00",
    "updated_at": "2026-11-15T09:30:00+00:00"
  },
  "average_score": 87.5,
  "completed_count": 3
}
```

### Download an attachment

```http
GET /api/jury/applications/{public_id}/attachments/{attachment_id}/download/
```

Returns the original file. The key must belong to an active jury member.

### Current identity

```http
GET /api/jury/me/
```

Returns the authenticated user and metadata for the key used in the request
(`name`, `prefix`, `created_at`, `expires_at`, `last_used_at`).

## Examples

```bash
KEY="ptj_..."

curl -H "Authorization: Bearer $KEY" \
  "http://127.0.0.1:8000/api/jury/forms/"

curl -H "Authorization: Bearer $KEY" \
  "http://127.0.0.1:8000/api/jury/forms/1/applications/?mine=pending&ordering=-submitted_at"

curl -H "Authorization: Bearer $KEY" \
  "http://127.0.0.1:8000/api/jury/applications/107fa2c5-76f0-40e6-8edd-d974ba05f356/"

curl -X POST \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"score": 90, "note": "Good submission"}' \
  "http://127.0.0.1:8000/api/jury/applications/107fa2c5-76f0-40e6-8edd-d974ba05f356/review/"
```

## Errors

| Status | Meaning |
| --- | --- |
| `400` | Invalid input or review is not currently allowed |
| `401` | Missing, malformed, expired or revoked key |
| `404` | Application, attachment or form not found |
| `405` | Wrong HTTP method |

Error responses use DRF's JSON shape, for example:

```json
{"detail": "Invalid or expired API key."}
```
