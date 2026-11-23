"""Adversarial G5 preparation tests: synthetic files, no Docker/DB/VPS."""
from __future__ import annotations

from dataclasses import replace
import fcntl
import hashlib
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_activation_fence import MARKER
from ops.g5_cutover_prepare import (
    BackupReceipt,
    G5Preparation,
    PreparationRequest,
)
from ops.g5_cutover_state import CutoverStore, MANIFEST, Phase, StateError


class FakePersistentBarrier:
    """Explicitly NOT a real barrier. Records call order and injects faults."""

    def __init__(self, backups: Path, fail: str | None = None):
        self.backups = backups
        self.fail = fail
        self.calls: list[str] = []
        self.verifications = 0
        self.receipt_override = None

    def _step(self, name: str) -> None:
        self.calls.append(name)
        if self.fail == name:
            raise RuntimeError(f"synthetic {name} failure")

    def close_admission(self):
        self._step("close_admission")

    def fence_database_writes(self):
        self._step("fence_database_writes")

    def stop_writers(self):
        self._step("stop_writers")

    def verify_drain(self):
        self.verifications += 1
        name = f"verify_{self.verifications}"
        self._step(name)
        if self.fail == "truthy_not_bool":
            return ["writer still connected"]
        if self.fail == "false":
            return False
        return True

    def capture_snapshot(self):
        self._step("capture_snapshot")
        if self.receipt_override is not None:
            return self.receipt_override
        archive = self.backups / "g5-snapshot.dump"
        archive.write_bytes(b"synthetic PostgreSQL backup with commit 001\n")
        archive.chmod(0o600)
        return BackupReceipt(str(archive), hashlib.sha256(archive.read_bytes()).hexdigest())


@pytest.fixture
def scope(tmp_path):
    host = tmp_path / "host"
    state = host / ".ops-state"
    state.mkdir(parents=True, mode=0o700)
    host.chmod(0o700)
    state.chmod(0o700)
    backups = tmp_path / "backups"
    backups.mkdir(mode=0o700)
    request = PreparationRequest(
        str(host), str(backups), "g5-prepare-only-001",
        "a" * 40, "b" * 40, "medievol", "medievol_db",
    )
    return request, state, backups


def test_preparation_publishes_activated_before_mutating_and_stays_closed(scope):
    request, state, backups = scope
    port = FakePersistentBarrier(backups)
    previous_close = port.close_admission

    def check_marker_first():
        assert (state / MARKER).is_file()
        assert not (state / MANIFEST).exists()
        previous_close()

    port.close_admission = check_marker_first
    result = G5Preparation().prepare(request, port)
    assert result.phase is Phase.PREPARED
    assert result.identity.operation_id == request.operation_id
    assert result.identity.backup_sha256 == hashlib.sha256(
        (backups / "g5-snapshot.dump").read_bytes()
    ).hexdigest()
    assert port.calls == [
        "close_admission", "fence_database_writes", "stop_writers",
        "verify_1", "capture_snapshot", "verify_2",
    ]
    assert (state / MARKER).is_file()
    assert CutoverStore(request.host_root).show() == result
    assert (state / MANIFEST).is_file()

    # Already-armed cutovers never reenter the adapter or take a fresh backup.
    again = FakePersistentBarrier(backups)
    with pytest.raises(StateError, match="already exists"):
        G5Preparation().prepare(request, again)
    assert again.calls == []


@pytest.mark.parametrize(
    "failed_at",
    [
        "close_admission", "fence_database_writes", "stop_writers",
        "verify_1", "capture_snapshot", "verify_2",
    ],
)
def test_any_failure_before_persisting_backup_keeps_activation_and_blocks_retry(scope, failed_at):
    request, state, backups = scope
    port = FakePersistentBarrier(backups, fail=failed_at)
    with pytest.raises(RuntimeError, match="synthetic"):
        G5Preparation().prepare(request, port)
    assert port.calls[-1] == failed_at
    assert (state / MARKER).is_file()
    assert not (state / MANIFEST).exists()
    with pytest.raises(StateError, match="already exists"):
        G5Preparation().prepare(request, FakePersistentBarrier(backups))


@pytest.mark.parametrize("result", ["false", "truthy_not_bool"])
def test_drain_proof_must_be_literal_true_not_false_or_list(scope, result):
    request, state, backups = scope
    port = FakePersistentBarrier(backups, fail=result)
    with pytest.raises(StateError, match="not certified"):
        G5Preparation().prepare(request, port)
    assert port.calls == [
        "close_admission", "fence_database_writes", "stop_writers", "verify_1"
    ]
    assert (state / MARKER).is_file()
    assert not (state / MANIFEST).exists()
    assert not (backups / "g5-snapshot.dump").exists()


@pytest.mark.parametrize("tamper", ["wrong_hash", "foreign_path", "symlink", "nonreceipt", "archive_missing"])
def test_invalid_snapshot_never_publishes_prepared(scope, tamper):
    request, state, backups = scope
    port = FakePersistentBarrier(backups)
    archive = backups / "g5-snapshot.dump"
    if tamper == "wrong_hash":
        archive.write_bytes(b"synthetic archive")
        archive.chmod(0o600)
        port.receipt_override = BackupReceipt(str(archive), "f" * 64)
    elif tamper == "foreign_path":
        outside = backups.parent / "outside.dump"
        outside.write_bytes(b"synthetic archive")
        outside.chmod(0o600)
        port.receipt_override = BackupReceipt(
            str(outside), hashlib.sha256(outside.read_bytes()).hexdigest()
        )
    elif tamper == "symlink":
        target = backups / "target.dump"
        target.write_bytes(b"synthetic archive")
        target.chmod(0o600)
        archive.symlink_to(target)
        port.receipt_override = BackupReceipt(
            str(archive), hashlib.sha256(target.read_bytes()).hexdigest()
        )
    elif tamper == "nonreceipt":
        port.receipt_override = "fake-success"
    else:
        port.receipt_override = BackupReceipt(str(archive), "a" * 64)

    with pytest.raises((OSError, StateError)):
        G5Preparation().prepare(request, port)
    assert port.calls == [
        "close_admission", "fence_database_writes", "stop_writers",
        "verify_1", "capture_snapshot", "verify_2",
    ] or port.calls == [
        "close_admission", "fence_database_writes", "stop_writers",
        "verify_1", "capture_snapshot",
    ]
    assert (state / MARKER).is_file()
    assert not (state / MANIFEST).exists()


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("operation_id", "../escape"),
        ("previous_sha", "not-a-sha"),
        ("candidate_sha", "a" * 40),
        ("compose_project", "CAPITALS"),
        ("postgres_db", "danger; DROP ROLE"),
        ("host_root", "/tmp/../escape"),
        ("backup_root", "/"),
    ],
)
def test_invalid_request_rejected_before_irreversible_activation(scope, field, bad):
    request, state, backups = scope
    with pytest.raises((StateError, ValueError)):
        replace(request, **{field: bad})
    assert not (state / MARKER).exists()
    assert not (state / MANIFEST).exists()


def test_existing_lock_rejects_before_adapter_or_activation(scope):
    request, state, backups = scope
    lock = state / "deploy.lock"
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    port = FakePersistentBarrier(backups)
    with lock.open("a+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(StateError, match="holds the lock"):
            G5Preparation().prepare(request, port)
    assert port.calls == []
    assert not (state / MARKER).exists()


def test_bad_receipt_cannot_become_backup_authority(scope):
    request, state, backups = scope
    port = FakePersistentBarrier(backups)
    with pytest.raises(StateError, match="snapshot checksum"):
        port.receipt_override = BackupReceipt(str(backups / "fake.dump"), "FAKE")
    assert not (state / MARKER).exists()
