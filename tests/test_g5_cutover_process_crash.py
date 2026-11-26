"""Process-death regressions for the supervised G5 lifecycle.

The port below models durable side effects with a journal; no database, Docker
daemon, host configuration or production service is accessed.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_activation_fence import MARKER
from ops.g5_cutover_lifecycle import G5Lifecycle, MigrationRejected
from ops.g5_cutover_prepare import BackupReceipt, PreparationRequest
from ops.g5_cutover_state import CutoverStore, Phase, StateError


def make_request(root):
    return PreparationRequest(str(root / "host"), str(root / "backup"),
                              "crash-drill", "a" * 40, "b" * 40,
                              "crash_ci", "game_ci")


class CrashPort:
    def __init__(self, root, kill_at):
        self.root = root
        self.kill_at = kill_at
        self.checked = False

    def event(self, name):
        # The test observes a completed external side effect immediately
        # before the caller would receive its acknowledgement.
        with (self.root / "events").open("a", encoding="ascii") as stream:
            stream.write(name + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if name == self.kill_at:
            os.kill(os.getpid(), signal.SIGKILL)
            raise AssertionError("SIGKILL unexpectedly returned")

    def close_admission(self):
        self.event("close")

    def fence_database_writes(self):
        self.event("fence")

    def stop_writers(self):
        self.event("stop")

    def verify_drain(self):
        return True

    def capture_snapshot(self):
        payload = b"confirmed pre-cutover fixture"
        archive = self.root / "backup" / "snapshot.dump"
        fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(archive.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self.event("snapshot")
        return BackupReceipt(str(archive), hashlib.sha256(payload).hexdigest())

    def verify_continuity(self, identity):
        if not self.checked:
            self.checked = True
            self.event("prepared")
        return True

    def migrate(self, identity):
        self.event("migrate")
        if self.kill_at in ("restore", "verify_previous"):
            raise MigrationRejected("fixture executor exited with known rejection")

    def verify_candidate_readonly(self, identity):
        self.event("verify_candidate")
        return True

    def publish_candidate(self, identity):
        self.event("publish")

    def reopen_writers(self, identity):
        self.event("reopen")

    def restore_previous(self, identity, verified_fd):
        assert os.read(verified_fd, 4096) == b"confirmed pre-cutover fixture"
        self.event("restore")

    def verify_previous_readonly(self, identity):
        self.event("verify_previous")
        return True


FORWARD = ("close", "fence", "stop", "snapshot", "prepared", "migrate",
           "verify_candidate", "publish", "reopen")
REJECTED = FORWARD[:6] + ("restore", "verify_previous")


@pytest.mark.parametrize("stage,phase", [
    ("close", None),
    ("fence", None),
    ("stop", None),
    ("snapshot", None),
    ("prepared", Phase.PREPARED),
    ("migrate", Phase.MIGRATING),
    ("verify_candidate", Phase.MIGRATING),
    ("publish", Phase.VERIFIED_READONLY),
    ("restore", Phase.MIGRATING),
    ("verify_previous", Phase.MIGRATING),
    ("reopen", Phase.COMMITTED_WRITERS_ALLOWED),
])
def test_sigkill_preserves_last_phase_and_blocks_new_lifecycle(tmp_path, stage, phase):
    root = tmp_path.resolve()
    request = make_request(root)
    state = root / "host" / ".ops-state"
    state.mkdir(parents=True, mode=0o700)
    (root / "backup").mkdir(mode=0o700)

    # An actual separate process dies; no Python finally/except runs.
    child = subprocess.run([sys.executable, __file__, "--crash-child", str(root), stage],
                           capture_output=True, text=True, timeout=20)
    assert child.returncode == -signal.SIGKILL, child.stderr
    assert (state / MARKER).read_text() == "version=1\noperation_id=crash-drill\n"

    expected = REJECTED if stage in REJECTED[6:] else FORWARD
    expected = expected[:expected.index(stage) + 1]
    journal = root / "events"
    assert tuple(journal.read_text().splitlines()) == expected

    # Death releases the kernel lease, but the durable marker refuses a
    # new attempt even if a new process could now obtain deploy.lock.
    with (state / "deploy.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_UN)

    store = CutoverStore(request.host_root)
    if phase is None:
        with pytest.raises(StateError, match="missing"):
            store.show()
    else:
        manifest = store.show()
        assert manifest.phase is phase
        assert manifest.identity.operation_id == request.operation_id
        if phase is Phase.COMMITTED_WRITERS_ALLOWED:
            # A crash after issuing reopen cannot authorize stale restore.
            with pytest.raises(StateError, match="forbids"):
                with store.verify_restore_allowed(manifest.identity, request.backup_root):
                    pytest.fail("postcommit stale snapshot authorized")

    before = journal.read_bytes()
    with pytest.raises(StateError, match="already exists"):
        G5Lifecycle().execute(request, CrashPort(root, None))
    assert journal.read_bytes() == before
    assert (state / MARKER).is_file()
    if phase is not None:
        assert store.show() == manifest


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--crash-child":
        raise SystemExit(2)
    root = Path(sys.argv[2])
    G5Lifecycle().execute(make_request(root), CrashPort(root, sys.argv[3]))
    raise SystemExit("expected process death did not occur")
