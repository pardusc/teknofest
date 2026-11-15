# Keycloak (local development)

Development-only Keycloak realm for the Pardus Teknofest platform. The realm is
imported from `realm-teknofest.json` on container startup, with
`${KEYCLOAK_REALM}`, `${APP_URL}` and `${OIDC_RP_CLIENT_SECRET}` filled from the
environment.

> **Development only.** The admin password and the test-user passwords in this
> directory are intentionally public and trivial. Never reuse them in
> production, and never commit real credentials.

## Run

From the repository root:

```bash
podman volume create keycloak-data
podman pull quay.io/keycloak/keycloak:26.8.2

cp teknofest/.env.example teknofest/.env
# Set a real KC_BOOTSTRAP_ADMIN_PASSWORD in teknofest/.env first.

podman run --name keycloak -d \
  -p 127.0.0.1:8080:8080 \
  --env-file teknofest/.env \
  -v keycloak-data:/opt/keycloak/data \
  -v "$PWD/keycloak/realm-teknofest.json:/opt/keycloak/data/import/realm-teknofest.json:ro,Z" \
  quay.io/keycloak/keycloak:26.8.2 \
  start-dev --import-realm
```

`start-dev` serves plain HTTP, which is why the realm uses
`"sslRequired": "none"`. The container is bound to `127.0.0.1` only.

`teknofest/.env` must define `KEYCLOAK_REALM`, `APP_URL` and
`OIDC_RP_CLIENT_SECRET`; Keycloak substitutes them into
`realm-teknofest.json` during `--import-realm`. `APP_URL` is the browser-visible
base URL of the Django app (scheme + host + port).

Follow the startup log, especially the first import:

```bash
podman logs -f keycloak
```

## Endpoints

| What | URL |
| --- | --- |
| Admin console (master realm) | <http://127.0.0.1:8080/admin/> |
| Admin console (teknofest realm) | <http://127.0.0.1:8080/admin/teknofest/console/> |
| Account console | <http://127.0.0.1:8080/realms/teknofest/account/> |
| OIDC discovery | <http://127.0.0.1:8080/realms/teknofest/.well-known/openid-configuration> |
| Authorization | <http://127.0.0.1:8080/realms/teknofest/protocol/openid-connect/auth> |
| Token | <http://127.0.0.1:8080/realms/teknofest/protocol/openid-connect/token> |
| UserInfo | <http://127.0.0.1:8080/realms/teknofest/protocol/openid-connect/userinfo> |
| Logout | <http://127.0.0.1:8080/realms/teknofest/protocol/openid-connect/logout> |
| Realm JWKS | <http://127.0.0.1:8080/realms/teknofest/protocol/openid-connect/certs> |

Admin bootstrap credentials: `admin` plus the password in
`teknofest/.env` (development only).

## Client

The confidential client `teknofest-web` is configured for a server-side
authorization-code flow without PKCE:

- Client ID: `teknofest-web`
- Client secret: `${OIDC_RP_CLIENT_SECRET}` from `teknofest/.env`
- Redirect URI: `${APP_URL}/accounts/oidc/callback/`
- Post-logout redirect: `${APP_URL}/*`
- Group membership is exposed in the `groups` claim (short names, e.g. `jury`,
  not `/jury`) in the ID token, access token and UserInfo response.

## Django

Django loads `teknofest/.env` at startup through `python-dotenv`
(`override=False`, so real environment variables always win). The same file
holds the Keycloak admin password for the container:

```bash
python teknofest/manage.py runserver 127.0.0.1:8000
```

An empty `OIDC_RP_CLIENT_SECRET` makes the token exchange fail with
`401 unauthorized_client`.

## Test users

| Username | Password | Email | Groups |
| --- | --- | --- | --- |
| `applicant` | `Applicant123!` | `applicant@example.com` | none |
| `jury` | `Jury123!` | `jury@example.com` | `/jury` |

Both users are enabled, have verified e-mail addresses and no required actions.

## Re-import the realm

`--import-realm` only imports a realm that does not already exist. Editing the
JSON and restarting the container is therefore not enough: the old realm stays
in the volume. To apply changes, delete the volume and start fresh:

```bash
podman rm -f keycloak
podman volume rm keycloak-data
```

Then re-run the `podman volume create` / `podman run` commands above.

This destroys all state in the development realm (sessions, users created by
hand, etc.). Alternatively, import the file manually from the admin console via
**Realm settings → Action → Partial import**, but a clean volume is the
reproducible path.

## Stop and clean up

```bash
podman stop keycloak
podman rm keycloak
podman volume rm keycloak-data   # optional: also removes imported realm data
```
