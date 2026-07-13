# `aspect import-okta-users`

An [Aspect Extension](https://github.com/aspect-extensions) (AXL) command that
syncs your **Okta** users into **Frontegg** through Aspect's `userinfo-proxy`.

It exists because the SCIM path (Okta/Auth0 → SCIM → Frontegg) isn't viable for
our setup. Instead of a hosted connector, this is **plain, reviewable source**
you drop into your own repo and run as a daily CI cron job, so your security/IT
team can audit exactly what it does before adopting it.

> [!WARNING]
> **The write path is disabled.** Mutating identity from a CI job is a
> security-sensitive operation. Pending an internal security sign-off and a
> confirmed `userinfo-proxy` contract (Aspect ticket ENG-1746), this command
> only **reads** from Okta and prints the changes it *would* make (`--dry-run`,
> the default). It does not create, modify, or deactivate anyone yet.

## What it does

1. Reads users from the Okta admin API — `GET /api/v1/users`, following Okta's
   `Link`-header pagination — and extracts `profile.login`, `profile.email`,
   `firstName`, `lastName`, and `status`.
2. Computes the reconciliation against **your** Aspect account: upsert active
   users with a role, deactivate the rest.
3. (Gated) Pushes those changes to `userinfo-proxy`, which fronts Frontegg with
   a hard-limited set of capabilities: add user, set role (**Account Admin** or
   **Account Viewer** only), remove user.

## Security model — which account gets modified

The target account is **not** a flag and **not** a request field. It is read
from the `tenant_id` claim of the JWT that `aspect auth login` issued, which the
`userinfo-proxy` re-verifies on every call. Consequences:

- You can only ever modify the **single account your signed token was minted
  for**. There is no `--account` to point at someone else's tenant, so a
  misconfigured cron cannot import users into the wrong account.
- You must `aspect auth login` as an **Account Admin** of that account. The
  proxy authorizes the caller before any write.
- Assignable roles are capped at `Account Admin` / `Account Viewer` (Frontegg
  keys `account.admin` / `account.viewer`) — the tool can never grant a
  vendor/super-admin role. The proxy authorizes writes on the caller's
  `account.admin` role claim and performs the Frontegg change with its own
  server-side vendor credentials.
- **No Frontegg token is ever handled by you.** Frontegg vendor credentials
  live server-side in `userinfo-proxy`; the client only presents its Aspect
  identity. (This is why there is no `ASPECT_APP_TOKEN` / Frontegg secret.)

## Requirements

- The [Aspect CLI](https://docs.aspect.build/) on `PATH`, logged in as an
  Account Admin (`aspect auth login`).
- Network access to your Okta org and (for the eventual write path) the Aspect
  `userinfo-proxy` endpoint.

## Credentials

| What                   | How                                                          |
| ---------------------- | ------------------------------------------------------------ |
| Aspect (the proxy)     | `aspect auth login` as an Account Admin. Read via `aspect auth`; the account scope rides in the signed token. No secret to store. |
| Okta (read users)      | `OKTA_API_TOKEN` env var. Sent to Okta as `SSWS <token>`.    |
| `OKTA_ORG`             | Okta org (`acme`) or full base URL. Or use `--okta-org`.     |

The only secret you manage is the Okta API token, and it needs **read-only**
access to users. Rotate it on your normal cadence.

## Usage

Add the extension to your `MODULE.aspect` (see [`example/`](./example)):

```starlark
axl_local_dep(name = "import_users", path = "path/to/import-users", auto_use_tasks = True)
```

Dry run (default — safe, read-only):

```sh
aspect auth login              # as an Account Admin of the target account
export OKTA_ORG=acme
export OKTA_API_TOKEN=…
aspect import-okta-users --role="Account Viewer"
```

Flags:

| Flag          | Default          | Meaning                                          |
| ------------- | ---------------- | ------------------------------------------------ |
| `--okta-org`  | `$OKTA_ORG`      | Okta org subdomain or full base URL.             |
| `--role`      | `Account Viewer` | Role on upsert (`Account Admin`/`Account Viewer`). |
| `--dry-run`   | `true`           | Print planned changes without applying them.     |
| `--proxy-url` | `$ASPECT_USERINFO_PROXY_URL` | userinfo-proxy base URL.             |
| `--profile`   | `default`        | Aspect credential profile to use.                |

## Running as a daily cron in CI

GitHub Actions example. The only secret is the Okta API token; the Aspect
identity comes from an API token piped into `aspect auth login` (mint it for a
dedicated Account Admin service identity of the target account):

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
        run: aspect import-okta-users --role="Account Viewer" # add --dry-run=false once enabled
```

## Status

Read + pagination + dry-run diff + `aspect auth`-derived account scoping:
implemented. Write path: gated on security sign-off and the `userinfo-proxy`
contract (ENG-1746).
