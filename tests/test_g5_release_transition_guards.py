import hashlib
import json
from pathlib import Path
import stat
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops import ci_g5_release_transition as transition
from ops.ci_g5_release_transition import (
    EvidenceLog,
    PREVIOUS_SHA,
    TransitionPort,
    _database_fingerprint,
    _remove_fixture_image,
    image_provenance,
    main,
    recovery_is_authorized,
    release_pair,
)
from ops.g5_cutover_state import Phase, StateError


PREVIOUS_IMAGE = "sha256:" + "a" * 64
CANDIDATE_IMAGE = "sha256:" + "b" * 64
CANDIDATE_SHA = "c" * 40


def test_historical_and_candidate_release_identities_are_immutable_and_distinct():
    assert PREVIOUS_SHA == "6ec2f118d4423359707176538d7f835bdb43c0e9"
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


def test_nginx_route_accepts_candidate_reusing_previous_private_address(tmp_path):
    host = tmp_path / "host"
    host.mkdir()
    config = host / "nginx.g5.conf"
    original = "upstream backend { server 172.18.0.2:8000; }\n"
    config.write_text(original)
    evidence = EvidenceLog(tmp_path / "transition.jsonl")
    port = TransitionPort.__new__(TransitionPort)
    port.root = tmp_path
    port.evidence = evidence
    port.previous = "a" * 64
    port.candidate_id = "b" * 64
    port.previous_address = port.candidate_address = "172.18.0.2"

    port._route_nginx_to_candidate()

    assert config.read_text() == original
    assert [row["event"] for row in evidence.verify()] == [
        "nginx_candidate_route_address_reused",
    ]


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
