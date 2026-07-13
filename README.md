# `aspect import-okta-users`

An [Aspect Extension](https://github.com/aspect-extensions) (AXL) command that
syncs your **Okta** users into your Aspect account in **Frontegg**.

It exists because the SCIM path (Okta/Auth0 → SCIM → Frontegg) isn't viable for
our setup. Instead of a hosted connector, this is **plain, reviewable source**
you drop into your own repo and run as a daily CI cron job, so your security/IT
team can audit exactly what it does before adopting it.

It talks to Frontegg **directly** using the credential from `aspect auth` — no
intermediary service and no Frontegg secret to manage.

> [!IMPORTANT]
> This **applies changes by default** (invite / deactivate in your Frontegg
> account) — it's built to run unattended as a daily cron. Pass `--dry-run` to
> preview the reconciliation without writing. Mutating identity from CI should
> get a security-team review first.

## What it does

1. Reads users from the Okta admin API — `GET /api/v1/users`, following Okta's
   `Link`-header pagination — and extracts `profile.login`, `profile.email`,
   `firstName`, `lastName`, and `status`.
2. Reconciles them against **your** Aspect account: active Okta users
   (`ACTIVE`/`PROVISIONED`) are invited with a role; the rest are removed.
3. Writes to Frontegg with the Account Admin's `aspect auth` token:
   - invite/create — `POST /identity/resources/users/v2` (role assigned via
     `roleIds`, invite email suppressed by default),
   - deactivate — look up by email, then `DELETE /identity/resources/users/v1/{id}`.

## Security model — which account gets modified

The target account is **not** a flag and **not** a request field. Frontegg
derives it from the `frontegg-tenant-id` of your signed `aspect auth` token, and
only honors the write because that token carries the tenant **and** the
`account.admin` role. Consequences:

- You can only ever modify the **single account your token was minted for**.
  There is no `--account`, so a misconfigured cron cannot touch the wrong
  account.
- You must `aspect auth login` as an **Account Admin** of that account.
- Assignable roles are capped at `viewer` / `admin` (Frontegg keys
  `account.viewer` / `account.admin`) — never a vendor/super-admin role. Default
  is `viewer`; granting `admin` requires `--role admin` explicitly.
- **No Frontegg vendor secret is ever handled.** The client presents only the
  Account Admin's own Aspect identity; Frontegg authorizes the tenant-scoped
  user management from that user's `account.admin` permissions.
- Invites **do not email** users by default. Pass `--send-invite-email` to opt in.

## Requirements

- The [Aspect CLI](https://docs.aspect.build/) on `PATH`, logged in as an
  Account Admin (`aspect auth login`).
- Network access to your Okta org and your Aspect/Frontegg host.

## Credentials & config

| What            | How                                                                        |
| --------------- | -------------------------------------------------------------------------- |
| Aspect identity | `aspect auth login` as an Account Admin. Read via `aspect auth`; the account scope rides in the signed token. No secret to store. |
| `OKTA_API_TOKEN`| Okta API token, **read-only** access to users. Sent as `SSWS <token>`.     |
| `OKTA_ORG`      | Okta org (`acme`), hostname (`acme.okta.com`), or URL. Or `--okta-org`.    |
| `FRONTEGG_URL`  | Your Aspect/Frontegg host (same domain your token was issued by, e.g. `https://auth.aspect.build`). Or `--frontegg-url`. Required for writes. |

The only secret you manage is the read-only Okta API token. Rotate it on your
normal cadence.

## Usage

Add the extension to your `MODULE.aspect` (see [`example/`](./example)):

```starlark
axl_local_dep(name = "import_users", path = "path/to/import-users", auto_use_tasks = True)
```

Preview (read-only — pass `--dry-run`):

```sh
aspect auth login              # as an Account Admin of the target account
export OKTA_ORG=acme
export OKTA_API_TOKEN=…
aspect import-okta-users --dry-run
```

Apply (the default):

```sh
aspect import-okta-users --frontegg-url=https://auth.aspect.build
```

Flags:

| Flag                  | Default     | Meaning                                          |
| --------------------- | ----------- | ------------------------------------------------ |
| `--okta-org`          | `$OKTA_ORG` | Okta org subdomain, hostname, or full URL.       |
| `--role`              | `viewer`    | Role on upsert: `viewer` or `admin`.             |
| `--dry-run`           | `false`     | Preview the reconciliation without writing.      |
| `--frontegg-url`      | `$FRONTEGG_URL` | Aspect/Frontegg host. Required for writes.   |
| `--send-invite-email` | `false`     | Send Frontegg's invite email (off by default).   |
| `--profile`           | `default`   | Aspect credential profile to use.                |

## Running as a daily cron in CI

GitHub Actions example. Secrets: the read-only Okta token, plus an Aspect API
token (mint it for a dedicated Account Admin service identity of the account):

```yaml
name: sync-okta-users
on:
  schedule:
    - cron: "0 7 * * *" # daily 07:00 UTC
  workflow_dispatch:
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Install Aspect CLI
        uses: jaxxstorm/action-install-gh-release@v2.1.0
        with:
          repo: aspect-build/aspect-cli
          asset-name: aspect-cli
          platform: unknown_linux
          arch: x86_64
          extension-matching: disable
          rename-to: aspect
          chmod: 0755
      - name: Log in to Aspect (Account Admin, scopes to that account only)
        run: printf '%s' "${ASPECT_API_TOKEN}" | aspect auth login --with-api-token
        env:
          ASPECT_API_TOKEN: ${{ secrets.ASPECT_API_TOKEN }}
      - name: Sync
        env:
          OKTA_ORG: ${{ vars.OKTA_ORG }}
          OKTA_API_TOKEN: ${{ secrets.OKTA_API_TOKEN }}
          FRONTEGG_URL: ${{ vars.FRONTEGG_URL }}
        run: aspect import-okta-users # applies by default
```

## Validating locally

The read + dry-run path runs end-to-end against a bundled fake Okta, so you see
the exact reconciliation output without a real org or any writes.

```sh
# 1. Start the fake Okta (serves two paginated pages of users).
python3 test/mock_okta.py &

# 2. Authenticate to Aspect (the tool refuses to run otherwise).
aspect auth login

# 3. Point the tool at the mock. --dry-run previews without writing;
#    OKTA_API_TOKEN can be any non-empty value.
OKTA_API_TOKEN=dummy aspect import-okta-users --okta-org=http://localhost:8799 --dry-run
```

Expected dry-run output:

```
Planned reconciliation for account <your-tenant> (role=viewer):
  + upsert     ada@acme.com <ada@acme.com> (Ada Lovelace)
  + upsert     alan@acme.com <alan@acme.com> (Alan Turing)
  - deactivate old@acme.com <old@acme.com> [DEPROVISIONED]
```

For a real run, drop `--dry-run` and use `--okta-org=<your-org>`, a real
`OKTA_API_TOKEN`, and `--frontegg-url=<your-host>`.

### Targeting a non-production Aspect environment

Select the Aspect auth environment with `__ASPECT_ENVIRONMENT__` (`production`
default, or `staging` / `dev`). It's resolved every command and credentials are
keyed by auth domain, so set it for **both** the login and the run, and use a
distinct `--profile` to keep it beside your prod login:

```sh
__ASPECT_ENVIRONMENT__=staging aspect auth login --profile staging
__ASPECT_ENVIRONMENT__=staging OKTA_API_TOKEN=dummy \
  aspect import-okta-users --okta-org=http://localhost:8799 --profile staging --dry-run
```

## Status

Read + pagination + dry-run diff, `aspect auth`-derived account scoping, and the
write path (invite with role + deactivate, direct to Frontegg) are implemented
and validated against a live Okta trial + Frontegg account. Mutating identity
from CI should still get a security-team +1.
