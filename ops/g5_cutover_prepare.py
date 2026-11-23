"""G5 protected *preparation* sequence (BM-0093 / #174).

No command-line entrypoint and no live adapter are provided. This is not a
deployment, PostgreSQL write barrier, or permission to restore an archive.
A future audited adapter must implement the durable external protections.
The sequence intentionally never migrates, restores, publishes a release, or
reopens writers. On *every* failure, arm_cutover's durable legacy lockout stays.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from ops.g5_activation_fence import arm_cutover
from ops.g5_cutover_state import (
    CutoverStore,
    Identity,
    Manifest,
    Phase,
    StateError,
    _absolute,
)


_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_SHA = re.compile(r"[0-9a-f]{40}")
_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}")
_DATABASE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")
_HASH = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class PreparationRequest:
    host_root: str
    backup_root: str
    operation_id: str
    previous_sha: str
    candidate_sha: str
    compose_project: str
    postgres_db: str

    def __post_init__(self) -> None:
        # Fail *before* creating an irreversible activation marker on a bad
        # request. CutoverStore independently checks the archive and paths.
        for path in (self.host_root, self.backup_root):
            if not isinstance(path, str):
                raise StateError("G5 root must be a canonical absolute string")
            _absolute(path)
        if self.backup_root == "/":
            raise StateError("G5 backup root cannot be /")
        for value, pattern, name in (
            (self.operation_id, _OPERATION, "operation ID"),
            (self.previous_sha, _SHA, "previous SHA"),
            (self.candidate_sha, _SHA, "candidate SHA"),
            (self.compose_project, _PROJECT, "Compose project"),
            (self.postgres_db, _DATABASE, "PostgreSQL database"),
        ):
            if not isinstance(value, str) or not pattern.fullmatch(value):
                raise StateError(f"invalid {name}")
        if self.previous_sha == self.candidate_sha:
            raise StateError("G5 release SHAs must differ")


@dataclass(frozen=True)
class BackupReceipt:
    """Immutable archive identity to be verified by CutoverStore from disk."""

    path: str
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or _absolute(self.path) == "/":
            raise StateError("invalid G5 snapshot path")
        if not isinstance(self.sha256, str) or not _HASH.fullmatch(self.sha256):
            raise StateError("invalid G5 snapshot checksum")


class PreparationPort(Protocol):
    """Contract for a *future* certified, persistent, external writer barrier.

    All operations must be synchronous and fail closed. close_admission must
    reject new HTTP and Socket.IO requests; fence_database_writes must prevent
    even reconnects and remain in effect after process crash; stop_writers must
    disable Docker restarts, active workers, schedulers and migrations.
    verify_drain must attest to all of those AND zero live/prepared SQL writers.
    A successful point-in-time g5_writer_drain_probe is NOT sufficient.
    """

    def close_admission(self) -> None: ...
    def fence_database_writes(self) -> None: ...
    def stop_writers(self) -> None: ...
    def verify_drain(self) -> bool: ...
    def capture_snapshot(self) -> BackupReceipt: ...


class G5Preparation:
    """Compose durable legacy exclusion, a writer barrier, and backup metadata.

    All writing operations are supplied by the port; the package includes NO
    production adapter or CLI. Success means phase PREPARED only. The permanent
    activation marker remains, so legacy deploy and rollback stay disabled.
    """

    def prepare(self, request: PreparationRequest, port: PreparationPort) -> Manifest:
        if not isinstance(request, PreparationRequest):
            raise StateError("invalid G5 preparation request")
        store = CutoverStore(request.host_root)
        with arm_cutover(request.host_root, request.operation_id):
            # The legacy deploy lock and persistent marker are active BEFORE
            # the edge, role, Docker, or snapshot operation is attempted.
            port.close_admission()
            port.fence_database_writes()
            port.stop_writers()

            # Only a certified durable barrier can make a point-in-time
            # observation meaningful. Exact bool True, not a truthy object,
            # avoids interpreting a list of blockers as a successful probe.
            if port.verify_drain() is not True:
                raise StateError("G5 durable writer barrier was not certified")
            receipt = port.capture_snapshot()
            if type(receipt) is not BackupReceipt:
                raise StateError("G5 backup did not provide a verified receipt")
            if port.verify_drain() is not True:
                raise StateError("G5 writer barrier changed during backup")

            identity = Identity(
                operation_id=request.operation_id,
                previous_sha=request.previous_sha,
                candidate_sha=request.candidate_sha,
                backup_sha256=receipt.sha256,
                backup_path=receipt.path,
                compose_project=request.compose_project,
                postgres_db=request.postgres_db,
            )
            # This checks the actual disk archive (identity, inode, hash,
            # path, ownership and size) and writes a durable PREPARED manifest.
            # No subsequent step is allowed to reopen application writers.
            manifest = store.prepare(identity, request.backup_root)
            if manifest.phase is not Phase.PREPARED:
                raise StateError("G5 preparation did not persist PREPARED")
            return manifest
