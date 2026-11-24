#!/usr/bin/env python3
"""Isolated G5 PREPARED drill: real PostgreSQL 15, never a deployment adapter.

The only entrypoint refuses non-GitHub-CI execution. It always starts an
unpublished disposable Docker container without network/ports/mounts, creates
synthetic data and a private temporary host, then destroys both. It exercises
the genuine G5 activation marker, DB fence, pg_dump and durable manifest.
HTTP/Socket.IO, Docker application workers and external privileged writers
remain UNIMPLEMENTED for production; this is deliberately NOT G5 certification.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from ops.ci_g5_pg15_fence import CIOnlyAdmin, run
from ops.g5_activation_fence import MARKER
from ops.g5_cutover_prepare import BackupReceipt, G5Preparation, PreparationRequest
from ops.g5_cutover_state import CutoverStore, MANIFEST, Phase, StateError
from ops.g5_pg15_writer_fence import Pg15FenceTarget, Pg15PersistentFence, FenceError


def _postgres_ready(name: str) -> None:
    for _ in range(80):
        ready = run(["docker", "exec", name, "pg_isready", "-U", "postgres"], check=False)
        if ready.returncode == 0:
            final = run(
                ["docker", "exec", name, "psql", "-X", "-U", "postgres",
                 "-d", "postgres", "-Atqc", "SHOW listen_addresses;"], check=False
            )
            if final.returncode == 0 and final.stdout.strip() == "*":
                return
        time.sleep(0.25)
    raise RuntimeError("isolated PostgreSQL final postmaster not ready")


def _fresh_case(root: Path, database: str, role: str, admin: CIOnlyAdmin):
    host = root / ("host-" + database)
    state = host / ".ops-state"
    backup_root = root / ("backups-" + database)
    host.mkdir(mode=0o700)
    state.mkdir(mode=0o700)
    backup_root.mkdir(mode=0o700)
    admin.execute_committed(f'CREATE ROLE "{role}" LOGIN;')
    admin.execute_committed(f'CREATE DATABASE "{database}" OWNER "{role}";')
    admin._psql(
        "CREATE TABLE durable_probe (id integer PRIMARY KEY, marker text NOT NULL);"
        " INSERT INTO durable_probe VALUES (1, 'commit-before-cutover');",
        database=database,
    )
    request = PreparationRequest(
        host_root=str(host),
        backup_root=str(backup_root),
        operation_id="ci-g5-" + database,
        previous_sha="a" * 40,
        candidate_sha="b" * 40,
        compose_project="medievol_ci",
        postgres_db=database,
    )
    return request, state, backup_root


class CIOnlyPreparationPort:
    """Explicit fake admission/worker gate + **real** PostgreSQL catalog fence.

    This adapter never exists outside this non-public CI script. It cannot
    attest real edge, Socket.IO, external Docker or other privileged writers.
    """

    def __init__(self, admin: CIOnlyAdmin, container: str, request: PreparationRequest,
                 *, failure: str | None = None):
        self.admin = admin
        self.container = container
        self.request = request
        self.failure = failure
        self.calls: list[str] = []
        self.edge_closed = False
        self.workers_stopped = False
        self.fence = Pg15PersistentFence(
            Pg15FenceTarget(request.postgres_db, request.postgres_db + "_app", "postgres"),
            admin,
        )
        self.receipt = None
        self.verify_count = 0

    def _stage(self, name: str) -> None:
        # arm_cutover must publish durable evidence *before* ANY port action.
        state = Path(self.request.host_root) / ".ops-state"
        if not (state / MARKER).is_file():
            raise RuntimeError("G5 activation marker not published before port action")
        self.calls.append(name)
        if self.failure == name:
            raise RuntimeError("synthetic stage failure: " + name)

    def close_admission(self) -> None:
        self._stage("close_admission")
        self.edge_closed = True  # synthetic; no live HTTP server exists

    def fence_database_writes(self) -> None:
        self._stage("fence_database_writes")
        self.fence.engage()

    def stop_writers(self) -> None:
        self._stage("stop_writers")
        self.workers_stopped = True  # synthetic; active SQL sessions were drained

    def verify_drain(self) -> bool:
        self.verify_count += 1
        self._stage("verify_drain_" + str(self.verify_count))
        if not self.edge_closed or not self.workers_stopped:
            raise RuntimeError("synthetic admission/worker gate is not closed")
        self.fence.assert_closed()  # REAL PG15 role, limit, sessions, prepared xacts
        return True

    def capture_snapshot(self) -> BackupReceipt:
        self._stage("capture_snapshot")
        if self.receipt is not None:
            raise RuntimeError("snapshot may only be taken once")
        # pg_dump uses the explicitly isolated *administrative* identity.
        # PG15 allows the superuser to connect even when datconnlimit=0.
        result = subprocess.run(
            ["docker", "exec", self.container, "pg_dump", "-U", "postgres",
             "-d", self.request.postgres_db, "--format=custom",
             "--no-owner", "--no-privileges"],
            capture_output=True, timeout=30, check=False,
        )
        if result.returncode != 0 or not result.stdout:
            raise RuntimeError("isolated PostgreSQL dump failed")
        archive = Path(self.request.backup_root) / "cutover.dump"
        fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
            payload = result.stdout
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise RuntimeError("snapshot short write")
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        directory = os.open(self.request.backup_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        self.receipt = BackupReceipt(str(archive), hashlib.sha256(payload).hexdigest())
        return self.receipt


def _wait_for_writer(admin: CIOnlyAdmin, container: str, role: str, database: str) -> None:
    run([
        "docker", "exec", "-d", container, "psql", "-X", "-U", role,
        "-d", database, "-Atqc", "SELECT pg_sleep(90);",
    ])
    for _ in range(40):
        active = admin.query_fresh(
            "SELECT count(*) FROM pg_stat_activity "
            f"WHERE datname='{database}' AND usename='{role}';"
        )
        if active == "1":
            return
        time.sleep(0.25)
    raise RuntimeError("synthetic writer session did not become active")


def _assert_reconnect_denied(container: str, role: str, database: str) -> None:
    after = run(
        ["docker", "exec", container, "psql", "-X", "-U", role, "-d", database,
         "-Atqc", "INSERT INTO durable_probe VALUES (2, 'unexpected-after');"],
        check=False,
    )
    if after.returncode == 0:
        raise RuntimeError("confirmed post-fence INSERT was unexpectedly admitted")


def _prove_snapshot(admin: CIOnlyAdmin, container: str, port: CIOnlyPreparationPort):
    if port.receipt is None:
        raise RuntimeError("no snapshot receipt after successful prepare")
    admin.execute_committed("CREATE DATABASE isolated_restore_probe;")
    archive = Path(port.receipt.path).read_bytes()
    restored = subprocess.run(
        ["docker", "exec", "-i", container, "pg_restore",
         "--no-owner", "--no-privileges", "--exit-on-error",
         "-U", "postgres", "-d", "isolated_restore_probe"],
        input=archive, capture_output=True, timeout=30, check=False,
    )
    if restored.returncode != 0:
        raise RuntimeError("isolated snapshot failed to restore")
    value = admin._psql(
        "SELECT marker FROM durable_probe WHERE id=1;", database="isolated_restore_probe"
    ).stdout.strip()
    if value != "commit-before-cutover":
        raise RuntimeError("confirmed pre-fence transaction missing from restored snapshot")


def _run_cases(container: str, admin: CIOnlyAdmin, root: Path) -> None:
    # First case: an actual PostgreSQL session is active when cutover begins.
    request, state, backup_root = _fresh_case(root, "game_success", "game_success_app", admin)
    _wait_for_writer(admin, container, "game_success_app", "game_success")
    port = CIOnlyPreparationPort(admin, container, request)
    manifest = G5Preparation().prepare(request, port)
    if manifest.phase is not Phase.PREPARED or CutoverStore(request.host_root).show() != manifest:
        raise RuntimeError("successful G5 preparation did not persist PREPARED")
    if port.calls != [
        "close_admission", "fence_database_writes", "stop_writers",
        "verify_drain_1", "capture_snapshot", "verify_drain_2",
    ]:
        raise RuntimeError("cutover operations were ordered incorrectly")
    if not (state / MARKER).is_file() or not (state / MANIFEST).is_file():
        raise RuntimeError("G5 lockout or manifest missing after successful preparation")
    _assert_reconnect_denied(container, "game_success_app", "game_success")
    _prove_snapshot(admin, container, port)

    # Second case: failure *after* the database fence must NOT reopen writers
    # or publish a successful PREPARED manifest.
    request, state, backup_root = _fresh_case(root, "game_failure", "game_failure_app", admin)
    port = CIOnlyPreparationPort(admin, container, request, failure="capture_snapshot")
    try:
        G5Preparation().prepare(request, port)
    except RuntimeError as exc:
        if "synthetic stage failure" not in str(exc):
            raise
    else:
        raise RuntimeError("injected backup failure unexpectedly committed")
    if not (state / MARKER).is_file() or (state / MANIFEST).exists():
        raise RuntimeError("failed G5 preparation reopened legacy or published manifest")
    port.fence.assert_closed()
    _assert_reconnect_denied(container, "game_failure_app", "game_failure")
    try:
        G5Preparation().prepare(request, CIOnlyPreparationPort(admin, container, request))
    except StateError:
        pass
    else:
        raise RuntimeError("failed G5 preparation permitted unsafe retry")


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
        print("G5 PG15 PREPARED drill is CI-only; no production executor", file=sys.stderr)
        return 2
    name = f"bm-g5-prepared-{os.getpid()}-{uuid4().hex[:8]}"
    started = False
    try:
        run([
            "docker", "run", "--rm", "-d", "--network", "none", "--name", name,
            "-e", "POSTGRES_PASSWORD=synthetic-ci-only-not-a-secret",
            "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:15-alpine",
        ], timeout=90)
        started = True
        _postgres_ready(name)
        admin = CIOnlyAdmin(name)
        with tempfile.TemporaryDirectory(prefix="bm-g5-prepared-") as temp:
            _run_cases(name, admin, Path(temp))
        print("G5 integrated PREPARED rehearsal passed (PG15 isolated; not G5 approval)")
        return 0
    finally:
        if started:
            run(["docker", "rm", "-f", name], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
