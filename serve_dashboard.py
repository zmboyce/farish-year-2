#!/usr/bin/env python3
"""
Static file server for the Farish dashboard (e.g. Railway).
Optional HTTP Basic Auth when BASIC_AUTH_USER and BASIC_AUTH_PASSWORD are set.

Set these in your host (e.g. Railway project variables) — do not commit secrets to git.
"""
from __future__ import annotations

import base64
import binascii
import os
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def _realm() -> str:
    return os.environ.get("BASIC_AUTH_REALM", "Farish Street Dashboard")


def _auth_configured() -> bool:
    u = (os.environ.get("BASIC_AUTH_USER") or "").strip()
    p = os.environ.get("BASIC_AUTH_PASSWORD")
    p = p if p is not None else ""
    return bool(u and p)


def _valid_basic(header: str | None) -> bool:
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        raw = base64.b64decode(header.split(None, 1)[1].strip()).decode("utf-8")
    except (IndexError, ValueError, UnicodeDecodeError, binascii.Error):
        return False
    if ":" not in raw:
        return False
    u, p = raw.split(":", 1)
    expect_u = (os.environ.get("BASIC_AUTH_USER") or "").strip()
    expect_p = os.environ.get("BASIC_AUTH_PASSWORD") or ""
    return u == expect_u and p == expect_p


def make_handler() -> type[SimpleHTTPRequestHandler]:
    root = os.path.abspath(os.environ.get("HTTP_SERVER_ROOT", "."))

    class AuthStaticHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root, **kwargs)

        def _unauthorized(self) -> None:
            self.send_response(401, "Authentication required")
            self.send_header("WWW-Authenticate", f'Basic realm="{_realm()}"')
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            if _auth_configured() and not _valid_basic(self.headers.get("Authorization")):
                self._unauthorized()
                return
            super().do_GET()

        def do_HEAD(self) -> None:  # noqa: N802
            if _auth_configured() and not _valid_basic(self.headers.get("Authorization")):
                self._unauthorized()
                return
            super().do_HEAD()

        def list_directory(self, path: str) -> None:  # noqa: N802
            self.send_error(HTTPStatus.FORBIDDEN, "Directory listing is disabled")

        def log_message(self, fmt, *a) -> None:  # noqa: ANN001
            sys.stderr.write(f"[{self.address_string()}] {fmt % a}\n")

    return AuthStaticHandler


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    Handler = make_handler()
    # Allow binding on Railway / containers
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    if _auth_configured():
        print("HTTP Basic Auth: enabled", file=sys.stderr)
    else:
        print(
            "HTTP Basic Auth: disabled (set BASIC_AUTH_USER and BASIC_AUTH_PASSWORD to enable)",
            file=sys.stderr,
        )
    print(f"Serving {os.path.abspath(os.environ.get('HTTP_SERVER_ROOT', '.'))} on 0.0.0.0:{port}", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
