#!/usr/bin/env python3
"""Check operator declarations offline; never authorize a G5 release."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
import re
import stat
import sys


SHA = re.compile(r"[0-9a-f]{40}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")

# Ages are conservative review windows, not guarantees of continuing validity.
AGES = {
    "ci_validation": 30, "ci_journeys": 30, "deploy": 7,
    "https": 7, "smtp": 7, "health_manual": 1, "health_schedule": 1,
    "soak": 7, "alerts": 7, "migration": 7, "backup": 7,
    "clone_restore": 7, "rollback": 7, "blockers": 1, "policy": 7,
    "protected_cutover": 7,
}

CI_JOBS = {
    "ci_validation": ("backend", "postgres-concurrency", "frontend", "browser-e2e",
                      "accessibility-e2e", "dependency-audit", "g5-operations", "images"),
    "ci_journeys": ("isolated-journeys",),
}
CI_G5_STEPS = ("actual_migration", "role_provisioning", "full_schema_restore",
               "logical_clone", "actual_reopen", "release_transition")
CUTOVER_CASES = {
    "stop_writers": "precommit", "backup": "precommit", "pull": "precommit",
    "migration": "precommit", "up": "precommit", "https_timeout": "precommit",
    "smoke": "precommit", "load": "precommit", "recovery": "precommit",
    "before_commit": "precommit", "after_commit": "postcommit",
    "reopen": "postcommit", "lost_response": "postcommit",
}
MAX_JSON_BYTES = 256 * 1024


def _time(value):
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _id(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def _number(value, minimum=0, maximum=None, *, integer=False):
    return (not isinstance(value, bool) and isinstance(value, int if integer else (int, float))
            and (isinstance(value, int) or math.isfinite(value)) and value >= minimum
            and (maximum is None or value <= maximum))


def validate_evidence(document, *, now):
    """Return blockers for untrusted declarations, without inspecting external systems."""
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    if not isinstance(document, dict):
        return {"status": "INCOMPLETE", "blockers": ["document must be an object"]}

    sha = document.get("release_sha")
    environment = document.get("environment_id")
    origin = document.get("origin")
    require(isinstance(sha, str) and SHA.fullmatch(sha) is not None, "invalid release_sha")
    require(document.get("main_head_sha") == sha and isinstance(sha, str)
            and SHA.fullmatch(sha) is not None, "main HEAD does not match release")
    require(_id(environment), "invalid environment_id")
    require(origin in ("real", "synthetic"), "invalid origin")
    records = document.get("records")
    if not isinstance(records, dict):
        records = {}
        errors.append("records must be an object")

    times = {}
    refs = set()
    for name, days in AGES.items():
        record = records.get(name)
        if not isinstance(record, dict):
            errors.append(f"{name}: missing record")
            continue
        require(record.get("release_sha") == sha and isinstance(sha, str) and SHA.fullmatch(sha) is not None,
                f"{name}: release mismatch")
        require(record.get("environment_id") == environment and _id(environment),
                f"{name}: environment mismatch")
        require(record.get("origin") == origin and origin in ("real", "synthetic"),
                f"{name}: origin mismatch")
        ref = record.get("reference")
        require(_id(ref), f"{name}: invalid reference")
        if _id(ref):
            require(ref not in refs, f"{name}: duplicate reference")
            refs.add(ref)
        timestamp = _time(record.get("observed_at"))
        require(timestamp is not None and now - timedelta(days=days) <= timestamp <= now,
                f"{name}: invalid, future or stale observed_at")
        if timestamp:
            times[name] = timestamp
        require(record.get("result") == "pass", f"{name}: result must be pass")

    def rec(name):
        value = records.get(name)
        return value if isinstance(value, dict) else {}

    def true(name, *fields):
        for field in fields:
            require(rec(name).get(field) is True, f"{name}: {field} must be true")

    for name in ("ci_validation", "ci_journeys"):
        require(rec(name).get("conclusion") == "success", f"{name}: CI must succeed")
        true(name, "completed")
        jobs = rec(name).get("jobs")
        for job in CI_JOBS[name]:
            entry = jobs.get(job) if isinstance(jobs, dict) else None
            require(isinstance(entry, dict) and entry.get("executed") is True
                    and entry.get("conclusion") == "success", f"{name}: job {job} must run and succeed")
        if name == "ci_validation":
            steps = rec(name).get("g5_image_steps")
            for step in CI_G5_STEPS:
                entry = steps.get(step) if isinstance(steps, dict) else None
                require(isinstance(entry, dict) and entry.get("executed") is True
                        and entry.get("conclusion") == "success",
                        f"{name}: images step {step} must run and succeed")
    true("deploy", "workflow_executed", "immutable", "migration_succeeded")
    require(rec("deploy").get("deployed_sha") == sha and isinstance(sha, str) and SHA.fullmatch(sha) is not None,
            "deploy: deployed_sha mismatch")
    true("https", "dns_verified", "tls_verified", "hostname_verified", "https_verified")
    true("smtp", "real_provider", "test_recipient_only", "delivery_verified")
    true("migration", "staging_source", "recoverable_copy", "upgrade_verified")

    def metrics(name, field, *, minimum_requests=1, smoke=False):
        r = rec(name).get(field)
        if not isinstance(r, dict):
            errors.append(f"{name}: {field} measurements required")
            return
        label = f"{name}: {field}"
        requests = r.get("requests")
        errors_count = r.get("errors")
        server_errors = r.get("server_errors")
        require(_number(requests, minimum_requests, integer=True), f"{label}: invalid requests")
        require(_number(errors_count, 0, integer=True), f"{label}: invalid errors")
        require(_number(server_errors, 0, 0, integer=True), f"{label}: 5xx must be zero")
        if _number(requests, 1, integer=True) and _number(errors_count, 0, integer=True):
            require(errors_count <= requests and errors_count * 200 <= requests,
                    f"{label}: error budget exceeded")
            if smoke:
                require(errors_count == 0, f"{label}: smoke errors must be zero")
        require(_number(r.get("p95_ms"), 0, 750), f"{label}: probe p95 budget exceeded")

    def run_interval(name, duration_field):
        started = _time(rec(name).get("started_at"))
        ended = _time(rec(name).get("ended_at"))
        duration = rec(name).get(duration_field)
        require(started is not None and ended is not None, f"{name}: valid execution times required")
        if started and ended:
            require(times.get("deploy", now) <= started <= ended <= times.get(name, now),
                    f"{name}: inconsistent execution timeline")
            require(_number(duration, 0) and (ended - started).total_seconds() >= duration,
                    f"{name}: duration exceeds execution interval")

    for name, trigger in (("health_manual", "manual"), ("health_schedule", "schedule")):
        r = rec(name)
        require(r.get("trigger") == trigger, f"{name}: incorrect trigger")
        true(name, "repository_url_configured", "job_executed", "smoke_executed", "load_executed")
        require(r.get("job_conclusion") == "success", f"{name}: probe job must succeed")
        metrics(name, "smoke_metrics", minimum_requests=20, smoke=True)
        metrics(name, "load_metrics")
        require(_number(r.get("load_duration_seconds"), 10), f"{name}: load duration too short")
        run_interval(name, "load_duration_seconds")
    manual_end = _time(rec("health_manual").get("ended_at"))
    scheduled_start = _time(rec("health_schedule").get("started_at"))
    require(manual_end is not None and scheduled_start is not None and manual_end <= scheduled_start,
            "health: manual must complete before scheduled start")
    true("soak", "job_executed", "load_executed", "smoke_executed",
         "server_metrics_reviewed", "no_duplicate_effects")
    require(rec("soak").get("job_conclusion") == "success", "soak: probe job must succeed")
    duration = rec("soak").get("duration_seconds")
    planned = rec("soak").get("planned_duration_seconds")
    require(_number(planned, 900) and _number(duration, 900) and duration >= planned,
            "soak: invalid or incomplete duration")
    run_interval("soak", "duration_seconds")
    require(_id(rec("soak").get("capacity_scope")), "soak: capacity_scope required")
    metrics("soak", "load_metrics")
    metrics("soak", "smoke_metrics", minimum_requests=30, smoke=True)
    require(_number(rec("soak").get("api_p95_ms"), 0)
            and rec("soak")["api_p95_ms"] < 300, "soak: game API p95 budget exceeded")
    true("alerts", "api", "worker", "database", "failure_visible", "alert_tested", "logs_reviewed")

    true("backup", "external_copy", "checksum_verified", "retention_verified")
    backup_hash = rec("backup").get("sha256")
    require(isinstance(backup_hash, str) and HASH.fullmatch(backup_hash) is not None,
            "backup: invalid sha256")
    true("clone_restore", "isolated", "fixture_mutated", "restore_verified", "data_verified")
    require(isinstance(backup_hash, str) and HASH.fullmatch(backup_hash) is not None
            and rec("clone_restore").get("backup_sha256") == backup_hash,
            "clone_restore: backup hash mismatch")
    clone_id = rec("clone_restore").get("clone_id")
    require(_id(clone_id) and clone_id != environment, "clone_restore: invalid clone identity")
    def distinct_identities(name):
        record = rec(name)
        identities = [record.get(field) for field in ("source_identity", "clone_identity", "witness_identity")]
        for field in ("cluster", "container", "network", "volume"):
            values = [item.get(field) if isinstance(item, dict) else None for item in identities]
            require(all(_id(value) for value in values) and len(set(v for v in values if _id(v))) == 3,
                    f"{name}: source, clone and witness {field} identities must differ")

    distinct_identities("clone_restore")
    true("rollback", "isolated", "application_verified", "database_verified", "smoke_verified")
    require(_id(clone_id) and rec("rollback").get("clone_id") == clone_id,
            "rollback: clone identity mismatch")
    require(rec("rollback").get("backup_sha256") == backup_hash and isinstance(backup_hash, str)
            and HASH.fullmatch(backup_hash) is not None, "rollback: backup hash mismatch")
    require(_number(rec("rollback").get("rpo_seconds"), 0, 86400), "rollback: RPO exceeds 24h")
    require(_number(rec("rollback").get("rto_seconds"), 0, 14400), "rollback: RTO exceeds 4h")
    captured = _time(rec("backup").get("captured_at"))
    recovery_point = _time(rec("rollback").get("recovery_point_at"))
    last_commit = _time(rec("rollback").get("last_commit_at"))
    incident = _time(rec("rollback").get("incident_at"))
    restored = _time(rec("rollback").get("service_restored_at"))
    require(all((captured, recovery_point, last_commit, incident, restored)),
            "recovery: valid UTC timestamps required")
    if all((captured, recovery_point, last_commit, incident, restored)):
        require(recovery_point == captured and captured <= times.get("backup", now)
                and recovery_point <= last_commit <= incident <= restored <= times.get("rollback", now)
                and times.get("clone_restore", now) <= incident,
                "recovery: inconsistent timeline")
        require(_number(rec("rollback").get("rpo_seconds"), 0, 86400)
                and rec("rollback")["rpo_seconds"] == (last_commit - recovery_point).total_seconds(),
                "rollback: RPO does not match timeline")
        require(_number(rec("rollback").get("rto_seconds"), 0, 14400)
                and rec("rollback")["rto_seconds"] == (restored - incident).total_seconds(),
                "rollback: RTO does not match timeline")
    true("blockers", "inventory_complete")
    for severity in ("p0_open", "p1_open"):
        require(_number(rec("blockers").get(severity), 0, 0, integer=True),
                f"blockers: {severity} must be zero")
    require(rec("blockers").get("p2_156") in ("resolved", "accepted"),
            "blockers: P2 #156 resolution or acceptance required")
    require(_id(rec("blockers").get("p2_156_reference")),
            "blockers: P2 #156 decision reference required")
    true("policy", "support", "privacy", "terms", "retention", "operator_details")

    def ordered(first, second):
        if first in times and second in times:
            require(times[first] <= times[second], f"{first} must precede {second}")

    for name in ("ci_validation", "ci_journeys"):
        ordered(name, "deploy")
    for name in AGES:
        if name not in ("ci_validation", "ci_journeys", "deploy", "migration", "protected_cutover"):
            ordered("deploy", name)
    ordered("migration", "protected_cutover")
    ordered("protected_cutover", "deploy")
    ordered("health_manual", "health_schedule")
    ordered("backup", "clone_restore")
    ordered("clone_restore", "rollback")
    for name in AGES:
        if name != "blockers":
            ordered(name, "blockers")

    cutover = rec("protected_cutover")
    true("protected_cutover", "isolated_rehearsal", "sql_exclusion_continuous",
         "edge_exclusion_continuous", "docker_exclusion_continuous",
         "privileged_exclusion_continuous", "external_writers_excluded",
         "snapshot_external", "snapshot_verified", "logical_clone_verified",
         "no_lost_commits", "no_stale_restore", "committed_writes_preserved",
         "concurrent_write_blocked", "no_early_reopen", "restore_forbidden_after_commit")
    source_sha = cutover.get("source_release_sha")
    require(isinstance(source_sha, str) and SHA.fullmatch(source_sha) is not None
            and source_sha != sha and rec("deploy").get("source_release_sha") == source_sha,
            "protected_cutover: source release mismatch")
    require(cutover.get("target_release_sha") == sha and isinstance(sha, str)
            and SHA.fullmatch(sha) is not None, "protected_cutover: target release mismatch")
    for field in ("source_backend_image", "source_frontend_image", "target_backend_image", "target_frontend_image"):
        value = cutover.get(field)
        require(isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None,
                f"protected_cutover: {field} immutable image identity required")
        require(rec("deploy").get(field) == value, f"deploy: {field} mismatch")
    snapshot = cutover.get("snapshot_sha256")
    require(isinstance(snapshot, str) and HASH.fullmatch(snapshot) is not None
            and rec("migration").get("backup_sha256") == snapshot
            and cutover.get("clone_backup_sha256") == snapshot,
            "protected_cutover: snapshot, clone and migration hash mismatch")
    distinct_identities("protected_cutover")
    require(_number(cutover.get("rpo_seconds"), 0, 0), "protected_cutover: RPO must be zero")
    barrier = _time(cutover.get("barrier_started_at"))
    snapshot_at = _time(cutover.get("snapshot_captured_at"))
    snapshot_verified = _time(cutover.get("snapshot_verified_at"))
    clone_verified = _time(cutover.get("clone_verified_at"))
    committed = _time(cutover.get("committed_at"))
    barrier_end = _time(cutover.get("barrier_ended_at"))
    require(all((barrier, snapshot_at, snapshot_verified, clone_verified, committed, barrier_end)),
            "protected_cutover: valid timeline required")
    if all((barrier, snapshot_at, snapshot_verified, clone_verified, committed, barrier_end)):
        require(barrier <= snapshot_at <= snapshot_verified <= clone_verified
                <= times.get("migration", now) <= committed <= barrier_end <= times.get("protected_cutover", now)
                and barrier >= now - timedelta(days=AGES["protected_cutover"]),
                "protected_cutover: snapshot, rehearsal and barrier chronology invalid")
    cases = cutover.get("failure_matrix")
    case_refs = set()
    for name, phase in CUTOVER_CASES.items():
        case = cases.get(name) if isinstance(cases, dict) else None
        valid = isinstance(case, dict) and case.get("phase") == phase and _id(case.get("reference"))
        if valid:
            ref = case["reference"]
            valid = ref not in case_refs and ref not in refs
            case_refs.add(ref)
        for field in ("failure_injected", "isolated", "sql_exclusion_continuous", "edge_exclusion_continuous",
                      "docker_exclusion_continuous", "privileged_exclusion_continuous",
                      "no_lost_commits", "no_stale_restore"):
            valid = valid and case.get(field) is True
        valid = valid and case.get("recovery_required") is True
        valid = valid and case.get("source_release_sha") == source_sha and case.get("target_release_sha") == sha
        valid = valid and all(case.get(field) == cutover.get(field) for field in
                              ("source_backend_image", "source_frontend_image", "target_backend_image", "target_frontend_image"))
        start = _time(case.get("barrier_started_at")) if isinstance(case, dict) else None
        failed = _time(case.get("failure_at")) if isinstance(case, dict) else None
        end = _time(case.get("barrier_ended_at")) if isinstance(case, dict) else None
        valid = valid and start is not None and failed is not None and end is not None
        if start and failed and end:
            valid = valid and now - timedelta(days=AGES["protected_cutover"]) <= start <= failed <= end <= times.get("protected_cutover", now)
        if phase == "postcommit":
            committed = _time(case.get("committed_at")) if isinstance(case, dict) else None
            valid = valid and committed is not None and start is not None and failed is not None and start <= committed <= failed
            valid = valid and case.get("restore_forbidden_after_commit") is True
        else:
            valid = valid and case.get("commit_not_recorded") is True
        require(valid, f"protected_cutover: {name} failure evidence incomplete")

    return {
        "status": "INCOMPLETE" if errors else ("SYNTHETIC_ONLY" if origin == "synthetic" else "REVIEW_REQUIRED"),
        "blockers": errors,
    }


def validate_approval(document, approval, *, now):
    """Check a separate, unverified approval declaration; it cannot grant GO."""
    result = validate_evidence(document, now=now)
    errors = []
    if not isinstance(approval, dict):
        approval = {}
        errors.append("approval must be a separate object")
    if result["status"] != "REVIEW_REQUIRED":
        errors.append("real evidence must be complete before approval")
    for field in ("release_sha", "environment_id"):
        if not isinstance(document, dict) or approval.get(field) != document.get(field):
            errors.append(f"approval: {field} mismatch")
    if approval.get("origin") != "real" or approval.get("decision") != "approve":
        errors.append("approval: real explicit approval required")
    try:
        canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                               allow_nan=False).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        digest = None
    if digest is None or approval.get("evidence_sha256") != digest:
        errors.append("approval: evidence digest mismatch")
    if not _id(approval.get("owner_id")) or not _id(approval.get("reference")):
        errors.append("approval: owner_id and reference required")
    approved_at = _time(approval.get("approved_at"))
    if approved_at is None or approved_at > now.astimezone(timezone.utc) or approved_at < now.astimezone(timezone.utc) - timedelta(days=1):
        errors.append("approval: invalid, future or stale approved_at")
    if approved_at and isinstance(document, dict) and isinstance(document.get("records"), dict):
        for record in document["records"].values():
            if isinstance(record, dict):
                observed = _time(record.get("observed_at"))
                if observed and approved_at < observed:
                    errors.append("approval: predates evidence")
                    break
                if approval.get("reference") == record.get("reference"):
                    errors.append("approval: reference must be separate")
                    break
    return {"status": "NO_GO", "approval_declaration": "INCOMPLETE" if errors else "REVIEW_REQUIRED",
            "blockers": result["blockers"] + errors}


def _load(path):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("input must be a regular file")
        raw = source.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("input too large")
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("invalid number")
        return parsed

    document = json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs,
                          parse_float=finite_float,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid number")))
    pending = [(document, 0)]
    count = 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if depth > 32 or count > 10000:
            raise ValueError("JSON too complex")
        if isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", help="local JSON file containing declarations")
    parser.add_argument("--approval", help="separate local JSON approval declaration")
    args = parser.parse_args(argv)
    try:
        document = _load(args.evidence)
        now = datetime.now(timezone.utc)
        result = (validate_approval(document, _load(args.approval), now=now) if args.approval
                  else validate_evidence(document, now=now))
    except (OSError, UnicodeError, ValueError, RecursionError):
        print("Invalid or unreadable local JSON input", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if not result["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
