"""G5 activation barrier: isolated fail-closed tests, never a real deployment."""
from pathlib import Path
import fcntl
import os
import stat
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_activation_fence import MARKER, arm_cutover
from ops.g5_cutover_state import StateError


@pytest.fixture
def release(tmp_path):
    root = tmp_path / "release"
    state = root / ".ops-state"
    state.mkdir(parents=True)
    root.chmod(0o700)
    state.chmod(0o700)
    return root, state


def test_arm_publishes_durable_marker_before_yield_and_never_unarms(release):
    root, state = release
    marker = state / MARKER
    assert not marker.exists()
    with arm_cutover(str(root), "g5-safe-001"):
        assert marker.read_text() == "version=1\noperation_id=g5-safe-001\n"
        assert stat.S_IMODE(marker.stat().st_mode) == 0o600
        assert stat.S_IMODE((state / "deploy.lock").stat().st_mode) == 0o600
        assert marker.stat().st_nlink == 1
    assert marker.is_file()
    assert "g5-safe-001" in marker.read_text()
    with pytest.raises(StateError, match="already exists"):
        with arm_cutover(str(root), "g5-safe-002"):
            pytest.fail("Cannot create another cutover after activation")


def test_worker_error_does_not_reopen_legacy_entrypoints(release):
    root, state = release
    with pytest.raises(RuntimeError, match="failed after activation"):
        with arm_cutover(str(root), "fail-in-body"):
            raise RuntimeError("failed after activation")
    assert (state / MARKER).is_file()
    with pytest.raises(StateError, match="already exists"):
        with arm_cutover(str(root), "retry"):
            pytest.fail("A failed cutover must remain blocked")


@pytest.mark.parametrize("kind", ["regular", "directory", "dangling-symlink"])
def test_orphaned_legacy_recovery_receipt_blocks_new_activation(release, kind):
    root, state = release
    receipt = state / "recovery-required.unresolved"
    if kind == "regular":
        receipt.write_text("reason=failed_recovery_marker_publication\\n")
    elif kind == "directory":
        receipt.mkdir()
    else:
        receipt.symlink_to(state / "missing")
    with pytest.raises(StateError, match="orphaned recovery evidence"):
        with arm_cutover(str(root), "must-not-bypass-incident"):
            pytest.fail("G5 must refuse a legacy incident even without canonical marker")
    assert not (state / MARKER).exists()
    assert receipt.is_symlink() or receipt.exists()


@pytest.mark.parametrize("previous", ["g5-cutover.json", MARKER, "recovery-required"])
@pytest.mark.parametrize("kind", ["file", "directory", "dangling-symlink"])
def test_prior_cutover_or_incident_is_fail_closed(release, previous, kind):
    root, state = release
    obstacle = state / previous
    if kind == "file":
        obstacle.write_bytes(b"malformed/untrusted previous incident")
    elif kind == "directory":
        obstacle.mkdir()
    else:
        obstacle.symlink_to(state / "missing")
    with pytest.raises(StateError, match="already exists"):
        with arm_cutover(str(root), "fresh-operation"):
            pytest.fail("Must not overwrite a prior incident")
    assert obstacle.exists() or obstacle.is_symlink()
    if previous != MARKER:
        assert not (state / MARKER).exists()


@pytest.mark.parametrize("name", ["", "../bad", "spaces bad", "bad\nnext=x",
                                    "x" * 129, "á", "a/b", "x;touch hacked"])
def test_operation_identity_is_validated_before_writing(release, name):
    root, state = release
    with pytest.raises(StateError, match="operation ID"):
        with arm_cutover(str(root), name):
            pytest.fail("Invalid identity activated")
    assert not (state / MARKER).exists()
    assert not (state / "deploy.lock").exists()


def test_legacy_deploy_lock_prevents_activation(release):
    root, state = release
    lock = state / "deploy.lock"
    with lock.open("a+") as held:
        os.chmod(lock, 0o600)
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(StateError, match="holds the lock"):
            with arm_cutover(str(root), "g5-lock-test"):
                pytest.fail("Must not arm during legacy operation")
        fcntl.flock(held.fileno(), fcntl.LOCK_UN)
    assert not (state / MARKER).exists()
    with arm_cutover(str(root), "g5-after-lock"):
        assert (state / MARKER).exists()


def test_armed_cutover_holds_lock_for_full_context(release):
    root, state = release
    with arm_cutover(str(root), "g5-owns-lock"):
        with (state / "deploy.lock").open("a+") as another:
            with pytest.raises(BlockingIOError):
                fcntl.flock(another.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "world-readable", "directory"])
def test_unsafe_legacy_lock_is_rejected_before_marker(release, kind):
    root, state = release
    lock = state / "deploy.lock"
    if kind == "symlink":
        lock.symlink_to(state / "absent")
    elif kind == "directory":
        lock.mkdir()
    else:
        lock.write_text("")
        lock.chmod(0o600)
        if kind == "hardlink":
            os.link(lock, state / "linked-lock")
        else:
            lock.chmod(0o644)
    with pytest.raises((StateError, OSError)):
        with arm_cutover(str(root), "g5-unsafe-lock"):
            pytest.fail("Unsafe deploy lock activated")
    assert not (state / MARKER).exists()


def test_linked_state_directory_is_never_followed(release):
    root, state = release
    original = root / "moved-state"
    state.rename(original)
    state.symlink_to(original)
    with pytest.raises((StateError, OSError)):
        with arm_cutover(str(root), "g5-state-link"):
            pytest.fail("Followed symlinked .ops-state")
    assert state.is_symlink()
    assert not (original / MARKER).exists()


def test_world_writable_state_directory_is_rejected(release):
    root, state = release
    state.chmod(0o777)
    with pytest.raises((StateError, OSError)):
        with arm_cutover(str(root), "g5-bad-perms"):
            pytest.fail("Armed in unsafe state directory")
    assert not (state / MARKER).exists()


def test_marker_is_fail_closed_if_sync_fails(release, monkeypatch):
    root, state = release
    real_fsync = os.fsync
    raised = [False]

    def fail_first_fsync(fd):
        if not raised[0]:
            raised[0] = True
            raise OSError("synthetic fsync outage")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_first_fsync)
    with pytest.raises(OSError, match="fsync outage"):
        with arm_cutover(str(root), "g5-sync-failed"):
            pytest.fail("Unsafe sync must not yield")
    # Partial/uncertain marker MUST NOT be cleaned up automatically.
    assert (state / MARKER).exists()
    with pytest.raises(StateError, match="already exists"):
        with arm_cutover(str(root), "g5-must-not-retry"):
            pytest.fail("Must fail closed after uncertain fsync")


def test_marker_removal_during_context_is_detected(release):
    root, state = release
    with pytest.raises(StateError, match="marker changed or disappeared"):
        with arm_cutover(str(root), "g5-removal"):
            (state / MARKER).unlink()


def test_two_competing_activations_cannot_both_succeed(release):
    root, state = release
    entered = threading.Event()
    finish = threading.Event()
    outcome = []

    def first():
        with arm_cutover(str(root), "first"):
            entered.set()
            assert finish.wait(timeout=4)

    worker = threading.Thread(target=first, daemon=True)
    worker.start()
    try:
        assert entered.wait(timeout=3)
        with pytest.raises(StateError, match="holds the lock"):
            with arm_cutover(str(root), "second"):
                pytest.fail("Concurrent cutover bypassed release lock")
        outcome.append((state / MARKER).read_text())
    finally:
        finish.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert outcome == ["version=1\noperation_id=first\n"]


@pytest.mark.parametrize("script", [
    "deploy_remote.sh", "rollback_remote.sh", "restore_postgres.sh"
])
def test_activated_marker_blocks_real_legacy_entrypoint_without_docker(release, script):
    """Integration with the actual historical scripts, without starting services."""
    import shutil
    import subprocess

    root, state = release
    ops = root / "ops"
    ops.mkdir()
    shutil.copy2(Path(__file__).resolve().parents[1] / "ops" / script, ops / script)
    (root / "base.env").write_text("APP_ENV=staging\\n")
    sha = "b" * 40
    arguments = {
        "deploy_remote.sh": ["base.env", sha, "registry.invalid/b", "registry.invalid/f"],
        "rollback_remote.sh": [sha, "ROLLBACK:" + sha],
        "restore_postgres.sh": ["base.env", "not-real.dump", "RESTORE:synthetic"],
    }[script]
    with arm_cutover(str(root), "g5-script-integration"):
        assert (state / MARKER).is_file()
    result = subprocess.run(
        ["bash", "ops/" + script, *arguments], cwd=root,
        capture_output=True, text=True, check=False, timeout=8,
    )
    assert result.returncode == 2, result.stderr
    assert "Legacy G5 operation refused" in result.stderr
    assert (state / MARKER).is_file()
    assert not (root / ".release.env.next").exists()


def test_non_string_operation_identity_is_rejected(release):
    root, state = release
    with pytest.raises(StateError, match="operation ID"):
        with arm_cutover(str(root), None):
            pytest.fail("Non-string ID accepted")
    assert not (state / MARKER).exists()
