import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ops.g5_staging_evidence import (
    AGES, CI_G5_STEPS, CI_JOBS, CUTOVER_CASES, MAX_JSON_BYTES,
    validate_approval, validate_evidence,
)


NOW = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 40
HASH = "b" * 64
SOURCE_SHA = "c" * 40


def stamp(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def fixture(origin="real"):
    records = {
        name: {
            "release_sha": SHA, "environment_id": "staging-1", "origin": origin,
            "reference": name, "observed_at": stamp(NOW - timedelta(hours=2)), "result": "pass",
        }
        for name in AGES
    }
    for name in ("ci_validation", "ci_journeys"):
        records[name].update(completed=True, conclusion="success",
                             jobs={job: {"executed": True, "conclusion": "success"} for job in CI_JOBS[name]},
                             observed_at=stamp(NOW - timedelta(hours=5)))
    records["ci_validation"]["g5_image_steps"] = {
        step: {"executed": True, "conclusion": "success"} for step in CI_G5_STEPS
    }
    images = {key: "sha256:" + digit * 64 for key, digit in (
        ("source_backend_image", "1"), ("source_frontend_image", "2"),
        ("target_backend_image", "3"), ("target_frontend_image", "4"))}
    records["deploy"].update(workflow_executed=True, immutable=True,
                             migration_succeeded=True, deployed_sha=SHA,
                             source_release_sha=SOURCE_SHA, **images,
                             observed_at=stamp(NOW - timedelta(hours=3)))
    records["https"].update(dns_verified=True, tls_verified=True, hostname_verified=True, https_verified=True)
    records["smtp"].update(real_provider=True, test_recipient_only=True, delivery_verified=True)
    records["migration"].update(staging_source=True, recoverable_copy=True, upgrade_verified=True,
                                backup_sha256=HASH, observed_at=stamp(NOW - timedelta(hours=4)))
    identities = {
        role + "_identity": {field: role + "-" + field for field in ("cluster", "container", "network", "volume")}
        for role in ("source", "clone", "witness")
    }
    cases = {}
    for name, phase in CUTOVER_CASES.items():
        cases[name] = {
            "phase": phase, "reference": "case-" + name, "failure_injected": True, "isolated": True,
            "sql_exclusion_continuous": True, "edge_exclusion_continuous": True,
            "docker_exclusion_continuous": True, "privileged_exclusion_continuous": True,
            "no_lost_commits": True, "no_stale_restore": True, "recovery_required": True,
            "origin": origin, "environment_id": "staging-1",
            "source_release_sha": SOURCE_SHA, "target_release_sha": SHA,
            **images,
            "barrier_started_at": stamp(NOW - timedelta(minutes=250)),
            "failure_at": stamp(NOW - timedelta(minutes=240)),
            "barrier_ended_at": stamp(NOW - timedelta(minutes=230)),
        }
        if phase == "postcommit":
            cases[name].update(committed_at=stamp(NOW - timedelta(minutes=245)),
                               restore_forbidden_after_commit=True)
        else:
            cases[name]["commit_not_recorded"] = True
    records["protected_cutover"].update(
        isolated_rehearsal=True, sql_exclusion_continuous=True, edge_exclusion_continuous=True,
        docker_exclusion_continuous=True, privileged_exclusion_continuous=True, external_writers_excluded=True,
        snapshot_external=True, snapshot_verified=True, logical_clone_verified=True,
        no_lost_commits=True, no_stale_restore=True, committed_writes_preserved=True,
        concurrent_write_blocked=True, no_early_reopen=True, restore_forbidden_after_commit=True,
        source_release_sha=SOURCE_SHA, target_release_sha=SHA,
        **images, **copy.deepcopy(identities), snapshot_sha256=HASH, clone_backup_sha256=HASH,
        rpo_seconds=0, barrier_started_at=stamp(NOW - timedelta(minutes=270)),
        snapshot_captured_at=stamp(NOW - timedelta(minutes=260)),
        snapshot_verified_at=stamp(NOW - timedelta(minutes=255)),
        clone_verified_at=stamp(NOW - timedelta(minutes=250)),
        committed_at=stamp(NOW - timedelta(minutes=220)),
        barrier_ended_at=stamp(NOW - timedelta(minutes=210)),
        observed_at=stamp(NOW - timedelta(minutes=200)), failure_matrix=cases)
    metrics = {"requests": 1000, "errors": 0, "server_errors": 0, "p95_ms": 750}
    for name, trigger in (("health_manual", "manual"), ("health_schedule", "schedule")):
        start = NOW - timedelta(minutes=160 if trigger == "manual" else 140)
        records[name].update(trigger=trigger, repository_url_configured=True, job_executed=True,
                             smoke_executed=True, load_executed=True, job_conclusion="success",
                             load_duration_seconds=10, smoke_metrics=copy.deepcopy(metrics),
                             load_metrics=copy.deepcopy(metrics), started_at=stamp(start),
                             ended_at=stamp(start + timedelta(minutes=1)),
                             observed_at=stamp(start + timedelta(minutes=2)))
    records["soak"].update(job_executed=True, load_executed=True, smoke_executed=True, server_metrics_reviewed=True,
                           no_duplicate_effects=True, job_conclusion="success", duration_seconds=3600,
                           planned_duration_seconds=3600, capacity_scope="controlled",
                           load_metrics=copy.deepcopy(metrics), smoke_metrics=copy.deepcopy(metrics), api_p95_ms=299.9,
                           started_at=stamp(NOW - timedelta(minutes=170)),
                           ended_at=stamp(NOW - timedelta(minutes=110)),
                           observed_at=stamp(NOW - timedelta(minutes=109)))
    records["alerts"].update(api=True, worker=True, database=True, failure_visible=True,
                             alert_tested=True, logs_reviewed=True)
    records["backup"].update(external_copy=True, checksum_verified=True, retention_verified=True, sha256=HASH,
                             captured_at=stamp(NOW - timedelta(minutes=110)),
                             observed_at=stamp(NOW - timedelta(minutes=100)))
    records["clone_restore"].update(isolated=True, fixture_mutated=True, restore_verified=True,
                                    data_verified=True, backup_sha256=HASH, clone_id="clone-1",
                                    observed_at=stamp(NOW - timedelta(minutes=90)), **copy.deepcopy(identities))
    records["rollback"].update(isolated=True, application_verified=True, database_verified=True,
                               smoke_verified=True, clone_id="clone-1", backup_sha256=HASH,
                               rpo_seconds=0, rto_seconds=600,
                               recovery_point_at=stamp(NOW - timedelta(minutes=110)),
                               last_commit_at=stamp(NOW - timedelta(minutes=110)),
                               incident_at=stamp(NOW - timedelta(minutes=80)),
                               service_restored_at=stamp(NOW - timedelta(minutes=70)),
                               observed_at=stamp(NOW - timedelta(minutes=60)))
    records["blockers"].update(inventory_complete=True, p0_open=0, p1_open=0,
                               p2_156="resolved", p2_156_reference="p2-decision",
                               observed_at=stamp(NOW - timedelta(minutes=30)))
    records["policy"].update(support=True, privacy=True, terms=True, retention=True, operator_details=True)
    return {"release_sha": SHA, "main_head_sha": SHA, "environment_id": "staging-1",
            "origin": origin, "records": records}


def approval():
    digest = hashlib.sha256(json.dumps(fixture(), sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()
    return {"release_sha": SHA, "environment_id": "staging-1", "origin": "real",
            "decision": "approve", "owner_id": "owner", "reference": "approval-1",
            "evidence_sha256": digest, "approved_at": stamp(NOW - timedelta(minutes=10))}


class EvidenceTests(unittest.TestCase):
    def test_complete_real_and_synthetic_never_grant_go(self):
        self.assertEqual(validate_evidence(fixture(), now=NOW), {"status": "REVIEW_REQUIRED", "blockers": []})
        self.assertEqual(validate_evidence(fixture("synthetic"), now=NOW)["status"], "SYNTHETIC_ONLY")
        self.assertEqual(validate_approval(fixture(), approval(), now=NOW),
                         {"status": "NO_GO", "approval_declaration": "REVIEW_REQUIRED", "blockers": []})
        self.assertEqual(validate_approval(fixture("synthetic"), approval(), now=NOW)["approval_declaration"],
                         "INCOMPLETE")

    def test_missing_and_invalid_records_fail_closed(self):
        for name in AGES:
            for value in (None, {}, "pass"):
                with self.subTest(name=name, value=value):
                    doc = fixture()
                    doc["records"][name] = value
                    self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        for doc in (None, [], {}, {"records": []}):
            self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")

    def test_failures_and_discrepancies(self):
        cases = [
            ("ci_validation", "conclusion", "skipped"),
            ("ci_journeys", "completed", False),
            ("deploy", "deployed_sha", "c" * 40),
            ("deploy", "immutable", False),
            ("https", "tls_verified", False),
            ("smtp", "real_provider", False),
            ("smtp", "test_recipient_only", False),
            ("health_manual", "job_executed", False),
            ("health_schedule", "job_conclusion", "skipped"),
            ("health_schedule", "repository_url_configured", False),
            ("health_schedule", "trigger", "manual"),
            ("health_manual", "load_duration_seconds", 9),
            ("soak", "duration_seconds", 30),
            ("soak", "planned_duration_seconds", 60),
            ("soak", "smoke_executed", False),
            ("soak", "started_at", stamp(NOW - timedelta(minutes=120))),
            ("soak", "api_p95_ms", 300),
            ("alerts", "alert_tested", False),
            ("migration", "recoverable_copy", False),
            ("backup", "external_copy", False),
            ("clone_restore", "backup_sha256", "c" * 64),
            ("clone_restore", "clone_id", "staging-1"),
            ("rollback", "clone_id", "other"),
            ("rollback", "database_verified", False),
            ("rollback", "rpo_seconds", 86401),
            ("rollback", "rto_seconds", 14401),
            ("rollback", "rto_seconds", 0),
            ("rollback", "last_commit_at", stamp(NOW)),
            ("blockers", "p0_open", 1),
            ("blockers", "p1_open", 1),
            ("blockers", "inventory_complete", False),
            ("blockers", "p2_156", "open"),
            ("blockers", "p2_156_reference", ""),
            ("policy", "terms", False),
        ]
        for name, field, value in cases:
            with self.subTest(name=name, field=field):
                doc = fixture()
                doc["records"][name][field] = value
                self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")

    def test_metrics_and_untrusted_types(self):
        for field, value in (("requests", 0), ("requests", True), ("errors", 6),
                             ("errors", -1), ("server_errors", 1), ("p95_ms", 751),
                             ("p95_ms", float("nan")), ("p95_ms", "0")):
            for metric in ("smoke_metrics", "load_metrics"):
                with self.subTest(field=field, metric=metric, value=value):
                    doc = fixture()
                    doc["records"]["health_manual"][metric][field] = value
                    self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        doc = fixture()
        del doc["records"]["health_manual"]["smoke_metrics"]
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        doc = fixture()
        doc["records"]["health_manual"]["smoke_metrics"]["errors"] = 1
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        doc = fixture()
        doc["records"]["health_manual"]["load_metrics"]["errors"] = 5
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "REVIEW_REQUIRED")

    def test_identity_freshness_and_order(self):
        doc = fixture()
        doc["main_head_sha"] = "c" * 40
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        for name in AGES:
            for field, value in (("release_sha", "c" * 40), ("environment_id", "other"),
                                 ("origin", "synthetic"), ("reference", "https://private"),
                                 ("observed_at", stamp(NOW + timedelta(seconds=1))),
                                 ("observed_at", stamp(NOW - timedelta(days=AGES[name], seconds=1)))):
                with self.subTest(name=name, field=field, value=value):
                    doc = fixture()
                    doc["records"][name][field] = value
                    self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        for first, second in (("ci_validation", "deploy"), ("deploy", "https"),
                              ("health_manual", "health_schedule"), ("backup", "clone_restore"),
                              ("clone_restore", "rollback")):
            doc = fixture()
            doc["records"][first]["observed_at"] = stamp(NOW - timedelta(minutes=1))
            doc["records"][second]["observed_at"] = stamp(NOW - timedelta(minutes=2))
            self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        doc = fixture()
        doc["records"]["https"]["reference"] = doc["records"]["smtp"]["reference"]
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")

    def test_approval_is_separate_and_fresh(self):
        for field, value in (("decision", "approve?"), ("owner_id", ""), ("origin", "synthetic"),
                             ("release_sha", "c" * 40), ("environment_id", "other"),
                             ("evidence_sha256", "d" * 64),
                             ("reference", "https"), ("approved_at", stamp(NOW - timedelta(days=2))),
                             ("approved_at", stamp(NOW + timedelta(seconds=1))),
                             ("approved_at", stamp(NOW - timedelta(hours=4)))):
            with self.subTest(field=field):
                declaration = approval()
                declaration[field] = value
                self.assertEqual(validate_approval(fixture(), declaration, now=NOW)["approval_declaration"],
                                 "INCOMPLETE")
        self.assertEqual(validate_approval(fixture(), None, now=NOW)["status"], "NO_GO")
        declaration = approval()
        declaration["reference"] = fixture()["records"]["protected_cutover"]["failure_matrix"]["after_commit"]["reference"]
        self.assertEqual(validate_approval(fixture(), declaration, now=NOW)["approval_declaration"], "INCOMPLETE")

    def test_every_mandatory_ci_job_and_step_must_run(self):
        for workflow, jobs in CI_JOBS.items():
            for job in jobs:
                for bad in (None, {"executed": False, "conclusion": "success"},
                            {"executed": True, "conclusion": "skipped"}):
                    with self.subTest(workflow=workflow, job=job, bad=bad):
                        doc = fixture()
                        doc["records"][workflow]["jobs"][job] = bad
                        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        for step in CI_G5_STEPS:
            doc = fixture()
            doc["records"]["ci_validation"]["g5_image_steps"][step]["executed"] = False
            self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE", step)

    def test_cutover_failure_matrix_is_independent_and_fail_closed(self):
        for name, phase in CUTOVER_CASES.items():
            with self.subTest(name=name):
                doc = fixture()
                del doc["records"]["protected_cutover"]["failure_matrix"][name]
                self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
            for field in ("failure_injected", "isolated", "sql_exclusion_continuous", "edge_exclusion_continuous",
                          "docker_exclusion_continuous", "privileged_exclusion_continuous",
                          "no_lost_commits", "no_stale_restore", "recovery_required",
                          "restore_forbidden_after_commit" if phase == "postcommit" else "commit_not_recorded"):
                with self.subTest(name=name, field=field):
                    doc = fixture()
                    doc["records"]["protected_cutover"]["failure_matrix"][name][field] = False
                    self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
            for field, value in (("phase", "wrong"), ("source_release_sha", SHA),
                                 ("origin", "synthetic"), ("environment_id", "other"),
                                 ("target_release_sha", SOURCE_SHA), ("target_backend_image", "sha256:" + "f" * 64),
                                 ("barrier_started_at", stamp(NOW - timedelta(minutes=235))),
                                 ("barrier_ended_at", stamp(NOW - timedelta(minutes=241)))):
                with self.subTest(name=name, field=field):
                    doc = fixture()
                    doc["records"]["protected_cutover"]["failure_matrix"][name][field] = value
                    self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        doc = fixture()
        matrix = doc["records"]["protected_cutover"]["failure_matrix"]
        matrix["after_commit"]["reference"] = matrix["before_commit"]["reference"]
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        doc = fixture()
        doc["records"]["protected_cutover"]["failure_matrix"]["after_commit"]["committed_at"] = stamp(NOW)
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        doc = fixture()
        del doc["records"]["protected_cutover"]
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")

    def test_cutover_and_disaster_recovery_are_not_interchangeable(self):
        for field in ("isolated_rehearsal", "sql_exclusion_continuous", "edge_exclusion_continuous",
                      "docker_exclusion_continuous", "privileged_exclusion_continuous", "external_writers_excluded",
                      "snapshot_external", "snapshot_verified", "logical_clone_verified", "no_lost_commits",
                      "no_stale_restore", "no_early_reopen", "restore_forbidden_after_commit",
                      "committed_writes_preserved", "concurrent_write_blocked"):
            with self.subTest(field=field):
                doc = fixture()
                doc["records"]["protected_cutover"][field] = False
                self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        for field, value in (("rpo_seconds", 1), ("source_release_sha", SHA), ("target_release_sha", SOURCE_SHA),
                             ("snapshot_sha256", "d" * 64), ("clone_backup_sha256", "d" * 64),
                             ("target_backend_image", "latest"),
                             ("snapshot_verified_at", stamp(NOW - timedelta(minutes=230))),
                             ("committed_at", stamp(NOW - timedelta(minutes=205))),
                             ("barrier_started_at", stamp(NOW - timedelta(days=8)))):
            with self.subTest(field=field):
                doc = fixture()
                doc["records"]["protected_cutover"][field] = value
                self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        doc = fixture()
        doc["records"]["migration"]["backup_sha256"] = "d" * 64
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        doc = fixture()
        doc["records"]["deploy"]["target_backend_image"] = "sha256:" + "f" * 64
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")

    def test_distinct_clone_identity_and_chronology(self):
        for record in ("clone_restore", "protected_cutover"):
            for field in ("cluster", "container", "network", "volume"):
                for other in ("source_identity", "witness_identity"):
                    with self.subTest(record=record, field=field, other=other):
                        doc = fixture()
                        obj = doc["records"][record]
                        obj["clone_identity"][field] = obj[other][field]
                        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        for record, field, value in (
            ("backup", "captured_at", stamp(NOW - timedelta(minutes=105))),
            ("backup", "captured_at", stamp(NOW - timedelta(hours=4))),
            ("rollback", "recovery_point_at", stamp(NOW - timedelta(minutes=111))),
            ("migration", "observed_at", stamp(NOW - timedelta(minutes=180))),
            ("protected_cutover", "observed_at", stamp(NOW - timedelta(minutes=179))),
            ("health_schedule", "started_at", stamp(NOW - timedelta(minutes=160))),
            ("blockers", "observed_at", stamp(NOW - timedelta(minutes=70))),
        ):
            with self.subTest(record=record, field=field):
                doc = fixture()
                doc["records"][record][field] = value
                self.assertEqual(validate_evidence(doc, now=NOW)["status"], "INCOMPLETE")
        doc = fixture()
        doc["records"]["rollback"]["last_commit_at"] = stamp(NOW - timedelta(minutes=120))
        self.assertEqual(validate_evidence(doc, now=NOW)["status"], "REVIEW_REQUIRED")

    def test_cli_rejects_duplicate_keys_and_invalid_json(self):
        script = Path(__file__).resolve().parents[1] / "ops" / "g5_staging_evidence.py"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            for text in ('{"records": {}, "records": {}}', '{"x": NaN}', '{'):
                path.write_text(text, encoding="utf-8")
                result = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
            path.write_text(json.dumps({}), encoding="utf-8")
            result = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["status"], "INCOMPLETE")
            for text in (' ' * (MAX_JSON_BYTES + 1), '[' * 2000 + ']' * 2000,
                         '{"x":' + '1' * 5000 + '}'):
                path.write_text(text, encoding="utf-8")
                result = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True,
                                        timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)
            fifo = Path(directory) / "fifo"
            import os
            os.mkfifo(fifo)
            result = subprocess.run([sys.executable, str(script), str(fifo)], capture_output=True, text=True,
                                    timeout=5)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
