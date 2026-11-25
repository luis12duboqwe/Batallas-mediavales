"""Regression and adversarial ordering tests of the single-lease lifecycle."""
from __future__ import annotations

import fcntl
import hashlib
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

    def migrate(self, identity):
        self.step("migrate")
        assert self.store.show().phase is Phase.MIGRATING
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
        assert self.store.show().phase is Phase.VERIFIED_READONLY
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
        assert self.store.show().phase is Phase.COMMITTED_WRITERS_ALLOWED
        assert self.publication == identity.candidate_sha
        with pytest.raises(StateError, match="forbids"):
            with self.store.verify_restore_allowed(identity, self.request.backup_root):
                pytest.fail("committed operation still permits restore")


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
