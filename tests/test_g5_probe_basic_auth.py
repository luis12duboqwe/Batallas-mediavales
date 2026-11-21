"""G5 staging probes may authenticate to a protected preview without a secret leak."""

from __future__ import annotations

import sys
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))

import load_smoke  # noqa: E402
import smoke_http  # noqa: E402
from probe_auth import build_probe_opener  # noqa: E402


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"version":"test"}'


class _RecordingOpener:
    def __init__(self):
        self.urls = []

    def open(self, url, timeout):
        self.urls.append((url, timeout))
        return _Response()


class ProbeBasicAuthTests(unittest.TestCase):
    def test_unconfigured_probe_does_not_require_credentials(self):
        opener = build_probe_opener("https://preview.example/", {})
        self.assertFalse(
            any(isinstance(handler, urllib.request.HTTPBasicAuthHandler) for handler in opener.handlers)
        )

    def test_partial_credentials_fail_closed_without_exposing_password(self):
        for values in (
            {"STAGING_BASIC_AUTH_USERNAME": "visitor"},
            {"STAGING_BASIC_AUTH_PASSWORD": "private-value"},
        ):
            with self.subTest(values=list(values)):
                with self.assertRaisesRegex(ValueError, "both STAGING_BASIC_AUTH"):
                    build_probe_opener("https://preview.example/", values)

    def test_reject_insecure_auth_url_and_embedded_credentials(self):
        credentials = {
            "STAGING_BASIC_AUTH_USERNAME": "visitor",
            "STAGING_BASIC_AUTH_PASSWORD": "private-value",
        }
        for url in ("http://preview.example/", "https://visitor:secret@preview.example/"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    build_probe_opener(url, credentials)

    def test_password_manager_only_matches_exact_https_origin(self):
        opener = build_probe_opener(
            "https://preview.example:8443/",
            {
                "STAGING_BASIC_AUTH_USERNAME": "visitor",
                "STAGING_BASIC_AUTH_PASSWORD": "private-value",
            },
        )
        handler = next(
            handler for handler in opener.handlers
            if isinstance(handler, urllib.request.HTTPBasicAuthHandler)
        )
        self.assertEqual(
            handler.passwd.find_user_password(None, "https://preview.example:8443/inbox/"),
            ("visitor", "private-value"),
        )
        for wrong in (
            "http://preview.example:8443/inbox/",
            "https://preview.example:8444/inbox/",
            "https://other.example:8443/inbox/",
        ):
            with self.subTest(wrong=wrong):
                self.assertEqual(handler.passwd.find_user_password(None, wrong), (None, None))

    def test_invalid_credentials_fail_without_echoing_secret(self):
        for user, password in (("vis:itor", "abc"), ("visitor", "pw\r\nHeader:evil")):
            with self.subTest(user=user):
                with self.assertRaisesRegex(ValueError, "invalid staging Basic auth"):
                    build_probe_opener(
                        "https://preview.example/",
                        {"STAGING_BASIC_AUTH_USERNAME": user, "STAGING_BASIC_AUTH_PASSWORD": password},
                    )

    def test_smoke_request_uses_configured_opener(self):
        opener = _RecordingOpener()
        status, body, elapsed_ms = smoke_http.request(
            "https://preview.example/health", 3.0, opener=opener
        )
        self.assertEqual((status, body), (200, b'{"version":"test"}'))
        self.assertGreaterEqual(elapsed_ms, 0)
        self.assertEqual(opener.urls, [("https://preview.example/health", 3.0)])

    def test_load_request_uses_configured_opener(self):
        opener = _RecordingOpener()
        status, elapsed_ms = load_smoke.one_request(
            "https://preview.example/api/economy/balance_preview", 3.0, opener=opener
        )
        self.assertEqual(status, 200)
        self.assertGreaterEqual(elapsed_ms, 0)
        self.assertEqual(len(opener.urls), 1)


if __name__ == "__main__":
    unittest.main()
