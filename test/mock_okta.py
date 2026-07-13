#!/usr/bin/env python3
"""A tiny fake Okta `/api/v1/users` endpoint for validating import-okta-users.

Serves two pages joined by a `Link: ...; rel="next"` header so the extension's
pagination, JSON parsing, and active/inactive classification can be exercised
without touching a real Okta org. Requires an `Authorization: SSWS ...` header,
mirroring Okta, so the auth wiring is checked too.

Usage:
    python3 test/mock_okta.py            # serves on http://localhost:8799
    OKTA_MOCK_PORT=9000 python3 test/mock_okta.py

Then, in another shell (see README "Validating locally"):
    aspect auth login
    OKTA_API_TOKEN=dummy aspect import-okta-users --okta-org=http://localhost:8799
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("OKTA_MOCK_PORT", "8799"))

PAGE1 = [
    {"status": "ACTIVE", "profile": {"login": "ada@acme.com", "email": "ada@acme.com",
                                     "firstName": "Ada", "lastName": "Lovelace"}},
    {"status": "PROVISIONED", "profile": {"login": "alan@acme.com", "email": "alan@acme.com",
                                          "firstName": "Alan", "lastName": "Turing"}},
]
PAGE2 = [
    {"status": "DEPROVISIONED", "profile": {"login": "old@acme.com", "email": "old@acme.com",
                                            "firstName": "Old", "lastName": "User"}},
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def do_GET(self):
        if not self.headers.get("Authorization", "").startswith("SSWS "):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"[]")
            return

        if "after=PAGE2" in self.path:
            body, link = json.dumps(PAGE2).encode(), None
        else:
            body = json.dumps(PAGE1).encode()
            link = '<http://localhost:%d/api/v1/users?limit=200&after=PAGE2>; rel="next"' % PORT

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if link:
            self.send_header("Link", link)
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print("mock Okta on http://localhost:%d/api/v1/users" % PORT)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
