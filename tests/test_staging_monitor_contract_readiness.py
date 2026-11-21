"""Readiness documentation and scope contracts for G5 staging monitoring."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "G5_MONITOR_READINESS.md"


class StagingMonitorReadinessDocumentTests(unittest.TestCase):
    def test_readiness_document_distinguishes_skipped_from_health_success(self):
        text = DOC.read_text()
        self.assertIn("STAGING_BASE_URL", text)
        self.assertIn("variable de repositorio", text)
        self.assertIn("NOT READY", text)
        self.assertIn("no es éxito de health", text)
        self.assertNotIn("**APROBADO**", text)
        self.assertNotIn("beta habilitada con este monitor", text)

    def test_readiness_document_has_safe_operator_checklist(self):
        text = DOC.read_text()
        for required in (
            "Variable de repositorio",
            "environment",
            "Basic",
            "ALERT_WEBHOOK_URL",
            "rollback",
            "No usar secretos",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
