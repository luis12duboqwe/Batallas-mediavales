"""Contract regressions for the scheduled G5 staging monitor workflows."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

def _workflow(filename: str) -> dict:
    return yaml.safe_load((WORKFLOWS / filename).read_text())


class StagingMonitorWorkflowContractTests(unittest.TestCase):
    def test_health_monitor_requires_repository_variable_for_probe_job(self):
        text = (WORKFLOWS / "staging-health.yml").read_text()
        self.assertIn("if: ${{ vars.STAGING_BASE_URL == '' }}", text)
        self.assertIn("if: ${{ vars.STAGING_BASE_URL != '' }}", text)
        self.assertIn("STAGING_BASE_URL: ${{ vars.STAGING_BASE_URL }}", text)
        self.assertNotIn("STAGING_BASE_URL: ${{ secrets.", text)

    def test_soak_monitor_requires_repository_variable_for_probe_job(self):
        text = (WORKFLOWS / "staging-soak.yml").read_text()
        self.assertIn("if: ${{ vars.STAGING_BASE_URL == '' }}", text)
        self.assertIn("if: ${{ vars.STAGING_BASE_URL != '' }}", text)
        self.assertIn("STAGING_BASE_URL: ${{ vars.STAGING_BASE_URL }}", text)
        self.assertNotIn("STAGING_BASE_URL: ${{ secrets.", text)

    def test_readiness_jobs_are_honest_and_do_not_probe(self):
        for filename, probe_id, probe_name in (
            ("staging-health.yml", "smoke", "no staging health probe executed"),
            ("staging-soak.yml", "soak", "no staging soak probe executed"),
        ):
            with self.subTest(filename=filename):
                jobs = _workflow(filename)["jobs"]
                readiness = jobs["readiness"]
                probe = jobs[probe_id]

                self.assertEqual(readiness["if"], "${{ vars.STAGING_BASE_URL == '' }}")
                self.assertEqual(probe["if"], "${{ vars.STAGING_BASE_URL != '' }}")
                self.assertIn("NOT READY", readiness["name"])
                self.assertIn(probe_name, readiness["name"])

                readiness_text = "\n".join(
                    str(step.get("run", "")) for step in readiness["steps"]
                )
                self.assertIn("NOT READY", readiness_text)
                self.assertIn("does not provide", readiness_text)
                for step in readiness["steps"]:
                    run_text = str(step.get("run", ""))
                    self.assertNotIn("python3 ops/", run_text)

                probe_text = "\n".join(
                    str(step.get("run", "")) for step in probe["steps"]
                )
                self.assertIn("python3 ops/", probe_text)

    def test_optional_basic_auth_contract_is_consistent_between_monitors(self):
        for filename in ("staging-health.yml", "staging-soak.yml"):
            with self.subTest(filename=filename):
                text = (WORKFLOWS / filename).read_text()
                self.assertIn(
                    "STAGING_BASIC_AUTH_USERNAME: ${{ vars.STAGING_BASIC_AUTH_USERNAME }}",
                    text,
                )
                self.assertIn(
                    "STAGING_BASIC_AUTH_PASSWORD: ${{ secrets.STAGING_BASIC_AUTH_PASSWORD }}",
                    text,
                )

    def test_probe_failures_remain_workflow_failures_and_alert_is_optional(self):
        for filename in ("staging-health.yml", "staging-soak.yml"):
            with self.subTest(filename=filename):
                text = (WORKFLOWS / filename).read_text()
                self.assertIn("if: ${{ failure() }}", text)
                self.assertIn("ALERT_WEBHOOK_URL: ${{ secrets.ALERT_WEBHOOK_URL }}", text)
                self.assertIn("python3 ops/load_smoke.py", text)
                self.assertIn("python3 ops/smoke_http.py", text)

    def test_workflows_do_not_contain_external_staging_urls(self):
        for filename in ("staging-health.yml", "staging-soak.yml"):
            with self.subTest(filename=filename):
                text = (WORKFLOWS / filename).read_text()
                self.assertNotIn("https://staging.", text)
                self.assertNotIn("http://staging.", text)


if __name__ == "__main__":
    unittest.main()
