"""G5 release and monitoring budgets must reject NaN/Inf before network or deploy."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
from preflight import validate  # noqa: E402


def safe_test_environment() -> dict[str, str]:
    sha = "0123456789abcdef0123456789abcdef01234567"
    return {
        "APP_ENV": "staging",
        "SECRET_KEY": "g5-test-only-random-looking-0123456789012345",
        "DB_URL": "postgresql+psycopg://user:test@database:5432/g5_test",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "synthetic-test-only",
        "POSTGRES_DB": "g5_test",
        "FRONTEND_URL": "https://staging.example.invalid",
        "PUBLIC_BASE_URL": "https://staging.example.invalid",
        "PUBLIC_HOST": "staging.example.invalid",
        "TLS_EMAIL": "test@example.invalid",
        "HTTP_PORT": "18080",
        "HTTPS_PORT": "18443",
        "CORS_ORIGINS": "https://staging.example.invalid",
        "SMTP_HOST": "mail.example.invalid",
        "FROM_EMAIL": "test@example.invalid",
        "SUPPORT_CONTACT": "test@example.invalid",
        "BACKEND_IMAGE": f"example.invalid/g5/backend:{sha}",
        "FRONTEND_IMAGE": f"example.invalid/g5/frontend:{sha}",
        "BACKUP_DIR": "/tmp/g5-test-only",
        "BACKUP_RETENTION_DAYS": "1",
        "LOAD_DURATION_SECONDS": "10",
        "LOAD_CONCURRENCY": "6",
        "LOAD_TARGET_RPS": "6",
        "MAX_P95_MS": "750",
        "MAX_ERROR_RATE": "0.005",
    }


class ProtectedGateBudgetTests(unittest.TestCase):
    def test_normal_protected_values_pass(self):
        self.assertEqual(validate(safe_test_environment()), [])

    def test_release_rejects_nonfinite_numbers_and_zero(self):
        for key in ("LOAD_DURATION_SECONDS", "LOAD_CONCURRENCY", "LOAD_TARGET_RPS", "MAX_P95_MS"):
            for value in ("NaN", "Infinity", "-Infinity", "0", "-1", "not-a-number"):
                with self.subTest(key=key, value=value):
                    env = safe_test_environment()
                    env[key] = value
                    errors = validate(env)
                    self.assertTrue(any(key in error for error in errors), (key, value, errors))

    def test_release_caps_monitor_below_proxy_rate(self):
        env = safe_test_environment()
        env["LOAD_TARGET_RPS"] = "10.01"
        self.assertTrue(any("LOAD_TARGET_RPS" in error for error in validate(env)))
        env["LOAD_TARGET_RPS"] = "10"
        self.assertEqual(validate(env), [])

    def test_release_rejects_nonfinite_error_rate(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                env = safe_test_environment()
                env["MAX_ERROR_RATE"] = value
                self.assertTrue(any("MAX_ERROR_RATE" in error for error in validate(env)))

    def test_probes_fail_before_network_with_invalid_budgets(self):
        cases = (
            ("smoke_http.py", ("--max-p95-ms", "NaN")),
            ("smoke_http.py", ("--max-p95-ms", "Infinity")),
            ("smoke_http.py", ("--max-p95-ms", "0")),
            ("smoke_http.py", ("--timeout", "-1")),
            ("load_smoke.py", ("--max-p95-ms", "NaN")),
            ("load_smoke.py", ("--max-p95-ms", "Infinity")),
            ("load_smoke.py", ("--max-p95-ms", "-1")),
            ("load_smoke.py", ("--max-error-rate", "NaN")),
            ("load_smoke.py", ("--timeout", "0")),
        )
        for script, args in cases:
            with self.subTest(script=script, args=args):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "ops" / script),
                        "--base-url",
                        "https://127.0.0.1:19999",
                        *args,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(args[0], result.stderr)


if __name__ == "__main__":
    unittest.main()
