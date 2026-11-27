"""Adversarial read-only evidence checks; no external services."""
import hashlib
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_activation_fence import MARKER, arm_cutover
from ops.g5_cutover_state import CutoverStore, Identity, Phase, StateError
from ops.g5_incident_inspect import Disposition, inspect_incident


@pytest.fixture
def scope(tmp_path):
    host = tmp_path / "host"
    state = host / ".ops-state"
    state.mkdir(parents=True, mode=0o700)
    backups = tmp_path / "backups"
    backups.mkdir(mode=0o700)
    archive = backups / "archive.dump"
    archive.write_bytes(b"synthetic snapshot")
    archive.chmod(0o600)
    identity = Identity("inspect-ci", "a" * 40, "b" * 40,
                        hashlib.sha256(archive.read_bytes()).hexdigest(), str(archive),
                        "ci_project", "ci_db")
    return host, state, backups, identity


def persist(scope, phase):
    host, state, backups, identity = scope
    with arm_cutover(str(host), identity.operation_id):
        if phase is not None:
            store = CutoverStore(str(host))
            store.prepare(identity, str(backups))
            if phase is Phase.RECOVERY_REQUIRED:
                store.advance(identity, Phase.PREPARED, phase)
            else:
                current = Phase.PREPARED
                for next_phase in (Phase.MIGRATING, Phase.VERIFIED_READONLY,
                                   Phase.COMMITTED_WRITERS_ALLOWED):
                    if current is phase:
                        break
                    store.advance(identity, current, next_phase)
                    current = next_phase
    return host, state


def contents(state):
    return {p.name: (p.stat().st_ino, p.read_bytes()) for p in state.iterdir()}


@pytest.mark.parametrize("phase,disposition", [
    (None, Disposition.PREPARATION_UNCERTAIN),
    (Phase.PREPARED, Disposition.PRECOMMIT_RECONCILIATION),
    (Phase.MIGRATING, Disposition.PRECOMMIT_RECONCILIATION),
    (Phase.VERIFIED_READONLY, Disposition.PRECOMMIT_RECONCILIATION),
    (Phase.RECOVERY_REQUIRED, Disposition.INCIDENT_RECONCILIATION),
    (Phase.COMMITTED_WRITERS_ALLOWED, Disposition.POSTCOMMIT_RECONCILIATION),
])
def test_evidence_only_with_no_file_mutation(scope, phase, disposition):
    host, state = persist(scope, phase)
    before = contents(state)
    evidence = inspect_incident(str(host))
    assert evidence.operation_id == "inspect-ci"
    assert evidence.observed_phase is phase
    assert evidence.disposition is disposition
    assert contents(state) == before


def test_active_coordinator_refuses_inspection(scope):
    host, state, _, identity = scope
    with arm_cutover(str(host), identity.operation_id):
        with pytest.raises(StateError, match="lease is active"):
            inspect_incident(str(host))


def test_missing_lock_does_not_create_one(scope):
    host, state, _, _ = scope
    with pytest.raises(FileNotFoundError):
        inspect_incident(str(host))
    assert list(state.iterdir()) == []


@pytest.mark.parametrize("mutation", ["absent", "malformed", "wrong_id", "mode", "symlink",
                                      "hardlink", "fifo", "oversized"])
def test_unsafe_marker_refused(scope, mutation):
    host, state = persist(scope, Phase.MIGRATING)
    marker = state / MARKER
    if mutation == "absent":
        marker.unlink()
    elif mutation == "malformed":
        marker.write_bytes(b"version=1\n")
    elif mutation == "wrong_id":
        marker.write_bytes(b"version=1\noperation_id=another\n")
    elif mutation == "mode":
        marker.chmod(0o644)
    elif mutation == "symlink":
        marker.unlink()
        marker.symlink_to(state / "deploy.lock")
    elif mutation == "hardlink":
        os.link(marker, state / "other")
    elif mutation == "fifo":
        marker.unlink()
        os.mkfifo(marker, 0o600)
    else:
        marker.write_bytes(b"x" * 161)
    with pytest.raises((StateError, OSError)):
        inspect_incident(str(host))


@pytest.mark.parametrize("name", ["recovery-required", "recovery-required.orphan",
                                  ".g5-cutover-deadbeef.tmp"])
def test_ambiguous_artifact_is_preserved(scope, name):
    host, state = persist(scope, Phase.PREPARED)
    artifact = state / name
    artifact.write_text("unresolved evidence")
    before = contents(state)
    with pytest.raises(StateError, match="ambiguous"):
        inspect_incident(str(host))
    assert contents(state) == before


def test_corrupt_manifest_refused(scope):
    host, state = persist(scope, Phase.COMMITTED_WRITERS_ALLOWED)
    (state / "g5-cutover.json").write_text("{}")
    with pytest.raises(StateError):
        inspect_incident(str(host))


def test_marker_drift_during_manifest_read_refused(scope, monkeypatch):
    host, state = persist(scope, Phase.PREPARED)
    load = CutoverStore._load

    def changed(store, directory):
        result = load(store, directory)
        (state / MARKER).write_text("version=1\noperation_id=changed\n")
        return result

    monkeypatch.setattr(CutoverStore, "_load", changed)
    with pytest.raises(StateError, match="marker changed"):
        inspect_incident(str(host))
