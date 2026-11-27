"""Read-only, non-authorizing G5 incident evidence for manual reconciliation.

No CLI, SQL, Docker, archive restore, marker cleanup or recovery execution.
An observed manifest phase is not proof of external barrier continuity.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import fcntl
import os
import re

from ops.g5_activation_fence import DEPLOY_LOCK, MARKER, _check_lock, _check_marker
from ops.g5_cutover_state import CutoverStore, Phase, StateError, READ_FILE, _directory_identity


class Disposition(str, Enum):
    PREPARATION_UNCERTAIN = "PREPARATION_UNCERTAIN"
    PRECOMMIT_RECONCILIATION = "PRECOMMIT_RECONCILIATION"
    INCIDENT_RECONCILIATION = "INCIDENT_RECONCILIATION"
    POSTCOMMIT_RECONCILIATION = "POSTCOMMIT_RECONCILIATION"


@dataclass(frozen=True)
class IncidentEvidence:
    operation_id: str
    observed_phase: Phase | None
    disposition: Disposition


_MARKER_FORMAT = re.compile(rb"version=1\noperation_id=([A-Za-z0-9][A-Za-z0-9_-]{0,127})\n")


def _marker(directory):
    fd = os.open(MARKER, READ_FILE | os.O_CLOEXEC, dir_fd=directory)
    try:
        info = os.fstat(fd)
        _check_marker(directory, info)
        if not 0 < info.st_size <= 160:
            raise StateError("invalid activation marker size")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(161)
        _check_marker(directory, info)
        match = _MARKER_FORMAT.fullmatch(raw)
        if len(raw) != info.st_size or match is None:
            raise StateError("invalid activation marker content")
        return match.group(1).decode("ascii"), info
    finally:
        os.close(fd)


def _assert_no_ambiguous_artifacts(directory):
    # A killed publication may leave a temporary manifest, and a legacy
    # incident may leave orphaned receipts. Preserve them for human review.
    if any(name == "recovery-required" or name.startswith("recovery-required.")
           or (name.startswith(".g5-cutover-") and name.endswith(".tmp"))
           for name in os.listdir(directory)):
        raise StateError("ambiguous recovery artifacts require manual reconciliation")


def inspect_incident(host_root: str) -> IncidentEvidence:
    """Observe one coherent idle G5 incident; never authorize a next action.

    Requires an existing safe deploy.lock and a valid activation marker.
    No files are created, removed or written. Missing evidence, active
    coordinator, mismatched operation ID and ambiguous artifacts all fail.
    The shared locks exclude cooperating writers only while observing.
    """
    store = CutoverStore(host_root)
    with store._state_directory() as outer:
        original = _directory_identity(os.fstat(outer))
        fd = os.open(DEPLOY_LOCK, READ_FILE | os.O_CLOEXEC, dir_fd=outer)
        try:
            _check_lock(outer, fd)
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                raise StateError("deployment lease is active; inspection refused") from None
            _check_lock(outer, fd)
            with store._locked(shared=True) as directory:
                store._check_directory(directory, original)
                _assert_no_ambiguous_artifacts(directory)
                operation, marker_info = _marker(directory)
                manifest, stamp = store._load(directory)
                if manifest is None:
                    disposition = Disposition.PREPARATION_UNCERTAIN
                    phase = None
                else:
                    if manifest.identity.operation_id != operation:
                        raise StateError("activation and manifest operation IDs differ")
                    phase = manifest.phase
                    if phase is Phase.COMMITTED_WRITERS_ALLOWED:
                        disposition = Disposition.POSTCOMMIT_RECONCILIATION
                    elif phase is Phase.RECOVERY_REQUIRED:
                        disposition = Disposition.INCIDENT_RECONCILIATION
                    else:
                        disposition = Disposition.PRECOMMIT_RECONCILIATION
                _assert_no_ambiguous_artifacts(directory)
                _check_marker(directory, marker_info)
                store._check_entry(directory, stamp)
                _check_lock(outer, fd)
                return IncidentEvidence(operation, phase, disposition)
        finally:
            # Closing our independent read-only descriptor releases its flock.
            os.close(fd)
