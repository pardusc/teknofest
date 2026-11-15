# Keycloak authentication

The platform delegates applicant and jury sign-in to Keycloak over OpenID
Connect. Keycloak owns credentials, login sessions and group membership; Django
keeps the user database, permissions, applications and the admin panel.

The local realm, client, test users and container commands live in
[keycloak/README.md](../keycloak/README.md). General Python/Django setup is in
[README.md](../README.md). This document covers how the integration works, how
to run and verify it, and how to cut over and deploy it.

## 1. How authentication works

Sign-in uses the OIDC **authorization code flow** with a confidential client
(`teknofest-web`), handled entirely server-side. No token is exposed to the
browser.

1. The browser opens `/accounts/login/` and either submits the local password
   form (transition period only) or clicks **Sign in with Keycloak**, which
   links to `/accounts/oidc/authenticate/`.
2. Django generates `state` and `nonce`, stores them in the session, and
   redirects to the Keycloak authorization endpoint derived from
   `OIDC_OP_ISSUER`.
3. Keycloak authenticates the user (password, and its own SSO session cookie)
   and redirects back to
   `http://127.0.0.1:8000/accounts/oidc/callback/?code=...&state=...`.
4. Django checks `state`, exchanges the code at the token endpoint using the
   client ID and client secret, and verifies the ID token signature against the
   realm JWKS (RS256) plus the `nonce`.
5. `main.auth.KeycloakOIDCBackend` matches or provisions the local account and
   syncs the `jury` group from the `groups` claim.
6. Django creates its own session and redirects to `LOGIN_REDIRECT_URL`
   (`main:application_list`). Applicants without a complete profile are sent to
   the profile form first by `main.middleware.ProfileCompletionMiddleware`.

Relevant URLs:

| URL | Purpose |
| --- | --- |
| `/accounts/login/` | Local login page; password form and the Keycloak button |
| `/accounts/oidc/authenticate/` | Starts the OIDC handshake |
| `/accounts/oidc/callback/` | Registered redirect URI; finishes the handshake |
| `/accounts/oidc/logout/` | Logout endpoint (see section 6) |
| `/admin/` | Django admin, local username/password only |

Roles come from two different places:

| Role | Source | Local representation |
| --- | --- | --- |
| Applicant | Any Keycloak user without the `jury` group | `User` with no `jury` group |
| Jury | Keycloak group `jury` | Django group `jury` (`main.permissions.JURY_GROUP_NAME`) |
| Staff / superuser | Created locally, never from claims | `is_staff` / `is_superuser` |

## 2. Local setup checklist

Run everything from the repository root with the virtualenv active.

1. **Start Keycloak.** Follow [keycloak/README.md](../keycloak/README.md):
   copy `teknofest/.env.example` to `teknofest/.env`, set the admin
   password, and start the container with
   `quay.io/keycloak/keycloak:26.8.2 start-dev --import-realm` on
   `127.0.0.1:8080`. Wait until the realm import appears in
   `podman logs -f keycloak`.

2. **Install dependencies.** `mozilla-django-oidc==5.0.2` is already listed in
   `requirements.txt`:

   ```bash
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```

3. **Configure the app environment.** `teknofest/teknofest/settings.py` loads
   `teknofest/.env` through `python-dotenv`, so no shell exports are needed.
   The file (copied in step 1) already carries `OIDC_OP_ISSUER`,
   `OIDC_RP_CLIENT_ID` and `OIDC_RP_CLIENT_SECRET`; real environment variables
   still take precedence when present.

4. **Apply migrations** (the custom user model carries `keycloak_id`):

   ```bash
   python teknofest/manage.py migrate
   ```

5. **Create an admin** if you do not have one. This account stays local and
   must not have a Keycloak identity:

   ```bash
   python teknofest/manage.py createsuperuser
   ```

6. **Confirm both authentication backends are registered.** The OIDC backend
   and the local `ModelBackend` (for `/admin/`) must both be active in
   `teknofest/teknofest/settings.py`:

   ```python
   AUTHENTICATION_BACKENDS = [
       "main.auth.KeycloakOIDCBackend",
       "django.contrib.auth.backends.ModelBackend",
   ]
   ```

   Check what the running settings actually load:

   ```bash
   python teknofest/manage.py shell -c \
     "from django.conf import settings; print(settings.AUTHENTICATION_BACKENDS)"
   ```

7. **Run the server on the registered host.** The redirect URI contains
   `127.0.0.1`, not `localhost`:

   ```bash
   python teknofest/manage.py runserver 127.0.0.1:8000
   ```

   Open <http://127.0.0.1:8000/accounts/login/> and use **Sign in with
   Keycloak**. Log in with `applicant` / `Applicant123!` first, then with
   `jury` / `Jury123!`.

8. **Verify provisioning and role mapping.** Each login should create (or
   update) exactly one local user:

   ```bash
   python teknofest/manage.py shell -c "
   from django.contrib.auth import get_user_model
   for user in get_user_model().objects.order_by('username'):
       print(
           user.username,
           user.email,
           user.keycloak_id,
           user.has_usable_password(),
           sorted(user.groups.values_list('name', flat=True)),
           user.is_staff,
       )
   "
   ```

   Expected for the two test users:

   - `applicant@example.com`: a non-empty `keycloak_id`, no groups,
     `has_usable_password()` is `False`.
   - `jury@example.com`: a non-empty `keycloak_id`, groups `['jury']`,
     `has_usable_password()` is `False`.
   - Your admin: a username/password account, `keycloak_id` is `None`.

   A second Keycloak login must reuse the same rows, not create duplicates.

9. **Run the integration tests:**

   ```bash
   python teknofest/manage.py test main.tests_oidc main.tests_reset_accounts
   ```

10. **Check `/admin/` still works** with the local superuser credentials.

## 3. Environment variables

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `OIDC_OP_ISSUER` | No in development | `http://127.0.0.1:8080/realms/teknofest` | Base URL of the realm. A trailing slash is stripped. |
| `OIDC_RP_CLIENT_ID` | No | `teknofest-web` | Confidential client registered in the realm. |
| `OIDC_RP_CLIENT_SECRET` | Yes outside development | empty string | An empty value makes the token exchange fail. Never commit a real secret. |

The authorization, token, userinfo, JWKS and logout endpoints in settings are
derived from `OIDC_OP_ISSUER`; only the issuer, client ID and client secret need
values per environment.

**The issuer must match the browser-visible URL exactly.** Keycloak stamps its
own URLs, and the token `iss`, with the URL clients use. If the browser reaches
Keycloak at `https://sso.example.org/realms/teknofest`, that is the value for
`OIDC_OP_ISSUER`; using a container name or `http://` internally while the
browser uses `https://` sends redirects and token requests to the wrong host
(and produces a token `iss` that does not match the configured realm). Scheme,
host, port and realm path must all agree, and `DJANGO_ALLOWED_HOSTS` must contain
the hostname Django is reached at.

## 4. Roles and provisioning rules

All logic lives in `main.auth.KeycloakOIDCBackend` (a
`mozilla_django_oidc.auth.OIDCAuthenticationBackend` subclass). Tests in
`teknofest/main/tests_oidc.py` pin these rules.

- **Identity is the `sub` claim only.** Returning users are matched on
  `User.keycloak_id`. Email is never an identity key.
- **New users** are created with the email from the claims, a unique username
  derived from `preferred_username` (lowercased, invalid characters collapsed,
  max 150 characters, numeric suffix on collision, `user` fallback), and an
  **unusable password**.
- **Legacy accounts are linked once.** If a non-staff local account already
  owns the same email, the first Keycloak login attaches it (preserving
  applications and profile) and also sets an unusable password, so the local
  password stops working.
- **Staff and superuser emails are refused.** A Keycloak identity that claims a
  staff/superuser email is rejected with `SuspiciousOperation`; staff accounts
  are never linked or converted.
- **No re-linking.** An account already bound to one `sub` is never moved to
  another identity, and an email owned by a different user is rejected.
- **Group sync happens on every login.** The Keycloak `groups` claim (accepts
  `jury`, `/jury` or `/team/jury`) adds or removes the single local `jury`
  group. Other local groups are untouched.
- **Privileges are never derived from claims.** The backend never sets
  `is_staff`, `is_superuser` or `is_active`; admin access remains a local
  decision.
- **Names** are refreshed from `given_name`/`family_name`, falling back to
  `name`.

Because `keycloak_id` is unique and nullable, local admins and staff keep
working with an empty value. The [jury API](api.md) is bound to the same local
account, so API keys issued to a juror belong to that user.

## 5. Transition plan and cut-over

The password login and Keycloak run in parallel until legacy local accounts are
retired.

**Stage 1 — parallel login.** Keep `/accounts/login/` and the Keycloak button.
Tell users to sign in with Keycloak at least once. Verify in the shell that
`keycloak_id` is populated and roles are correct (section 2, step 8). Keep
`createsuperuser` for admins.

**Stage 2 — inventory legacy accounts.** Back up first: removing a user
cascades to their applications, profiles, reviews, attachments and API keys.

```bash
cp teknofest/db.sqlite3 teknofest/db.sqlite3.bak
python teknofest/manage.py shell -c \
  "from django.contrib.auth import get_user_model; print(list(get_user_model().objects.filter(is_staff=False, is_superuser=False).values_list('username', 'email')))"
```

Export anything those users still need before removing them.

**Stage 3 — remove legacy accounts.** Delete the remaining non-staff accounts
through the Django admin (`/admin/main/user/`) or with a one-off script you
review yourself. Accounts already linked to Keycloak are removed too, and the
next Keycloak login provisions a fresh local account. Uploaded files for deleted
applications are removed by the existing `post_delete` signal. Staff and
superusers must be preserved so `/admin/` keeps working.

**Stage 4 — OIDC-only login.** Once every non-admin account is Keycloak-backed,
remove the local password form from `/accounts/login/` (or make the login route
start the OIDC flow directly) and keep only the **Sign in with Keycloak** path.
Do not remove `django.contrib.auth.backends.ModelBackend`: `/admin/` needs it,
and `createsuperuser` remains the way to bootstrap administrators.

Keep a rollback path: the database backup from stage 2 plus the ability to
re-enable the password form. Keycloak accounts are not in that backup, but no
Keycloak state is touched by the command.

## 6. Production notes

- **Use HTTPS for both apps.** Keycloak must be reached at its public HTTPS URL
  (for example `https://sso.example.org/realms/teknofest`) and Django at its
  public HTTPS URL. The realm client must list
  `https://<app-host>/accounts/oidc/callback/` as a valid redirect URI and
  `https://<app-host>/*` as a post-logout redirect. Development URIs stay in the
  dev realm only.
- **Do not run `start-dev` in production.** The dev container uses plain HTTP,
  an imported realm with public test credentials and `sslRequired: none`. Run
  Keycloak with `start`, a real database, TLS termination and its public
  hostname/frontend URL configured so the `iss` it mints is the HTTPS URL.
  Replace the dev realm import with a managed realm.
- **Use a real client secret.** Generate a new secret for `teknofest-web`, store
  it in a secret manager, inject `OIDC_RP_CLIENT_SECRET` from the environment,
  and rotate it by updating Keycloak and the app together. Never reuse the
  development value from `teknofest/.env`.
- **Secure cookies and proxy headers.** Behind a TLS-terminating proxy, Django
  only knows the request was HTTPS if you tell it:

  ```python
  SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
  SESSION_COOKIE_SECURE = True
  CSRF_COOKIE_SECURE = True
  CSRF_TRUSTED_ORIGINS = ["https://<app-host>"]
  ```

  Also set `DJANGO_DEBUG=0`, a real `DJANGO_SECRET_KEY`, the correct
  `DJANGO_ALLOWED_HOSTS`, and `SECURE_SSL_REDIRECT`/HSTS as appropriate. The
  proxy must forward `Host`, `X-Forwarded-Proto` and `X-Forwarded-For`.
- **Session lifetime.** The Django session and the Keycloak SSO session are
  independent. The Django session lasts `SESSION_COOKIE_AGE` (two weeks by
  default) unless `SESSION_EXPIRE_AT_BROWSER_CLOSE` is set. The project adds
  `main.middleware.OIDCSessionRefresh` (a `SessionRefresh` subclass that skips
  sessions without an ID token) to `MIDDLEWARE`, so Keycloak sessions renew the
  ID token five minutes before expiry while local admin sessions are untouched.
  Align the realm's SSO Session Idle/Max values with the intended policy.
- **RP-initiated logout.** `OIDC_STORE_ID_TOKEN=True` keeps the ID token
  available as `id_token_hint`. The logout form posts to `/accounts/logout/`
  (`mozilla_django_oidc.views.OIDCLogoutView`), which calls
  `main.auth.keycloak_logout_url` through `OIDC_OP_LOGOUT_URL_METHOD` and
  redirects to Keycloak's end-session endpoint with `id_token_hint` and the
  registered `post_logout_redirect_uri`. Sessions without an ID token (local
  admin logins) fall back to `/`. Register the post-logout URI in the client
  (the dev realm allows `http://127.0.0.1:8000/*`).
- **Clock and network.** Token validation depends on reasonably accurate clocks
  on both hosts, and Django must be able to reach the issuer for JWKS, token and
  userinfo requests. Keep the realm key cache warm; block public access to the
  Keycloak admin console or restrict it to administrators.

## 7. Troubleshooting

### `Invalid parameter: redirect_uri`

Keycloak rejects the callback because the `redirect_uri` Django sent is not an
exact string match of a registered URI. Compare scheme, host, port, path and the
trailing slash. The classic cause is opening the site at
`http://localhost:8000` instead of `http://127.0.0.1:8000`, or using HTTPS in
production without adding the production URI to the client. Fix the URL you use
or add the URI in the Keycloak admin console; do not "fix" it by widening the
redirect pattern to a wildcard.

### `state not found` / state mismatch

The callback arrived without the `state` value stored in the Django session.
Typical causes: the callback was opened in a different browser or tab profile,
the session cookie was not sent (cookie domain/`Secure`/`SameSite` problem), the
user took too long and the session expired, or the app was restarted with a new
`DJANGO_SECRET_KEY` or a cleared session table mid-flow. Start the login again
from `/accounts/login/` in the same browser. If it repeats behind a proxy,
check `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` and the forwarded-proto
header.

### `iss` mismatch / wrong realm

The `iss` in the discovery document and tokens must equal `OIDC_OP_ISSUER`, and
all derived endpoints are built from that value. A container-internal hostname
(`http://keycloak:8080`), a different port or a hostname the browser cannot
reach sends the authorization redirect or token/userinfo calls to the wrong
place. Check what the realm publishes:

```bash
curl -s "$OIDC_OP_ISSUER/.well-known/openid-configuration" \
  | grep -o '"issuer":"[^"]*"'
```

That value must match `OIDC_OP_ISSUER` character for character. Note that
`mozilla-django-oidc==5.0.2` verifies the signature and nonce but not the `iss`
or `aud` claims, so a wrong-but-reachable issuer can fail late and confusingly
rather than at the callback.

### HTTP issuer on an HTTPS site

If the browser loads Django over HTTPS but `OIDC_OP_ISSUER` is `http://...`,
redirects will be blocked as mixed content or the Keycloak session cookie will
be rejected. Set the issuer to the HTTPS public URL and terminate TLS for
Keycloak as well; do not disable HTTPS checks in the client.

### CSRF or cookie problems behind a proxy

A `403` on POST (for example the logout form) or a login that loops usually means
Django sees `http` while the browser uses `https`. Set
`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, make sure the
proxy forwards `Host` and `X-Forwarded-Proto`, add the site to
`CSRF_TRUSTED_ORIGINS`, and confirm `DJANGO_ALLOWED_HOSTS` includes the public
hostname. Secure cookies on an HTTP-only setup are dropped silently.

### Login ends on the home page instead of the login page

`mozilla-django-oidc` sends handshake failures to
`LOGIN_REDIRECT_URL_FAILURE`, which is `/accounts/login/` in this project. If you
land on `/` instead, that setting is not being loaded (wrong settings module,
stale process, or an environment override). With the setting in place, a
redirect back to the login page means the handshake failed: check the Django log
for the reason (redirect URI, state, token exchange, `SuspiciousOperation` from
provisioning).

### "Password login fails" for Keycloak users

Expected. Keycloak-provisioned users and legacy accounts linked on their first
OIDC login have an unusable password, so the form at `/accounts/login/` cannot
authenticate them; they must use **Sign in with Keycloak**. Do not set a local
password on an OIDC account: the next login resets it. If someone needs local
password access, keep that as a separate staff account. They are ordinary
non-staff rows in the user list; that is not an error.

### A Keycloak user is refused or provisioned with an unexpected username

A staff/superuser email in the claims is refused by design, and an email already
bound to another `sub` is refused too; the same applies when an existing account
is moved onto an email owned by someone else. Usernames are derived from
`preferred_username` and de-duplicated, so a collision produces a suffix rather
than a second account. These refusals surface as a failed login (and an entry in
the Django log), not as a new account.

## 8. Security checklist

- [ ] Dev credentials (`Applicant123!`, `Jury123!`, the client secret, the
      Keycloak admin password) are used only on the local container.
- [ ] Keycloak runs with `start`, a real database, HTTPS and its public hostname
      configured; `start-dev` and the imported dev realm stay out of production.
- [ ] The production client uses a freshly generated secret from a secret
      manager; `teknofest/.env` is never committed or deployed.
- [ ] `OIDC_OP_ISSUER` is the exact HTTPS issuer, and the client's redirect and
      post-logout URIs are exact HTTPS URLs (no wildcards for callbacks).
- [ ] `DJANGO_DEBUG=0`, a real `DJANGO_SECRET_KEY`, correct
      `DJANGO_ALLOWED_HOSTS`, `SECURE_PROXY_SSL_HEADER`, secure session/CSRF
      cookies and HSTS are set behind TLS.
- [ ] `ModelBackend` remains enabled, and `/admin/` is restricted to staff,
      protected with strong passwords and, where possible, network/VPN access.
- [ ] Staff/superuser flags are only granted locally; the claims-to-role mapping
      only ever creates the `jury` group.
- [ ] OIDC-provisioned accounts have unusable passwords; no shared or default
      passwords exist outside Keycloak.
- [ ] Logout ends both the Django session and the Keycloak SSO session
      (RP-initiated logout), and the post-logout redirect is registered.
- [ ] Sessions and realm SSO lifetimes are aligned with policy; token renewal
      behavior is intentional.
- [ ] A database backup exists before legacy local accounts are removed.
- [ ] Dependency versions (`mozilla-django-oidc==5.0.2`, Keycloak 26.8.2) are
      tracked and updated with a test run of `main.tests_oidc`.
- [ ] Authentication failures, exceptions and provisioning refusals are logged
      and monitored, and the realm keys rotate on a schedule.
