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
2. Computes the reconciliation against your Aspect account: upsert active users
   with a role, deactivate the rest.
3. (Gated) Pushes those changes to `userinfo-proxy`, which fronts Frontegg with
   a hard-limited set of capabilities: add user, set role (**Admin** or
   **Viewer** only), remove user — scoped to a single account.

## Requirements

- The [Aspect CLI](https://docs.aspect.build/) on `PATH`.
- Network access to your Okta org and (for the eventual write path) the Aspect
  `userinfo-proxy` endpoint.
- `curl` available (present in standard CI images).

## Tokens

Secrets are read **only** from the environment — never passed on the command
line (where they'd leak into process listings and CI logs):

| Variable                    | Purpose                                              |
| --------------------------- | ---------------------------------------------------- |
| `OKTA_API_TOKEN`            | Okta API token (read users). Sent as `SSWS <token>`. |
| `ASPECT_APP_TOKEN`          | Aspect app token (auth to `userinfo-proxy`).         |
| `OKTA_ORG`                  | Okta org (`acme`) or full base URL. Or use `--okta-org`. |
| `ASPECT_USERINFO_PROXY_URL` | Proxy base URL. Or use `--proxy-url`.                |

Scope both tokens as narrowly as possible. The Okta token needs only read
access to users; the Aspect token should be scoped to the single target
account. Rotate them on your normal secret-rotation cadence.

## Usage

Add the extension to your `MODULE.aspect` (see [`example/`](./example)):

```starlark
axl_local_dep(name = "import_users", path = "path/to/import-users", auto_use_tasks = True)
```

Dry run (default — safe, read-only):

```sh
export OKTA_ORG=acme
export OKTA_API_TOKEN=…
aspect import-okta-users --role=Viewer
```

Flags:

| Flag          | Default    | Meaning                                       |
| ------------- | ---------- | --------------------------------------------- |
| `--okta-org`  | `$OKTA_ORG`| Okta org subdomain or full base URL.          |
| `--role`      | `Viewer`   | Role to assign on upsert (`Admin`/`Viewer`).  |
| `--dry-run`   | `true`     | Print planned changes without applying them.  |
| `--proxy-url` | `$ASPECT_USERINFO_PROXY_URL` | userinfo-proxy base URL.     |

## Running as a daily cron in CI

GitHub Actions example — store the tokens as repository secrets:

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
      - name: Sync
        env:
          OKTA_ORG: ${{ vars.OKTA_ORG }}
          OKTA_API_TOKEN: ${{ secrets.OKTA_API_TOKEN }}
          ASPECT_APP_TOKEN: ${{ secrets.ASPECT_APP_TOKEN }}
        run: aspect import-okta-users --role=Viewer # add --dry-run=false once enabled
```

## Status

Read + pagination + dry-run diff: implemented. Write path: gated on security
sign-off and the `userinfo-proxy` contract (ENG-1746).
