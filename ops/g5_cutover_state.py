"""Durable host-local cutover manifest for a manager that owns the write barrier."""

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import Enum
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import uuid


STATE_DIR = ".ops-state"
MANIFEST = "g5-cutover.json"
MAX_MANIFEST = 16384
DEFAULT_MAX_BACKUP_BYTES = 1 << 40
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
READ_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


class StateError(ValueError):
    """The requested operation cannot safely proceed."""


class Phase(str, Enum):
    PREPARED = "PREPARED"
    MIGRATING = "MIGRATING"
    VERIFIED_READONLY = "VERIFIED_READONLY"
    COMMITTED_WRITERS_ALLOWED = "COMMITTED_WRITERS_ALLOWED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


RESTORE_PHASES = frozenset((Phase.PREPARED, Phase.MIGRATING, Phase.VERIFIED_READONLY))
NEXT = {
    Phase.PREPARED: Phase.MIGRATING,
    Phase.MIGRATING: Phase.VERIFIED_READONLY,
    Phase.VERIFIED_READONLY: Phase.COMMITTED_WRITERS_ALLOWED,
}


def _absolute(path):
    path = os.fspath(path)
    if (not isinstance(path, str) or not path.startswith("/") or
            (path != "/" and any(part in ("", ".", "..") for part in path[1:].split("/"))) or
            any(ord(char) < 32 or ord(char) == 127 for char in path)):
        raise StateError("expected a canonical absolute path")
    return path


@dataclass(frozen=True)
class Identity:
    operation_id: str
    previous_sha: str
    candidate_sha: str
    backup_sha256: str
    backup_path: str
    compose_project: str
    postgres_db: str

    def __post_init__(self):
        for field, pattern in (
            ("operation_id", r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}"),
            ("previous_sha", r"[0-9a-f]{40}"),
            ("candidate_sha", r"[0-9a-f]{40}"),
            ("backup_sha256", r"[0-9a-f]{64}"),
            ("compose_project", r"[a-z0-9][a-z0-9_-]{0,127}"),
            ("postgres_db", r"[A-Za-z_][A-Za-z0-9_-]{0,62}"),
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not re.fullmatch(pattern, value):
                raise StateError(f"invalid {field}")
        if self.previous_sha == self.candidate_sha:
            raise StateError("release SHAs must differ")
        if not isinstance(self.backup_path, str) or _absolute(self.backup_path) == "/":
            raise StateError("invalid backup_path")


@dataclass(frozen=True)
class Manifest:
    identity: Identity
    phase: Phase

    def payload(self):
        return {"version": 1, "identity": asdict(self.identity), "phase": self.phase.value}


@contextmanager
def _open(path, flags, mode=0o600, *, dir_fd=None):
    fd = os.open(path, flags, mode, dir_fd=dir_fd)
    try:
        yield fd
    finally:
        os.close(fd)


def _directory_identity(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid


def _check_ancestor(info):
    if (info.st_uid not in (0, os.geteuid()) or
            (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)):
        raise StateError("unsafe directory ancestor")


@contextmanager
def _directory(path, *, private_root=None):
    """Walk from / without following symlinks, pinning each parent for openat."""
    path = _absolute(path)
    fd = os.open("/", DIRECTORY)
    try:
        _check_ancestor(os.fstat(fd))
        current = "/"
        for part in path[1:].split("/") if path != "/" else ():
            child = os.open(part, DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
            current = os.path.join(current, part)
            info = os.fstat(fd)
            _check_ancestor(info)
            if private_root and os.path.commonpath((current, private_root)) == private_root:
                if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                    raise StateError("unsafe directory inside backup root")
                if current == private_root and stat.S_IMODE(info.st_mode) != 0o700:
                    raise StateError("backup root must have mode 0700")
        yield fd
    finally:
        os.close(fd)


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _entry_stamp(directory, name):
    try:
        return _stamp(os.stat(name, dir_fd=directory, follow_symlinks=False))
    except FileNotFoundError:
        return None


def _unique_object(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise StateError("duplicate JSON key")
    return obj


def _encode(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class CutoverStore:
    """One manifest per host release root. The manager acquires its lock first."""

    def __init__(self, host_root, *, max_backup_bytes=DEFAULT_MAX_BACKUP_BYTES):
        if type(max_backup_bytes) is not int or max_backup_bytes <= 0:
            raise StateError("max_backup_bytes must be a positive integer")
        self.host_root = _absolute(host_root)
        self.max_backup_bytes = max_backup_bytes
        self._pid = os.getpid()

    @contextmanager
    def _state_directory(self):
        with _directory(self.host_root) as host:
            info = os.fstat(host)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise StateError("unsafe host root owner or mode")
            with _open(STATE_DIR, DIRECTORY, dir_fd=host) as directory:
                info = os.fstat(directory)
                if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise StateError(".ops-state must be owned by the caller with mode 0700")
                yield directory

    def _check_process(self):
        if os.getpid() != self._pid:
            raise StateError("cutover store cannot be used after fork")

    @contextmanager
    def _locked(self, *, shared=False):
        self._check_process()
        with self._state_directory() as directory:
            original = _directory_identity(os.fstat(directory))
            mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
            fcntl.flock(directory, mode | fcntl.LOCK_NB)
            try:
                self._check_directory(directory, original)
                yield directory
                self._check_directory(directory, original)
            finally:
                if os.getpid() == self._pid:
                    fcntl.flock(directory, fcntl.LOCK_UN)

    def _check_directory(self, directory, original=None):
        self._check_process()
        pinned = _directory_identity(os.fstat(directory))
        with self._state_directory() as current:
            if (pinned != _directory_identity(os.fstat(current)) or
                    (original is not None and pinned != original)):
                raise StateError("state directory changed")

    def _load(self, directory):
        stamp = _entry_stamp(directory, MANIFEST)
        if stamp is None:
            return None, None
        with _open(MANIFEST, READ_FILE, dir_fd=directory) as fd:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or
                    info.st_uid != os.geteuid() or info.st_nlink != 1 or
                    not 0 < info.st_size <= MAX_MANIFEST or _stamp(info) != stamp):
                raise StateError("unsafe cutover manifest")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_MANIFEST + 1)
            if len(raw) != info.st_size or _stamp(os.fstat(fd)) != stamp:
                raise StateError("cutover manifest changed during read")
        self._check_entry(directory, stamp)
        try:
            envelope = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
            if not isinstance(envelope, dict) or set(envelope) != {"manifest", "sha256"}:
                raise StateError("invalid cutover envelope")
            payload = envelope["manifest"]
            if envelope["sha256"] != hashlib.sha256(_encode(payload)).hexdigest():
                raise StateError("cutover manifest checksum mismatch")
            if (not isinstance(payload, dict) or set(payload) != {"version", "identity", "phase"} or
                    type(payload["version"]) is not int or payload["version"] != 1):
                raise StateError("unsupported cutover manifest schema")
            return Manifest(Identity(**payload["identity"]), Phase(payload["phase"])), stamp
        except (ValueError, TypeError, RecursionError) as exc:
            raise StateError("invalid cutover manifest") from exc

    def _check_entry(self, directory, stamp):
        self._check_directory(directory)
        if _entry_stamp(directory, MANIFEST) != stamp:
            raise StateError("cutover manifest changed")

    def _publish(self, directory, manifest, previous_stamp):
        payload = manifest.payload()
        checksum = hashlib.sha256(_encode(payload)).hexdigest()
        raw = _encode({"manifest": payload, "sha256": checksum}) + b"\n"
        if len(raw) > MAX_MANIFEST:
            raise StateError("cutover manifest is too large")
        temp = f".g5-cutover-{uuid.uuid4().hex}.tmp"
        with _open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                   dir_fd=directory) as fd:
            published = False
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(fd)
                self._check_entry(directory, previous_stamp)
                if _entry_stamp(directory, temp) != _stamp(os.fstat(fd)):
                    raise StateError("temporary manifest changed")
                os.replace(temp, MANIFEST, src_dir_fd=directory, dst_dir_fd=directory)
                published = True
                os.fsync(directory)
                self._check_entry(directory, _stamp(os.fstat(fd)))
            finally:
                if not published and _entry_stamp(directory, temp) == _stamp(os.fstat(fd)):
                    os.unlink(temp, dir_fd=directory)

    def _matching(self, directory, identity):
        manifest, stamp = self._load(directory)
        if manifest is None:
            raise StateError("cutover manifest is missing")
        if manifest.identity != identity:
            raise StateError("cutover identity mismatch")
        return manifest, stamp

    @contextmanager
    def _backup(self, identity, backup_root):
        root = _absolute(backup_root)
        path = identity.backup_path
        if root == "/" or os.path.commonpath((path, root)) != root or path == root:
            raise StateError("backup must be inside the configured backup root")
        parent, name = os.path.split(path)
        with (_directory(parent, private_root=root) as directory,
              _open(name, READ_FILE, dir_fd=directory) as fd):
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                    info.st_nlink != 1 or stat.S_IMODE(info.st_mode) not in (0o400, 0o600) or
                    info.st_size <= 0):
                raise StateError("unsafe backup type, owner, mode, link count or size")
            if info.st_size > self.max_backup_bytes:
                raise StateError("backup exceeds max_backup_bytes")
            stamp = _stamp(info)

            def check_backup():
                self._check_process()
                with _directory(parent, private_root=root) as current:
                    if (not os.path.samestat(os.fstat(directory), os.fstat(current)) or
                            _entry_stamp(current, name) != stamp or _stamp(os.fstat(fd)) != stamp):
                        raise StateError("backup changed during verification or consumption")

            digest = hashlib.sha256()
            remaining = info.st_size
            while remaining:
                block = os.read(fd, min(remaining, 1024 * 1024))
                if not block:
                    raise StateError("backup changed size during verification")
                digest.update(block)
                remaining -= len(block)
            if os.read(fd, 1):
                raise StateError("backup changed size during verification")
            if digest.hexdigest() != identity.backup_sha256:
                raise StateError("backup checksum mismatch")
            os.lseek(fd, 0, os.SEEK_SET)
            check_backup()
            yield fd, check_backup
            check_backup()

    def prepare(self, identity, backup_root):
        """Record a new operation after the manager confirms the closed barrier."""
        with self._locked() as directory:
            existing, _ = self._load(directory)
            if existing is not None:
                raise StateError("cutover slot is already occupied")
            with self._backup(identity, backup_root):
                manifest = Manifest(identity, Phase.PREPARED)
                self._publish(directory, manifest, None)
            return manifest

    def advance(self, identity, expected, target):
        """Compare and advance after the manager verifies the target prerequisites."""
        expected, target = Phase(expected), Phase(target)
        with self._locked() as directory:
            manifest, stamp = self._matching(directory, identity)
            if manifest.phase != expected:
                raise StateError("unexpected current cutover phase")
            if not (NEXT.get(expected) == target or
                    (expected in RESTORE_PHASES and target == Phase.RECOVERY_REQUIRED)):
                raise StateError("cutover transition is forbidden")
            updated = Manifest(identity, target)
            self._publish(directory, updated, stamp)
            return updated

    @contextmanager
    def verify_restore_allowed(self, identity, backup_root, *, expected_phase=None):
        """Yield a verified FD under the lock, optionally requiring an exact phase.

        The lifecycle always supplies its expected phase. Older read-only
        verification callers may inspect any restore-eligible phase.
        """
        if expected_phase is not None and not isinstance(expected_phase, Phase):
            raise StateError("invalid expected restore phase")
        with self._locked() as directory:
            manifest, stamp = self._matching(directory, identity)
            if manifest.phase not in RESTORE_PHASES:
                raise StateError("cutover phase forbids snapshot restore")
            if expected_phase is not None and manifest.phase is not expected_phase:
                raise StateError("unexpected exact restore phase")
            with self._backup(identity, backup_root) as (backup_fd, check_backup):
                os.fsync(directory)
                self._check_entry(directory, stamp)
                check_backup()
                yield backup_fd
                self._check_entry(directory, stamp)

    def show(self):
        with self._locked(shared=True) as directory:
            manifest, _ = self._load(directory)
            if manifest is None:
                raise StateError("cutover manifest is missing")
            return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "advance", "show"):
        sub = commands.add_parser(command)
        sub.add_argument("--host-root", required=True)
        if command != "show":
            for field in Identity.__dataclass_fields__:
                sub.add_argument("--" + field.replace("_", "-"), required=True)
        if command == "prepare":
            sub.add_argument("--backup-root", required=True)
        if command == "advance":
            sub.add_argument("--expected", choices=[phase.value for phase in Phase], required=True)
            sub.add_argument("--to", choices=[phase.value for phase in Phase], required=True)
    args = parser.parse_args(argv)

    try:
        store = CutoverStore(args.host_root)
        if args.command == "show":
            print(json.dumps(store.show().payload(), sort_keys=True))
            return 0
        identity = Identity(**{field: getattr(args, field) for field in Identity.__dataclass_fields__})
        if args.command == "prepare":
            store.prepare(identity, args.backup_root)
        else:
            store.advance(identity, args.expected, args.to)
    except (OSError, StateError) as exc:
        print(f"cutover state refused ({exc})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
