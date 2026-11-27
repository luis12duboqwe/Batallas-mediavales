import hashlib
import fcntl
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops import ci_g5_release_transition as transition
from ops.ci_g5_release_transition import (
    EvidenceLog,
    PREVIOUS_SHA,
    ScenarioFault,
    TransitionPort,
    _database_fingerprint,
    _hold_supervised_recovery_lease,
    _inject_scenario_fault,
    _remove_fixture_image,
    _scenario_fault_reached,
    image_provenance,
    main,
    recovery_is_authorized,
    release_pair,
)
from ops.g5_activation_fence import arm_cutover
from ops.g5_cutover_state import Identity, Phase, StateError


PREVIOUS_IMAGE = "sha256:" + "a" * 64
CANDIDATE_IMAGE = "sha256:" + "b" * 64
CANDIDATE_SHA = "c" * 40


def test_historical_and_candidate_release_identities_are_immutable_and_distinct():
    assert PREVIOUS_SHA == "eafc5bbd5fdc9caad698db48cbb8ad80df942f0e"
    assert release_pair(PREVIOUS_SHA, CANDIDATE_SHA,
                        PREVIOUS_IMAGE, CANDIDATE_IMAGE) == (PREVIOUS_SHA, CANDIDATE_SHA)
    for args in (
        (PREVIOUS_SHA, PREVIOUS_SHA, PREVIOUS_IMAGE, CANDIDATE_IMAGE),
        (PREVIOUS_SHA, CANDIDATE_SHA, PREVIOUS_IMAGE, PREVIOUS_IMAGE),
        ("mutable-tag", CANDIDATE_SHA, PREVIOUS_IMAGE, CANDIDATE_IMAGE),
    ):
        with pytest.raises(StateError):
            release_pair(*args)


def test_image_provenance_requires_exact_source_sha_and_fixture_scope():
    row = {
        "Id": CANDIDATE_IMAGE,
        "Config": {"Labels": {
            "org.opencontainers.image.revision": CANDIDATE_SHA,
            "medievol.g5.source-sha": CANDIDATE_SHA,
            "medievol.g5.scope": "github-ci-disposable",
        }},
    }
    assert image_provenance(row, CANDIDATE_SHA) == CANDIDATE_IMAGE
    for changed in (
        row | {"Id": "candidate:latest"},
        {"Id": CANDIDATE_IMAGE, "Config": None},
        {"Id": CANDIDATE_IMAGE, "Config": {"Labels": {
            "org.opencontainers.image.revision": "d" * 40,
            "medievol.g5.source-sha": CANDIDATE_SHA,
            "medievol.g5.scope": "github-ci-disposable",
        }}},
        {"Id": CANDIDATE_IMAGE, "Config": {"Labels": {
            "org.opencontainers.image.revision": CANDIDATE_SHA,
            "medievol.g5.source-sha": CANDIDATE_SHA,
            "medievol.g5.scope": "production",
        }}},
    ):
        with pytest.raises(StateError):
            image_provenance(changed, CANDIDATE_SHA)


@pytest.mark.parametrize(
    "changes",
    [
        {"approved": False},
        {"marker_operation": "different"},
        {"migration_started": True},
        {"current_sha256": "e" * 64},
        {"observed_image_id": CANDIDATE_IMAGE},
        {"phase": Phase.MIGRATING},
    ],
)
def test_previous_release_recovery_requires_supervision_and_proven_no_mutation(changes):
    evidence = {
        "approved": True,
        "marker_operation": "ci-operation",
        "operation_id": "ci-operation",
        "migration_started": False,
        "baseline_sha256": "d" * 64,
        "current_sha256": "d" * 64,
        "previous_image_id": PREVIOUS_IMAGE,
        "observed_image_id": PREVIOUS_IMAGE,
        "phase": Phase.RECOVERY_REQUIRED,
    } | changes
    with pytest.raises(StateError):
        recovery_is_authorized(**evidence)


def test_supervised_recovery_accepts_only_absent_or_incident_manifest():
    common = {
        "approved": True,
        "marker_operation": "ci-operation",
        "operation_id": "ci-operation",
        "migration_started": False,
        "baseline_sha256": "d" * 64,
        "current_sha256": "d" * 64,
        "previous_image_id": PREVIOUS_IMAGE,
        "observed_image_id": PREVIOUS_IMAGE,
    }
    assert recovery_is_authorized(**common, phase=None)
    assert recovery_is_authorized(**common, phase=Phase.RECOVERY_REQUIRED)


def test_evidence_log_is_private_append_only_and_detects_tampering(tmp_path):
    path = tmp_path / "transition.jsonl"
    log = EvidenceLog(path)
    log.append("snapshot", sha256=hashlib.sha256(b"snapshot").hexdigest())
    log.append("candidate_not_started", migration_started=False)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    rows = log.verify()
    assert [row["event"] for row in rows] == ["snapshot", "candidate_not_started"]
    assert "secret" not in path.read_text().lower()

    envelope = json.loads(path.read_text().splitlines()[0])
    envelope["fields"]["sha256"] = "0" * 64
    lines = path.read_text().splitlines()
    lines[0] = json.dumps(envelope)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(StateError, match="chain"):
        log.verify()
    log.close()


@pytest.mark.parametrize("damage", ["empty", "truncated", "trailing", "replaced"])
def test_evidence_log_rejects_empty_truncated_or_replaced_history(tmp_path, damage):
    path = tmp_path / "transition.jsonl"
    log = EvidenceLog(path)
    log.append("snapshot", sha256=hashlib.sha256(b"snapshot").hexdigest())
    if damage == "empty":
        path.write_bytes(b"")
    elif damage == "truncated":
        path.write_bytes(path.read_bytes()[:-2])
    elif damage == "trailing":
        with path.open("ab") as stream:
            stream.write(b"{}\n")
    else:
        replacement = tmp_path / "replacement.jsonl"
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
    try:
        with pytest.raises(StateError):
            log.verify()
    finally:
        log.close()


def _recovery_lease_fixture(tmp_path):
    host = tmp_path / "host"
    host.mkdir(mode=0o700)
    (host / ".ops-state").mkdir(mode=0o700)
    backup = tmp_path / "backup"
    backup.mkdir(mode=0o700)
    request = transition.PreparationRequest(
        str(host), str(backup), "ci-operation", "a" * 40, "b" * 40,
        "bm-ci", "bm_ci",
    )
    with arm_cutover(str(host), "ci-operation"):
        pass
    evidence = EvidenceLog(tmp_path / "transition.jsonl")
    evidence.append("snapshot", operation_id="ci-operation")
    return host, backup, request, evidence


def test_recovery_lease_rejects_contention_and_pins_marker_and_state(tmp_path):
    host, _backup, request, evidence = _recovery_lease_fixture(tmp_path)
    lock_fd = os.open(host / ".ops-state" / "deploy.lock", os.O_RDWR)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(StateError, match="deploy.lock"):
            with _hold_supervised_recovery_lease(
                str(host), "ci-operation", request, evidence,
            ):
                pytest.fail("contended recovery lease was acquired")
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        evidence.close()


@pytest.mark.parametrize("drift", ["marker", "manifest"])
def test_recovery_lease_detects_marker_and_manifest_drift(tmp_path, drift):
    host, backup, request, evidence = _recovery_lease_fixture(tmp_path)
    manifest_path = host / ".ops-state" / "g5-cutover.json"
    if drift == "manifest":
        store = transition.CutoverStore(str(host))
        archive = backup / "snapshot.dump"
        archive.write_bytes(b"snapshot")
        archive.chmod(0o400)
        identity = Identity(
            "ci-operation", "a" * 40, "b" * 40,
            hashlib.sha256(b"snapshot").hexdigest(), str(archive), "bm-ci", "bm_ci",
        )
        store.prepare(identity, str(backup))
        store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
        store.advance(identity, Phase.MIGRATING, Phase.RECOVERY_REQUIRED)
    try:
        with pytest.raises(StateError):
            with _hold_supervised_recovery_lease(
                str(host), "ci-operation", request, evidence,
            ) as (assert_active, _manifest):
                if drift == "marker":
                    marker = host / ".ops-state" / "g5-cutover-activated"
                    marker.write_text("version=1\noperation_id=changed\n")
                else:
                    manifest_path.write_text(manifest_path.read_text() + " ")
                assert_active()
    finally:
        evidence.close()


def test_scenario_faults_require_the_expected_typed_fault_and_durable_receipt(tmp_path):
    path = tmp_path / "transition.jsonl"
    log = EvidenceLog(path)
    try:
        with pytest.raises(ScenarioFault):
            _inject_scenario_fault(log, "pull", "pull")
        fault = ScenarioFault("pull", "pull")
        assert _scenario_fault_reached(log, fault, "pull")
        assert not _scenario_fault_reached(log, RuntimeError("unrelated"), "pull")
        assert not _scenario_fault_reached(log, ScenarioFault("backup", "backup"), "pull")
        with pytest.raises(ScenarioFault):
            _inject_scenario_fault(log, "replace", "candidate-replacement", migration_started=True)
        assert _scenario_fault_reached(
            log, ScenarioFault("replace", "candidate-replacement", True), "replace",
        )
        path.write_bytes(path.read_bytes()[:-3])
        with pytest.raises(StateError):
            _scenario_fault_reached(log, fault, "pull")
    finally:
        log.close()


def test_failure_reclosure_attempts_every_barrier_and_writer_after_errors(tmp_path, monkeypatch):
    log = EvidenceLog(tmp_path / "transition.jsonl")
    port = TransitionPort.__new__(TransitionPort)
    port.evidence = log
    ids = ["a" * 64, "b" * 64, "c" * 64, "d" * 64]
    port.previous, port.previous_worker, port.candidate_id, port.candidate_worker = ids
    calls = []
    rows = {
        cid: {
            "Id": cid,
            "State": {"Running": True, "Status": "running"},
            "HostConfig": {"RestartPolicy": {"Name": "always"}},
        }
        for cid in ids
    }

    class Edge:
        def close(self):
            calls.append("edge.close")
            raise RuntimeError("unrelated edge failure")

        def assert_closed(self):
            calls.append("edge.assert_closed")
            raise RuntimeError("edge still open")

    class Admin:
        def execute_committed(self, sql):
            calls.append(sql)
            if "CONNECTION LIMIT" in sql:
                raise RuntimeError("unrelated database failure")

        def sql(self, _sql, _database):
            return "0"

    port.edge = Edge()
    port.admin = Admin()
    port.sql = SimpleNamespace(assert_closed=lambda: calls.append("sql.assert_closed"))

    def run(args):
        calls.append(tuple(args))
        if args[0] == "update" and args[-1] == ids[0]:
            raise RuntimeError("unrelated container update failure")
        if args[0] == "stop":
            rows[args[-1]]["State"] = {"Running": False, "Status": "exited"}
            rows[args[-1]]["HostConfig"]["RestartPolicy"]["Name"] = "no"
        return ""

    def inspect(cid):
        calls.append(("inspect", cid))
        if cid == ids[0] and calls.count(("inspect", cid)) == 1:
            raise RuntimeError("unrelated inspect failure")
        return rows[cid]

    monkeypatch.setattr(transition, "run", run)
    monkeypatch.setattr(transition, "_container", inspect)
    try:
        with pytest.raises(StateError, match="uncertain"):
            port._restrict_after_failure()
        assert all(("stop", "--time", "10", cid) in calls for cid in ids)
        assert all(("update", "--restart=no", cid) in calls for cid in ids)
        assert "edge.assert_closed" in calls
        assert "sql.assert_closed" in calls
        assert sum("CONNECTION LIMIT" in call for call in calls if isinstance(call, str)) == 1
        assert any(row["event"] == "failure_reclosure_uncertain" for row in log.verify())
    finally:
        log.close()


@pytest.mark.parametrize("failure_point", ["after_old_start", "after_edge_open", "stopped_worker"])
def test_recovery_recloses_if_failure_follows_old_start_or_edge_open(
    tmp_path, monkeypatch, failure_point,
):
    log = EvidenceLog(tmp_path / "transition.jsonl")
    port = TransitionPort.__new__(TransitionPort)
    old_id = "a" * 64
    old_worker_id = "f" * 64
    port.previous = old_id
    port.previous_worker = old_worker_id
    port.candidate_id = port.candidate_worker = None
    port.previous_initial_running = {old_id: True, old_worker_id: failure_point != "stopped_worker"}
    port.recovery_started = set()
    port.images = {"previous": PREVIOUS_IMAGE, "candidate": CANDIDATE_IMAGE}
    port.original_db = SimpleNamespace(connection_limit=100)
    port.admin = SimpleNamespace(execute_committed=lambda _sql: None)
    port.evidence = log
    port.project = "bm-ci"
    port.access_token = "test-token"
    port.user_id = "test-user"
    port.nginx_address = "127.0.0.1"
    port.release_receipt = tmp_path / "absent-release.json"
    port._assert_recovery_preconditions = lambda *_args, **_kwargs: None
    port._restrict_after_failure = Mock()
    port._route_nginx_to_previous = lambda: None
    edge_opened = []
    if failure_point == "after_edge_open":
        def open_edge():
            edge_opened.append(True)
            raise RuntimeError("failure after edge admission")
        port._open_edge = open_edge

    started = []

    def run(args):
        started.append(args)
        return ""

    inspection_count = []

    def inspect(_cid):
        inspection_count.append(True)
        image_id = "sha256:" + ("e" * 64) if failure_point == "after_old_start" else PREVIOUS_IMAGE
        return {
            "Image": image_id,
            "State": {"Running": True},
            "HostConfig": {"RestartPolicy": {"Name": "no"}},
        }

    monkeypatch.setattr(transition, "run", run)
    monkeypatch.setattr(transition, "_container", inspect)
    monkeypatch.setattr(transition, "wait_until", lambda _fn, _message: None)
    monkeypatch.setattr(transition, "probe", lambda _args: (0, "", ""))
    monkeypatch.setattr(transition, "_container_ip", lambda *_args: "172.18.0.7")
    monkeypatch.setattr(transition, "_api_version", lambda *_args: None)
    monkeypatch.setattr(transition, "_app_call", lambda *_args: None)
    if failure_point == "after_edge_open":
        monkeypatch.setattr(TransitionPort, "_open_edge", lambda self: open_edge())
    try:
        with pytest.raises((StateError, RuntimeError)):
            port.supervised_recover_previous(lambda: None)
        assert started == ([["start", old_id], ["start", old_worker_id]]
                           if failure_point == "after_edge_open" else [["start", old_id]])
        assert port._restrict_after_failure.call_count >= 2
        assert bool(edge_opened) is (failure_point == "after_edge_open")
    finally:
        log.close()


def test_nginx_route_accepts_candidate_reusing_previous_private_address(tmp_path, monkeypatch):
    host = tmp_path / "host"
    host.mkdir()
    config = host / "nginx.g5.conf"
    original = "upstream backend {\n    server 172.18.0.2:8000;\n}\n"
    config.write_text(original)
    evidence = EvidenceLog(tmp_path / "transition.jsonl")
    port = TransitionPort.__new__(TransitionPort)
    port.root = tmp_path
    port.evidence = evidence
    port.previous = "a" * 64
    port.candidate_id = "b" * 64
    port.previous_address = port.candidate_address = "172.18.0.2"
    port.nginx = "nginx"
    monkeypatch.setattr(transition, "run", lambda _args: "")

    port._route_nginx_to_candidate()

    assert config.read_text() == original
    assert [row["event"] for row in evidence.verify()] == [
        "nginx_candidate_route_reloaded",
    ]
    evidence.close()


def test_nginx_previous_route_uses_the_recovered_container_address(tmp_path, monkeypatch):
    host = tmp_path / "host"
    host.mkdir()
    config = host / "nginx.g5.conf"
    config.write_text("upstream backend {\n    server 172.18.0.2:8000;\n}\n")
    evidence = EvidenceLog(tmp_path / "transition.jsonl")
    port = TransitionPort.__new__(TransitionPort)
    port.root = tmp_path
    port.evidence = evidence
    port.previous_address = "172.18.0.9"
    port.nginx = "nginx"
    monkeypatch.setattr(transition, "run", lambda _args: "")

    port._route_nginx_to_previous()

    assert "server 172.18.0.9:8000;" in config.read_text()
    assert [row["event"] for row in evidence.verify()] == ["nginx_previous_route_reloaded"]
    evidence.close()


def test_database_fingerprint_normalizes_pg_dump_stream_tokens(monkeypatch):
    template = (
        b"--\n-- PostgreSQL database dump\n"
        b"\\restrict first-token\nCREATE TABLE fixture (id integer);\n"
        b"\\unrestrict first-token\n"
    )
    monkeypatch.setattr(transition, "binary", lambda _args: template)
    first = _database_fingerprint("container")
    monkeypatch.setattr(
        transition, "binary",
        lambda _args: template.replace(b"first-token", b"second-token"),
    )
    assert _database_fingerprint("container") == first

    changed = template.replace(b"fixture", b"changed")
    monkeypatch.setattr(transition, "binary", lambda _args: changed)
    assert _database_fingerprint("container") != first


def test_fixture_image_cleanup_tolerates_absent_tag_and_checks_provenance(monkeypatch):
    row = {
        "Id": CANDIDATE_IMAGE,
        "Config": {"Labels": {
            "org.opencontainers.image.revision": CANDIDATE_SHA,
            "medievol.g5.source-sha": CANDIDATE_SHA,
            "medievol.g5.scope": "github-ci-disposable",
        }},
    }
    removed = []
    monkeypatch.setattr(transition, "probe", lambda _args: (
        1, "[]\n", "Error response from daemon: No such image: candidate:ci",
    ))
    _remove_fixture_image("candidate:ci", CANDIDATE_SHA)

    monkeypatch.setattr(transition, "probe", lambda _args: (0, json.dumps([row]), ""))
    monkeypatch.setattr(transition, "run", lambda args: removed.append(args) or "")
    _remove_fixture_image("candidate:ci", CANDIDATE_SHA)
    assert removed == [["image", "rm", "candidate:ci"]]

    with pytest.raises(StateError):
        _remove_fixture_image("candidate:ci", "d" * 40)
    assert removed == [["image", "rm", "candidate:ci"]]


def test_ci_gate_and_recovery_flag_are_required_before_fixture_creation(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert main(["success", str(tmp_path)]) == 2

    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    workspace = tmp_path / "private"
    workspace.mkdir(mode=0o700)
    workspace.chmod(0o700)
    assert main(["create", str(workspace)]) == 2
    assert not list(workspace.iterdir())
