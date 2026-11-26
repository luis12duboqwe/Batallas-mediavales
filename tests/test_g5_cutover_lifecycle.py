"""Regression and adversarial ordering tests of the single-lease lifecycle."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_activation_fence import MARKER, arm_cutover
from ops.g5_cutover_lifecycle import G5Lifecycle, MigrationRejected, RecoveryRequired
from ops.g5_cutover_prepare import BackupReceipt, PreparationRequest
from ops.g5_cutover_state import CutoverStore, Phase, StateError


@pytest.fixture
def request_scope(tmp_path):
    root = tmp_path / "host"
    root.mkdir(mode=0o700)
    (root / ".ops-state").mkdir(mode=0o700)
    backups = tmp_path / "backup"
    backups.mkdir(mode=0o700)
    return PreparationRequest(str(root), str(backups), "ci-lifecycle",
                              "a" * 40, "b" * 40, "ci_project", "game_ci")


class Port:
    """Synthetic adapter used only to test ordering and failure classification."""
    def __init__(self, request, fail=None):
        self.request = request
        self.store = CutoverStore(request.host_root)
        self.state = Path(request.host_root) / ".ops-state"
        self.archive = Path(request.backup_root) / "test.dump"
        self.calls = []
        self.fail = fail
        self.continuity_checks = 0
        self.data = b"confirmed previous data"
        self.publication = None

    def step(self, name):
        self.calls.append(name)
        assert (self.state / MARKER).is_file()
        with (self.state / "deploy.lock").open("a+") as fd:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if self.fail == name:
            raise RuntimeError("synthetic " + name)

    def close_admission(self):
        self.step("close")

    def fence_database_writes(self):
        self.step("fence")

    def stop_writers(self):
        self.step("stop")

    def verify_drain(self):
        self.step("drain")
        return True

    def capture_snapshot(self):
        self.step("snapshot")
        self.archive.write_bytes(self.data)
        self.archive.chmod(0o600)
        return BackupReceipt(str(self.archive), hashlib.sha256(self.data).hexdigest())

    def verify_continuity(self, identity):
        self.step("continuity")
        self.continuity_checks += 1
        assert identity.operation_id == self.request.operation_id
        if self.fail == "ambiguous_barrier":
            return ["not established"]
        if self.fail == "lost_barrier" and "migrate" in self.calls:
            return False
        return True

    def locked_phase(self, expected):
        # Read the persisted fixture receipt, not a recursive store lock.
        payload = json.loads((self.state / "g5-cutover.json").read_text())["manifest"]
        assert payload["phase"] == expected.value
        with pytest.raises(BlockingIOError):
            self.store.show()

    def migrate(self, identity):
        self.step("migrate")
        self.locked_phase(Phase.MIGRATING)
        self.data = b"candidate schema mutations"
        if self.fail in {"rejected", "rejected_lost_barrier", "tampered_archive",
                         "restore_error", "previous_unverified"}:
            if self.fail == "tampered_archive":
                self.archive.write_bytes(b"tampered")
            raise MigrationRejected("known failed migration with executor terminated")
        if self.fail == "interrupted":
            raise KeyboardInterrupt()

    def verify_candidate_readonly(self, identity):
        self.step("verify_candidate")
        assert self.store.show().phase is Phase.MIGRATING
        return self.fail != "candidate_false"

    def publish_candidate(self, identity):
        self.step("publish")
        self.locked_phase(Phase.VERIFIED_READONLY)
        self.publication = identity.candidate_sha

    def restore_previous(self, identity, verified_fd):
        self.step("restore")
        assert self.publication is None
        # The manifest lock is held during FD consumption.
        with pytest.raises(BlockingIOError):
            self.store.show()
        if self.fail == "restore_error":
            raise RuntimeError("restore failed")
        self.data = os.read(verified_fd, 1024)

    def verify_previous_readonly(self, identity):
        self.step("verify_previous")
        return self.fail != "previous_unverified" and self.data == b"confirmed previous data"

    def reopen_writers(self, identity):
        self.step("reopen")
        self.locked_phase(Phase.COMMITTED_WRITERS_ALLOWED)
        assert self.publication == identity.candidate_sha
        with pytest.raises(BlockingIOError):
            with self.store.verify_restore_allowed(identity, self.request.backup_root):
                pytest.fail("competing restore acquired lock during reopen")


def test_commit_before_reopen_with_same_lease(request_scope):
    port = Port(request_scope)
    result = G5Lifecycle().execute(request_scope, port)
    assert result.phase is Phase.COMMITTED_WRITERS_ALLOWED
    assert port.store.show() == result
    assert [c for c in port.calls if c != "continuity"] == [
        "close", "fence", "stop", "drain", "snapshot", "drain",
        "migrate", "verify_candidate", "publish", "reopen",
    ]
    assert "restore" not in port.calls
    with pytest.raises(StateError, match="already exists"):
        G5Lifecycle().execute(request_scope, Port(request_scope))


def test_known_rejection_restores_verified_fd_and_never_reopens(request_scope):
    port = Port(request_scope, "rejected")
    with pytest.raises(RecoveryRequired, match="previous data restored"):
        G5Lifecycle().execute(request_scope, port)
    assert port.data == b"confirmed previous data"
    assert port.store.show().phase is Phase.RECOVERY_REQUIRED
    assert "restore" in port.calls and "verify_previous" in port.calls
    assert "publish" not in port.calls and "reopen" not in port.calls
    with pytest.raises(StateError, match="forbids"):
        with port.store.verify_restore_allowed(port.store.show().identity, request_scope.backup_root):
            pytest.fail("incident is not permission for a second restore")


@pytest.mark.parametrize("failure", [
    "ambiguous_barrier", "lost_barrier", "migrate", "interrupted",
    "candidate_false", "verify_candidate", "publish", "tampered_archive",
    "restore_error", "previous_unverified",
])
def test_precommit_uncertainty_never_reopens_or_unconditionally_restores(request_scope, failure):
    port = Port(request_scope, failure)
    with pytest.raises((StateError, RuntimeError, KeyboardInterrupt)):
        G5Lifecycle().execute(request_scope, port)
    assert port.store.show().phase is Phase.RECOVERY_REQUIRED
    assert "reopen" not in port.calls
    if failure not in {"restore_error", "previous_unverified"}:
        assert "restore" not in port.calls
    assert (port.state / MARKER).exists()


def test_known_rejection_without_continuity_never_restores(request_scope):
    port = Port(request_scope, "rejected_lost_barrier")
    original = port.verify_continuity
    port.verify_continuity = lambda identity: (
        False if "migrate" in port.calls else original(identity)
    )
    with pytest.raises(StateError, match="continuous"):
        G5Lifecycle().execute(request_scope, port)
    assert port.store.show().phase is Phase.RECOVERY_REQUIRED
    assert "restore" not in port.calls and "reopen" not in port.calls


def test_failure_after_commit_never_downgrades_or_restores(request_scope):
    port = Port(request_scope, "reopen")
    with pytest.raises(RuntimeError, match="synthetic reopen"):
        G5Lifecycle().execute(request_scope, port)
    manifest = port.store.show()
    assert manifest.phase is Phase.COMMITTED_WRITERS_ALLOWED
    assert "restore" not in port.calls
    with pytest.raises(StateError, match="forbids"):
        with port.store.verify_restore_allowed(manifest.identity, request_scope.backup_root):
            pytest.fail("postcommit incident must never restore")


@pytest.mark.parametrize("drift", ["marker", "manifest"])
def test_tampered_authority_before_reopen_never_reopens(request_scope, drift):
    port = Port(request_scope)
    original = port.publish_candidate

    def change(identity):
        original(identity)
        if drift == "marker":
            (port.state / MARKER).write_text("changed operation")
        else:
            (port.state / "g5-cutover.json").write_text("corrupt")
    port.publish_candidate = change
    with pytest.raises(StateError):
        G5Lifecycle().execute(request_scope, port)
    assert "restore" not in port.calls and "reopen" not in port.calls


def test_activation_lease_rejects_use_after_exit(request_scope):
    with arm_cutover(request_scope.host_root, request_scope.operation_id) as lease:
        lease()
    with pytest.raises(StateError, match="no longer active"):
        lease()


def test_continuity_lost_after_commit_but_before_login_is_not_rollback_permission(request_scope):
    port = Port(request_scope)
    original = port.verify_continuity

    def drift(identity):
        if port.publication and port.store.show().phase is Phase.COMMITTED_WRITERS_ALLOWED:
            return False
        return original(identity)

    port.verify_continuity = drift
    with pytest.raises(StateError, match="continuous"):
        G5Lifecycle().execute(request_scope, port)
    assert port.store.show().phase is Phase.COMMITTED_WRITERS_ALLOWED
    assert "reopen" not in port.calls and "restore" not in port.calls


def test_lease_checks_marker_changes_during_active_context(request_scope):
    with pytest.raises(StateError, match="marker changed"):
        with arm_cutover(request_scope.host_root, request_scope.operation_id) as lease:
            marker = Path(request_scope.host_root) / ".ops-state" / MARKER
            marker.write_text("version=1\noperation_id=another\n")
            with pytest.raises(StateError, match="marker changed"):
                lease()


@pytest.mark.parametrize("race", ["before_restore", "before_backup_verification"])
def test_exact_phase_is_checked_inside_archive_lock(request_scope, monkeypatch, race):
    port = Port(request_scope, "rejected" if race == "before_restore" else None)
    original = CutoverStore.verify_restore_allowed
    raced = False

    def interleave(store, identity, backup_root, *, expected_phase=None):
        nonlocal raced
        if not raced and (
            (race == "before_restore" and expected_phase is Phase.MIGRATING)
            or (race == "before_backup_verification" and expected_phase is Phase.PREPARED)
        ):
            raced = True
            successor = {
                Phase.MIGRATING: Phase.VERIFIED_READONLY,
                Phase.PREPARED: Phase.MIGRATING,
            }[expected_phase]
            store.advance(identity, expected_phase, successor)
        return original(store, identity, backup_root, expected_phase=expected_phase)

    monkeypatch.setattr(CutoverStore, "verify_restore_allowed", interleave)
    with pytest.raises(StateError, match="unexpected exact restore phase"):
        G5Lifecycle().execute(request_scope, port)
    assert raced
    assert port.store.show().phase is Phase.RECOVERY_REQUIRED
    assert "restore" not in port.calls and "reopen" not in port.calls
    if race == "before_restore":
        assert port.data == b"candidate schema mutations"
    else:
        assert "migrate" not in port.calls


def test_archive_phase_argument_rejects_non_enum(request_scope):
    port = Port(request_scope)
    from ops.g5_cutover_prepare import G5Preparation
    manifest = G5Preparation().prepare(request_scope, port)
    with pytest.raises(StateError, match="invalid expected restore phase"):
        with port.store.verify_restore_allowed(
            manifest.identity, request_scope.backup_root, expected_phase="PREPARED"
        ):
            pytest.fail("non-enum expected phase accepted")


@pytest.mark.parametrize("expected,action", [
    (Phase.MIGRATING, "migrate"),
    (Phase.VERIFIED_READONLY, "publish"),
])
def test_phase_race_before_sensitive_mutation_is_refused(request_scope, monkeypatch, expected, action):
    port = Port(request_scope)
    original = CutoverStore.hold_phase
    raced = False

    def interleave(store, identity, phase):
        nonlocal raced
        if not raced and phase is expected:
            raced = True
            store.advance(identity, phase, Phase.RECOVERY_REQUIRED)
        return original(store, identity, phase)

    monkeypatch.setattr(CutoverStore, "hold_phase", interleave)
    with pytest.raises(StateError, match="unexpected exact cutover phase"):
        G5Lifecycle().execute(request_scope, port)
    assert raced
    assert port.store.show().phase is Phase.RECOVERY_REQUIRED
    assert action not in port.calls
    assert "restore" not in port.calls and "reopen" not in port.calls


@pytest.mark.parametrize("method,phase", [
    ("migrate", Phase.MIGRATING),
    ("publish_candidate", Phase.VERIFIED_READONLY),
    ("reopen_writers", Phase.COMMITTED_WRITERS_ALLOWED),
])
def test_competing_manifest_writer_is_excluded_through_callback(request_scope, method, phase):
    port = Port(request_scope)
    original = getattr(port, method)

    def compete(identity):
        with pytest.raises(BlockingIOError):
            port.store.advance(identity, phase, Phase.RECOVERY_REQUIRED)
        original(identity)

    setattr(port, method, compete)
    assert G5Lifecycle().execute(request_scope, port).phase is Phase.COMMITTED_WRITERS_ALLOWED


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Linux flock/fork regression")
def test_forked_child_cannot_release_parent_activation_lease(request_scope):
    context = arm_cutover(request_scope.host_root, request_scope.operation_id)
    lease = context.__enter__()
    try:
        pid = os.fork()
        if pid == 0:
            try:
                context.__exit__(None, None, None)
            except StateError:
                os._exit(0)
            except BaseException:
                os._exit(2)
            os._exit(1)
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        lease()
        lock = Path(request_scope.host_root) / ".ops-state" / "deploy.lock"
        with lock.open("a+") as competitor:
            with pytest.raises(BlockingIOError):
                fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        context.__exit__(None, None, None)
