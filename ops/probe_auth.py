"""Optional, origin-scoped Basic authentication for G5 read-only probes.

The staging UI may intentionally require HTTP Basic auth while its health/API
endpoints are public. Never put credentials in command-line arguments or URLs.
Credentials are only sent in response to an HTTP Basic challenge at the exact
HTTPS origin being probed. The password is read from an environment secret.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Mapping


class _HTTPSOriginPasswordManager(urllib.request.HTTPPasswordMgrWithDefaultRealm):
    """Reject HTTP downgrade and cross-origin challenges, including port changes."""

    def __init__(self, origin: str) -> None:
        super().__init__()
        parsed = urllib.parse.urlsplit(origin)
        self._hostname = parsed.hostname
        self._port = parsed.port or 443

    def find_user_password(self, realm: str | None, authuri: str) -> tuple[str | None, str | None]:
        try:
            requested = urllib.parse.urlsplit(authuri)
            allowed = (
                requested.scheme.lower() == "https"
                and requested.hostname == self._hostname
                and (requested.port or 443) == self._port
            )
        except ValueError:
            allowed = False
        if not allowed:
            return None, None
        return super().find_user_password(realm, authuri)


class _HTTPSOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Do not forward Authorization on redirects to another origin."""

    def __init__(self, origin: str) -> None:
        self._origin = self._destination(origin)

    @staticmethod
    def _destination(url: str) -> tuple[str, str | None, int | None] | None:
        try:
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme.lower() != "https" or not parsed.hostname:
                return None
            if parsed.username is not None or parsed.password is not None:
                return None
            return ("https", parsed.hostname, parsed.port or 443)
        except ValueError:
            return None

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if self._destination(newurl) != self._origin:
            raise urllib.error.HTTPError(
                req.full_url, code, "cross-origin staging redirect denied", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_probe_opener(
    base_url: str, environ: Mapping[str, str] | None = None
) -> urllib.request.OpenerDirector:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("do not embed credentials in the staging URL")

    values = os.environ if environ is None else environ
    username = values.get("STAGING_BASIC_AUTH_USERNAME", "")
    password = values.get("STAGING_BASIC_AUTH_PASSWORD", "")

    if not username and not password:
        return urllib.request.build_opener()
    if not username or not password:
        raise ValueError("both STAGING_BASIC_AUTH_USERNAME and STAGING_BASIC_AUTH_PASSWORD are required")
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("staging Basic auth requires an https:// URL")
    if ":" in username or "\r" in username or "\n" in username or "\r" in password or "\n" in password:
        raise ValueError("invalid staging Basic auth configuration")

    # The password manager is scoped to this HTTPS origin, never to other hosts
    # reached via a redirect. Do not add Authorization as a global HTTP header.
    origin = f"https://{parsed.netloc}/"
    manager = _HTTPSOriginPasswordManager(origin)
    manager.add_password(None, origin, username, password)
    return urllib.request.build_opener(
        urllib.request.HTTPBasicAuthHandler(manager), _HTTPSOriginRedirectHandler(origin)
    )
