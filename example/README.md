# `aspect import-okta-users` example

    # This is executable Markdown that's tested on CI.
    set -o errexit -o nounset -o xtrace
    alias ~~~=":<<'~~~sh'";:<<'~~~sh'

## Try it out

The Okta API token comes from the environment (`OKTA_API_TOKEN`) and the Aspect
identity from `aspect auth` — never from the command line. With no Okta token
set the command should refuse to run, which is what this test asserts, so CI
never touches a real Okta org or the userinfo-proxy.

~~~sh
# No OKTA_API_TOKEN in the environment -> the command must fail cleanly.
output="$(env -u OKTA_API_TOKEN aspect import-okta-users --okta-org=example 2>&1 || true)"

echo "${output}" | grep -q "missing OKTA_API_TOKEN" || {
    echo >&2 "Wanted an error mentioning 'missing OKTA_API_TOKEN' but got: '${output}'"
    exit 1
}
~~~
