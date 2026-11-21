"""Optional, origin-scoped Basic authentication for G5 read-only probes.

The staging UI may intentionally require HTTP Basic auth while its health/API
endpoints are public. Never put credentials in command-line arguments or URLs.
Credentials are only sent in response to an HTTP Basic challenge at the exact
HTTPS origin being probed. The password is read from an environment secret.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from typing import Mapping


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
    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, f"https://{parsed.netloc}/", username, password)
    return urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(manager))
