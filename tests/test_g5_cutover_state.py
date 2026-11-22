import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import os
import select
import signal
import stat
import subprocess
import sys
from threading import Barrier

import pytest

# CI uses pytest.ini pythonpath=batalla_medieval_backend, not the repo root.
# Make the standalone stdlib-only ops module importable in both local and CI.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops import g5_cutover_state as cutover
from ops.g5_cutover_state import CutoverStore, Identity, MANIFEST, Phase, StateError


@pytest.fixture
def scope(tmp_path):
    host = tmp_path / "release"
    state = host / ".ops-state"
    state.mkdir(parents=True, mode=0o700)
    backups = tmp_path / "backups"
    backups.mkdir(mode=0o700)
    archive = backups / "previous.dump"
    archive.write_bytes(b"verified snapshot")
    archive.chmod(0o600)
    identity = Identity("cutover-1", "a" * 40, "b" * 40,
                        hashlib.sha256(archive.read_bytes()).hexdigest(),
                        str(archive), "medievol", "medievol_db")
    return CutoverStore(host), identity, backups, state / MANIFEST


def check_restore(store, identity, backups):
    with store.verify_restore_allowed(identity, backups) as fd:
        assert cutover.os.read(fd, 1024) == b"verified snapshot"


def test_commit_is_terminal(scope):
    store, identity, backups, path = scope
    with pytest.raises(StateError, match="missing"):
        check_restore(store, identity, backups)
    assert store.prepare(identity, backups).phase == Phase.PREPARED
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    check_restore(store, identity, backups)
    sequence = (Phase.PREPARED, Phase.MIGRATING, Phase.VERIFIED_READONLY,
                Phase.COMMITTED_WRITERS_ALLOWED)
    for before, after in zip(sequence, sequence[1:]):
        assert store.advance(identity, before, after).phase == after
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        if after in cutover.RESTORE_PHASES:
            check_restore(store, identity, backups)
    with pytest.raises(StateError, match="forbids"):
        check_restore(store, identity, backups)
    for target in Phase:
        with pytest.raises(StateError, match="forbidden"):
            store.advance(identity, Phase.COMMITTED_WRITERS_ALLOWED, target)
    with pytest.raises(StateError, match="occupied"):
        store.prepare(replace(identity, operation_id="cutover-2"), backups)


def test_phase_order_and_recovery(scope):
    store, identity, backups, _ = scope
    store.prepare(identity, backups)
    with pytest.raises(StateError, match="forbidden"):
        store.advance(identity, Phase.PREPARED, Phase.VERIFIED_READONLY)
    store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
    with pytest.raises(StateError, match="unexpected"):
        store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
    with pytest.raises(StateError, match="forbidden"):
        store.advance(identity, Phase.MIGRATING, Phase.PREPARED)
    store.advance(identity, Phase.MIGRATING, Phase.RECOVERY_REQUIRED)
    with pytest.raises(StateError, match="forbids"):
        check_restore(store, identity, backups)
    with pytest.raises(StateError, match="forbidden"):
        store.advance(identity, Phase.RECOVERY_REQUIRED, Phase.PREPARED)


@pytest.mark.parametrize("changes", [
    {"operation_id": "cutover-2"}, {"backup_sha256": "1" * 64},
    {"previous_sha": "2" * 40}, {"candidate_sha": "3" * 40},
    {"compose_project": "other"}, {"postgres_db": "other"},
])
def test_cross_operation_and_identity_mismatch(scope, changes):
    store, identity, backups, _ = scope
    store.prepare(identity, backups)
    other = replace(identity, **changes)
    with pytest.raises(StateError, match="identity mismatch"):
        check_restore(store, other, backups)
    with pytest.raises(StateError, match="identity mismatch"):
        store.advance(other, Phase.PREPARED, Phase.MIGRATING)


@pytest.mark.parametrize("raw", [b"", b'{"manifest":', b'{"manifest":null,"manifest":null}', b"\xff"])
def test_corrupt_state_refuses_reinitialization(scope, raw):
    store, identity, backups, path = scope
    store.prepare(identity, backups)
    path.write_bytes(raw)
    with pytest.raises(StateError):
        check_restore(store, identity, backups)
    with pytest.raises(StateError):
        store.prepare(identity, backups)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("phase", ["UNKNOWN", "PREPARED"])
def test_modified_manifest(scope, phase):
    store, identity, backups, path = scope
    store.prepare(identity, backups)
    store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
    envelope = json.loads(path.read_bytes())
    envelope["manifest"]["phase"] = phase
    if phase == "UNKNOWN":
        envelope["sha256"] = hashlib.sha256(cutover._encode(envelope["manifest"])).hexdigest()
    path.write_text(json.dumps(envelope))
    with pytest.raises(StateError, match="invalid"):
        check_restore(store, identity, backups)


@pytest.mark.parametrize("entry", ["manifest", "state_dir", "host", "backup", "backup_dir"])
def test_symlinks_refused(scope, entry):
    store, identity, backups, path = scope
    store.prepare(identity, backups)
    original = {"manifest": path, "state_dir": path.parent, "host": path.parent.parent,
                "backup": Path(identity.backup_path), "backup_dir": backups}[entry]
    moved = original.with_name(original.name + "-moved")
    original.rename(moved)
    original.symlink_to(moved)
    with pytest.raises(OSError):
        check_restore(store, identity, backups)
    if entry == "manifest":
        with pytest.raises(OSError):
            store.prepare(identity, backups)


def test_paths_and_backup_bytes(scope):
    store, identity, backups, _ = scope
    with pytest.raises(StateError):
        replace(identity, operation_id="../other")
    with pytest.raises(StateError):
        replace(identity, backup_path=f"{backups}/../outside.dump")
    with pytest.raises(StateError):
        CutoverStore(f"{backups}/../release")
    archive = Path(identity.backup_path)
    other = backups.with_name("backups-other")
    other.mkdir()
    outside = other / archive.name
    outside.write_bytes(archive.read_bytes())
    with pytest.raises(StateError, match="backup root"):
        store.prepare(replace(identity, backup_path=str(outside)), backups)
    with pytest.raises(StateError, match="checksum"):
        store.prepare(replace(identity, backup_sha256="1" * 64), backups)
    store.prepare(identity, backups)
    archive.write_bytes(b"unexpected bytes")
    with pytest.raises(StateError, match="checksum"):
        check_restore(store, identity, backups)
    archive.unlink()
    with pytest.raises(FileNotFoundError):
        check_restore(store, identity, backups)


def test_unsafe_manifest_permissions(scope):
    store, identity, backups, path = scope
    store.prepare(identity, backups)
    path.chmod(0o644)
    with pytest.raises(StateError, match="unsafe"):
        check_restore(store, identity, backups)


def test_missing_backup_prevents_prepare(scope):
    store, identity, backups, path = scope
    Path(identity.backup_path).unlink()
    with pytest.raises(FileNotFoundError):
        store.prepare(identity, backups)
    assert not path.exists()


def test_backup_replaced_during_verification(scope, monkeypatch):
    store, identity, backups, _ = scope
    store.prepare(identity, backups)
    archive = Path(identity.backup_path)
    replacement = archive.with_suffix(".replacement")
    replacement.write_bytes(archive.read_bytes())
    real_read = cutover.os.read

    def swap(fd, size):
        if cutover.os.path.samestat(cutover.os.fstat(fd), archive.stat()):
            replacement.replace(archive)
        return real_read(fd, size)

    monkeypatch.setattr(cutover.os, "read", swap)
    with pytest.raises(StateError, match="backup changed"):
        check_restore(store, identity, backups)


@pytest.mark.parametrize("failure", ["replace", "file_fsync", "dir_fsync"])
def test_publication_failures(scope, monkeypatch, failure):
    store, identity, backups, path = scope
    store.prepare(identity, backups)
    store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
    store.advance(identity, Phase.MIGRATING, Phase.VERIFIED_READONLY)
    original = path.read_bytes()
    fsync = cutover.os.fsync

    def fault(fd):
        is_dir = stat.S_ISDIR(cutover.os.fstat(fd).st_mode)
        if failure == ("dir_fsync" if is_dir else "file_fsync"):
            raise OSError("injected fsync failure")
        fsync(fd)

    def failed_replace(*args, **kwargs):
        raise OSError("injected replace failure")

    with monkeypatch.context() as patch:
        patch.setattr(cutover.os, "fsync", fault)
        if failure == "replace":
            patch.setattr(cutover.os, "replace", failed_replace)
        with pytest.raises(OSError, match="injected"):
            store.advance(identity, Phase.VERIFIED_READONLY, Phase.COMMITTED_WRITERS_ALLOWED)
    assert list(path.parent.iterdir()) == [path]
    if failure == "dir_fsync":
        assert store.show().phase == Phase.COMMITTED_WRITERS_ALLOWED
        with pytest.raises(StateError, match="forbids"):
            check_restore(store, identity, backups)
    else:
        assert path.read_bytes() == original
        check_restore(store, identity, backups)


def test_verification_fails_if_directory_cannot_sync(scope, monkeypatch):
    store, identity, backups, _ = scope
    store.prepare(identity, backups)

    def fail(_fd):
        raise OSError("directory sync failed")

    monkeypatch.setattr(cutover.os, "fsync", fail)
    with pytest.raises(OSError, match="directory sync failed"):
        check_restore(store, identity, backups)


def test_directory_replacement_before_publish(scope, monkeypatch):
    store, identity, backups, path = scope
    store.prepare(identity, backups)
    fsync = cutover.os.fsync
    moved = path.parent.with_name("moved-state")

    def swap(fd):
        fsync(fd)
        path.parent.rename(moved)
        path.parent.mkdir(mode=0o700)

    monkeypatch.setattr(cutover.os, "fsync", swap)
    with pytest.raises(StateError, match="directory changed"):
        store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
    assert not path.exists()
    assert list(moved.iterdir()) == [moved / MANIFEST]
    assert json.loads((moved / MANIFEST).read_bytes())["manifest"]["phase"] == "PREPARED"


def test_manifest_swap_during_open(scope, monkeypatch):
    store, identity, backups, path = scope
    store.prepare(identity, backups)
    real_open = cutover.os.open

    def swap(name, *args, **kwargs):
        if name == MANIFEST:
            path.rename(path.with_suffix(".old"))
            path.symlink_to(path.with_suffix(".old"))
        return real_open(name, *args, **kwargs)

    monkeypatch.setattr(cutover.os, "open", swap)
    with pytest.raises(OSError):
        check_restore(store, identity, backups)


def test_concurrent_prepare_has_one_winner(scope):
    store, identity, backups, _ = scope
    start = Barrier(2)

    def run(operation):
        start.wait(timeout=5)
        try:
            return store.prepare(replace(identity, operation_id=operation), backups)
        except (BlockingIOError, StateError):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("cutover-1", "cutover-2")))
    assert [result for result in results if result is not None] == [store.show()]


def test_restore_context_excludes_phase_changes(scope):
    store, identity, backups, _ = scope
    store.prepare(identity, backups)
    with store.verify_restore_allowed(identity, backups):
        with pytest.raises(BlockingIOError):
            store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
        with pytest.raises(BlockingIOError):
            check_restore(store, identity, backups)


def test_cli(scope):
    store, identity, backups, path = scope
    script = Path(cutover.__file__)
    root = ["--host-root", str(path.parent.parent)]
    flags = [
        part for field, value in vars(identity).items()
        for part in ("--" + field.replace("_", "-"), value)
    ]

    def invoke(command, *arguments):
        return subprocess.run([sys.executable, str(script), command, *root, *arguments],
                              capture_output=True, text=True, timeout=5)

    backup = ["--backup-root", str(backups)]
    assert invoke("prepare").returncode == 2
    assert invoke("show").returncode == 1
    assert invoke("prepare", *flags, *backup).returncode == 0
    denied = invoke("verify-restore-allowed", *flags, *backup)
    assert denied.returncode == 2
    assert "invalid choice" in denied.stderr
    result = invoke("advance", *flags, "--expected", "PREPARED", "--to", "MIGRATING")
    assert result.returncode == 0, result.stderr
    assert json.loads(invoke("show").stdout) == store.show().payload()



@pytest.mark.parametrize("fault", ["mode", "hardlink", "owner", "fifo"])
def test_unsafe_backup_refused(scope, monkeypatch, fault):
    store, identity, backups, path = scope
    store.prepare(identity, backups)
    archive = Path(identity.backup_path)
    if fault == "mode":
        archive.chmod(0o777)
    elif fault == "hardlink":
        os.link(archive, backups / "alias")
    elif fault == "fifo":
        archive.unlink()
        os.mkfifo(archive, 0o600)
    else:
        original = archive.stat()
        fstat = os.fstat

        def wrong_owner(fd):
            info = fstat(fd)
            if not os.path.samestat(info, original):
                return info
            return SimpleNamespace(st_mode=info.st_mode, st_uid=os.geteuid() + 1)

        monkeypatch.setattr(os, "fstat", wrong_owner)
    with pytest.raises(StateError, match="unsafe backup"):
        check_restore(store, identity, backups)
    assert path.exists()


@pytest.mark.parametrize("fault", ["host", "state", "backup_root", "ancestor"])
def test_unprotected_directories_refused(scope, fault):
    store, identity, backups, path = scope
    directory = {"host": path.parent.parent, "state": path.parent,
                 "backup_root": backups, "ancestor": backups.parent}[fault]
    directory.chmod(0o777)
    with pytest.raises(StateError, match="unsafe|0700"):
        store.prepare(identity, backups)


def test_backup_modified_in_place_after_hash(scope, monkeypatch):
    store, identity, backups, _ = scope
    store.prepare(identity, backups)
    fsync = os.fsync
    with open(identity.backup_path, "r+b", buffering=0) as writer:
        def mutate(fd):
            fsync(fd)
            writer.write(b"altered")

        monkeypatch.setattr(os, "fsync", mutate)
        with pytest.raises(StateError, match="backup changed"):
            with store.verify_restore_allowed(identity, backups):
                pytest.fail("consumer received a modified backup")


def test_backup_modified_during_consumption_reported(scope):
    store, identity, backups, _ = scope
    store.prepare(identity, backups)
    with pytest.raises(StateError, match="backup changed"):
        with store.verify_restore_allowed(identity, backups):
            Path(identity.backup_path).write_bytes(b"modified")


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "17"])
def test_invalid_backup_limit(scope, limit):
    _, _, _, path = scope
    with pytest.raises(StateError, match="positive integer"):
        CutoverStore(path.parent.parent, max_backup_bytes=limit)


def test_readonly_backup_is_accepted(scope):
    store, identity, backups, _ = scope
    Path(identity.backup_path).chmod(0o400)
    store.prepare(identity, backups)
    check_restore(store, identity, backups)


def test_backup_size_limit(scope, monkeypatch):
    _, identity, backups, path = scope
    archive = Path(identity.backup_path)
    store = CutoverStore(path.parent.parent, max_backup_bytes=archive.stat().st_size)
    store.prepare(identity, backups)
    check_restore(store, identity, backups)
    with archive.open("r+b") as stream:
        stream.truncate(cutover.DEFAULT_MAX_BACKUP_BYTES + 1)

    def unexpected_read(*args):
        pytest.fail("oversized backup was read")

    monkeypatch.setattr(os, "read", unexpected_read)
    with pytest.raises(StateError, match="exceeds max_backup_bytes"):
        check_restore(store, identity, backups)


@pytest.mark.parametrize("change", ["append", "truncate"])
def test_backup_size_changes_during_hash(scope, monkeypatch, change):
    store, identity, backups, path = scope
    archive = Path(identity.backup_path)
    real_read = os.read
    reads = []

    def resize(fd, size):
        reads.append(size)
        if len(reads) == 1:
            if change == "append":
                with archive.open("ab") as stream:
                    stream.write(b"extra")
            else:
                archive.write_bytes(b"x")
        return real_read(fd, size)

    monkeypatch.setattr(os, "read", resize)
    with pytest.raises(StateError, match="changed size"):
        store.prepare(identity, backups)
    assert len(reads) <= 3
    assert not path.exists()


def test_directory_replacement_during_restore(scope):
    store, identity, backups, path = scope
    store.prepare(identity, backups)
    with pytest.raises(StateError, match="directory changed"):
        with store.verify_restore_allowed(identity, backups):
            path.parent.rename(path.parent.with_name("moved-state"))
            path.parent.mkdir(mode=0o700)


def commit_command(identity, path):
    flags = [
        part for field, value in vars(identity).items()
        for part in ("--" + field.replace("_", "-"), value)
    ]
    return [sys.executable, str(Path(cutover.__file__)), "advance",
            "--host-root", str(path.parent.parent), *flags,
            "--expected", "VERIFIED_READONLY", "--to", "COMMITTED_WRITERS_ALLOWED"]


def verify_readonly(store, identity, backups):
    store.prepare(identity, backups)
    store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
    store.advance(identity, Phase.MIGRATING, Phase.VERIFIED_READONLY)


def test_other_process_cannot_commit_during_restore(scope):
    store, identity, backups, path = scope
    verify_readonly(store, identity, backups)
    command = commit_command(identity, path)
    with store.verify_restore_allowed(identity, backups) as fd:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        assert result.returncode == 1, result.stderr
        assert "temporarily unavailable" in result.stderr
        assert os.read(fd, 1024) == b"verified snapshot"
    subprocess.run(command, check=True, timeout=5)
    with pytest.raises(StateError, match="forbids"):
        check_restore(store, identity, backups)


def test_parent_unlocks_while_forked_child_is_alive(scope):
    store, identity, backups, path = scope
    verify_readonly(store, identity, backups)
    ready_r, ready_w = os.pipe()
    resume_r, resume_w = os.pipe()
    child = None
    try:
        with store.verify_restore_allowed(identity, backups):
            child = os.fork()
            if child == 0:
                status = 2
                try:
                    os.write(ready_w, b"1")
                    if select.select([resume_r], [], [], 10)[0] and os.read(resume_r, 1):
                        store.advance(identity, Phase.VERIFIED_READONLY, Phase.RECOVERY_REQUIRED)
                except StateError as exc:
                    status = 0 if "after fork" in str(exc) else 3
                finally:
                    os._exit(status)
            assert select.select([ready_r], [], [], 5)[0]
            assert os.read(ready_r, 1) == b"1"
        subprocess.run(commit_command(identity, path), check=True, timeout=5)
        os.write(resume_w, b"1")
        _, status = os.waitpid(child, 0)
        child = None
        assert os.waitstatus_to_exitcode(status) == 0
    finally:
        if child:
            os.kill(child, signal.SIGKILL)
            os.waitpid(child, 0)
        for fd in (ready_r, ready_w, resume_r, resume_w):
            os.close(fd)


def test_missing_terminal_manifest_blocks_restore(scope):
    store, identity, backups, path = scope
    verify_readonly(store, identity, backups)
    store.advance(identity, Phase.VERIFIED_READONLY, Phase.COMMITTED_WRITERS_ALLOWED)
    path.unlink()
    with pytest.raises(StateError, match="missing"):
        check_restore(store, identity, backups)


def test_valid_older_manifest_swap_before_restore_refused(scope, monkeypatch):
    store, identity, backups, path = scope
    store.prepare(identity, backups)
    old = path.read_bytes()
    store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
    fsync = os.fsync

    def replay(fd):
        fsync(fd)
        path.write_bytes(old)

    monkeypatch.setattr(os, "fsync", replay)
    with pytest.raises(StateError, match="manifest changed"):
        with store.verify_restore_allowed(identity, backups):
            pytest.fail("consumer received authorization after a manifest swap")
