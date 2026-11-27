import hashlib
import json
from pathlib import Path
import stat
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops.ci_g5_release_transition import (
    EvidenceLog,
    PREVIOUS_SHA,
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
