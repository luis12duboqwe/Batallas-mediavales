"""Durable, one-way activation fence for a future supervised G5 cutover.

The fence deliberately does not drain writers, back up a DB or reopen access.
It acquires the *same* deploy.lock as legacy scripts, publishes a 0600
fsync'd marker before yielding to any caller, and never deletes that marker.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
import re
import stat

from ops.g5_cutover_state import CutoverStore, StateError, _stamp


MARKER = "g5-cutover-activated"
DEPLOY_LOCK = "deploy.lock"
OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def _entry(directory: int, name: str):
    try:
        return os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _identity(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid


def _check_lock(directory: int, lock_fd: int) -> None:
    fd_info = os.fstat(lock_fd)
    at_path = _entry(directory, DEPLOY_LOCK)
    if (at_path is None or _identity(fd_info) != _identity(at_path)
        or not stat.S_ISREG(fd_info.st_mode) or fd_info.st_uid != os.geteuid()
        or stat.S_IMODE(fd_info.st_mode) != 0o600 or fd_info.st_nlink != 1):
        raise StateError("unsafe or replaced deploy.lock")


def _check_marker(directory: int, expected) -> None:
    current = _entry(directory, MARKER)
    if (current is None or _stamp(current) != _stamp(expected)
        or not stat.S_ISREG(current.st_mode) or
        stat.S_IMODE(current.st_mode) != 0o600 or
        current.st_uid != os.geteuid() or current.st_nlink != 1):
        raise StateError("G5 activation marker changed or disappeared")


@contextmanager
def arm_cutover(host_root: str, operation_id: str):
    """Hold the legacy release lock and a durable 'do not use legacy' marker.

    This is NOT a usable cutover manager or a backup authorization. If the body
    raises or the host crashes, the marker intentionally remains. No automatic
    cleanup or unarm method exists.
    """
    if not isinstance(operation_id, str) or not OPERATION_ID.fullmatch(operation_id):
        raise StateError("invalid G5 operation ID")

    owner_pid = os.getpid()
    store = CutoverStore(os.fspath(host_root))
    with store._state_directory() as directory:
        state_identity = _identity(os.fstat(directory))
        lock_fd = os.open(
            DEPLOY_LOCK,
            os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=directory,
        )
        try:
            _check_lock(directory, lock_fd)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StateError("another deploy, rollback or G5 cutover holds the lock") from exc
            try:
                _check_lock(directory, lock_fd)
                # An existing manifest (including a corrupt/dangling symlink)
                # is a prior incident, never proof of a fresh activation.
                for name in (MARKER, "g5-cutover.json", "recovery-required"):
                    if _entry(directory, name) is not None:
                        raise StateError("G5 or recovery state already exists; reconcile manually")
                # Legacy recovery can leave an orphaned hardlink if publishing
                # the canonical marker failed (ENOSPC/fsync/race). The legacy
                # entrypoints already reject these; G5 must not bypass them.
                # listdir on the pinned private dirfd observes names without
                # dereferencing a malicious symlink or opening an attacker file.
                if any(name.startswith("recovery-required.") for name in os.listdir(directory)):
                    raise StateError("orphaned recovery evidence blocks G5 activation")

                marker_fd = os.open(
                    MARKER,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600, dir_fd=directory,
                )
                try:
                    payload = f"version=1\noperation_id={operation_id}\n".encode("ascii")
                    offset = 0
                    while offset < len(payload):
                        written = os.write(marker_fd, payload[offset:])
                        if written <= 0:
                            raise StateError("G5 activation marker write failed")
                        offset += written
                    os.fchmod(marker_fd, 0o600)
                    os.fsync(marker_fd)
                    expected = os.fstat(marker_fd)
                finally:
                    os.close(marker_fd)
                # The marker must be durable *before* a caller may close
                # admission, stop processes, or take a snapshot.
                os.fsync(directory)
                _check_marker(directory, expected)
                _check_lock(directory, lock_fd)
                if _identity(os.fstat(directory)) != state_identity:
                    raise StateError("state directory changed during activation")
                active = True

                def assert_active():
                    if not active or os.getpid() != owner_pid:
                        raise StateError("G5 activation lease is no longer active in this process")
                    _check_marker(directory, expected)
                    _check_lock(directory, lock_fd)
                    store._check_directory(directory, state_identity)

                try:
                    assert_active()
                    yield assert_active
                finally:
                    # Never remove the marker, even after an exception.
                    # Existing legacy entrypoints will continue to refuse.
                    try:
                        assert_active()
                    finally:
                        active = False
            finally:
                # A forked child inherits the same open file description.
                # It must not unlock the parent's active deployment lease.
                if os.getpid() == owner_pid:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
