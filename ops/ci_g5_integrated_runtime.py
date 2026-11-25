"""CI-only combined G5 preparation using real Nginx, Docker and PostgreSQL.

No public ports, real data, credentials or production execution path. The
HTTP/WebSocket server is synthetic; the worker performs real SQL transactions.
The runner owns this disposable project and its only privileged SQL executor.
This exercises PREPARED and fail-closed drift, not a production RPO guarantee.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from ops.ci_g5_edge_admission import (
    CLIENT, SERVER, cleanup_fixture, docker_command, docker_env, expect_line, probe, run,
)
from ops.g5_activation_fence import MARKER
from ops.g5_cutover_prepare import BackupReceipt, G5Preparation, PreparationRequest
from ops.g5_cutover_state import CutoverStore, MANIFEST, Phase, StateError
from ops.g5_docker_writer_fence import DockerFenceError, DockerWriterFence
from ops.g5_edge_admission import EdgeAdmission
from ops.g5_pg15_writer_fence import Pg15FenceTarget, Pg15PersistentFence


DB = "game_ci"
APP = "game_app"
APP_PASSWORD = "synthetic-app-ci-only"
ROWS = "1|committed-before\n2|worker-committed"


class IsolatedAdmin:
    def __init__(self, container):
        self.container = container

    def sql(self, sql, database="postgres"):
        return run(["exec", self.container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                    "-U", "postgres", "-d", database, "-Atqc", sql]).strip()

    def query_fresh(self, sql):
        return self.sql(sql)

    def execute_committed(self, sql):
        self.sql(sql)


def app_command(database, sql):
    return ["exec", "-e", "PGPASSWORD=" + APP_PASSWORD, database,
            "psql", "-X", "-w", "-v", "ON_ERROR_STOP=1",
            "-h", "127.0.0.1", "-U", APP, "-d", DB, "-Atqc", sql]


def binary(args, *, input=None):
    result = subprocess.run(docker_command(args), env=docker_env(), input=input,
                            capture_output=True, timeout=45, check=False)
    if result.returncode != 0:
        raise RuntimeError("isolated binary Docker command failed")
    return result.stdout


class RuntimePreparationPort:
    """Concrete CI adapter using all three actual fences, no simulated flags."""

    def __init__(self, request, database, nginx, backend, admin, client, *, drift):
        self.request = request
        self.database = database
        self.backend = backend
        self.admin = admin
        self.client = client
        self.drift = drift
        self.edge = EdgeAdmission(request.host_root, request.compose_project, nginx, run, probe)
        self.sql = Pg15PersistentFence(Pg15FenceTarget(DB, APP, "postgres"), admin)
        self.docker = DockerWriterFence(request.compose_project, run)
        self.receipt = None
        self.snapshot_taken = False

    def _activated(self):
        state = Path(self.request.host_root) / ".ops-state"
        if not (state / MARKER).is_file() or (state / MANIFEST).exists():
            raise RuntimeError("activation must precede all port actions and PREPARED")

    def close_admission(self):
        self._activated()
        self.edge.close()
        # Prove old upgraded connection still works even with new requests denied.
        self.client.stdin.write("ping\n")
        self.client.stdin.flush()
        expect_line(self.client, "PONG")

    def fence_database_writes(self):
        self._activated()
        self.sql.engage()

    def stop_writers(self):
        self._activated()
        self.docker.engage()
        self.client.stdin.write("closed\n")
        self.client.stdin.flush()
        expect_line(self.client, "DISCONNECTED")
        if self.client.wait(timeout=10) != 0:
            raise RuntimeError("pre-existing WebSocket client failed")

    def assert_barriers(self):
        self.edge.assert_closed()
        self.docker.assert_closed()
        self.sql.assert_closed()
        code, _, stderr = probe(app_command(
            self.database, "INSERT INTO durable_probe VALUES (4,'forbidden');"
        ))
        # Reject only an actual PostgreSQL login/connection-limit refusal,
        # not an arbitrary Docker failure or missing INSERT permission.
        if code == 0 or not re.search(
            r'FATAL:.*(?:not permitted to log in|too many connections for database)', stderr
        ):
            raise RuntimeError("confirmed app role was not explicitly refused by PostgreSQL")
        self.sql.assert_closed()

    def verify_drain(self):
        self._activated()
        self.assert_barriers()
        return True

    def capture_snapshot(self):
        self._activated()
        if self.receipt is not None:
            raise RuntimeError("duplicate snapshot attempt")
        archive = Path(self.request.backup_root) / "cutover.dump"
        payload = binary(["exec", self.database, "pg_dump", "-U", "postgres", "-d", DB,
                          "--format=custom"])
        if not payload.startswith(b"PGDMP"):
            raise RuntimeError("isolated pg_dump returned no custom archive")
        fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(self.request.backup_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self.receipt = BackupReceipt(str(archive), hashlib.sha256(payload).hexdigest())
        self.snapshot_taken = True
        if self.drift:
            # Deliberate administrator interference after a real dump. The
            # coordinator MUST reject PREPARED in its second drain check.
            run(["start", self.backend])
        return self.receipt


def wait_until(predicate, failure):
    for _ in range(60):
        if predicate():
            return
        time.sleep(0.25)
    raise RuntimeError(failure)


def ready_db(database):
    code, _, _ = probe(["exec", database, "pg_isready", "-U", "postgres"])
    if code:
        return False
    code, output, _ = probe(["exec", database, "psql", "-X", "-U", "postgres",
                             "-d", "postgres", "-Atqc", "SHOW listen_addresses;"])
    return code == 0 and output.strip() == "*"


def run_case(*, drift):
    project = "bm-g5-edge-" + uuid4().hex
    label = "medievol.g5.edge-fixture=" + project
    client = None
    with tempfile.TemporaryDirectory(prefix="bm-g5-integrated-") as temp:
        root = Path(temp).resolve()
        host = root / "host"
        backup = root / "backups"
        host.mkdir(mode=0o700)
        backup.mkdir(mode=0o700)
        state = host / ".ops-state"
        state.mkdir(mode=0o700)
        edge = state / "edge-maintenance"
        edge.mkdir(mode=0o755)
        edge.chmod(0o755)
        (edge / "open").mkdir(mode=0o755)
        conf = host / "nginx.g5.conf"
        shutil.copyfile(Path(__file__).resolve().parents[1] / "nginx.g5.conf", conf)
        conf.chmod(0o644)

        def start(service, args, *, restart="always"):
            return run([
                "run", "-d", "--init", "--network", project, "--network-alias", service,
                "--restart", restart, "--label", label,
                "--label", "com.docker.compose.project=" + project,
                "--label", "com.docker.compose.service=" + service, *args,
            ]).strip()

        try:
            run(["network", "create", "--internal", "--label", label, project])
            database = start("database", [
                "-e", "POSTGRES_PASSWORD=synthetic-admin-ci-only",
                "postgres:15-alpine",
            ])
            wait_until(lambda: ready_db(database), "PostgreSQL final server did not start")
            admin = IsolatedAdmin(database)
            admin.sql(f"CREATE ROLE {APP} LOGIN PASSWORD '{APP_PASSWORD}';")
            admin.sql(f"CREATE DATABASE {DB};")
            admin.sql("CREATE TABLE durable_probe (id int PRIMARY KEY, marker text NOT NULL);"
                      f" GRANT SELECT, INSERT ON durable_probe TO {APP};"
                      " INSERT INTO durable_probe VALUES (1,'committed-before');", DB)
            # Positive control of the exact post-fence SQL path.
            run(app_command(database, "INSERT INTO durable_probe VALUES (2,'worker-committed');"))
            backend = start("backend", ["python:3.11-alpine", "python", "-u", "-c", SERVER])
            start("backend", ["python:3.11-alpine", "python", "-u", "-c", SERVER])
            frontend = start("frontend", ["python:3.11-alpine", "python", "-m", "http.server", "80"])
            # A real SQL transaction, in a project-scoped worker process,
            # has inserted an uncommitted row and will be terminated by SQL fence.
            start("worker", [
                "-e", "PGPASSWORD=" + APP_PASSWORD, "--entrypoint", "/bin/sh",
                "postgres:15-alpine", "-c",
                "psql -X -w -v ON_ERROR_STOP=1 -h database -U game_app -d game_ci "
                "-c \"BEGIN; INSERT INTO durable_probe VALUES (3,'uncommitted'); "
                "SELECT pg_sleep(300); COMMIT;\" || true; exec sleep 300",
            ])
            start("migrate", ["python:3.11-alpine", "sleep", "300"])
            seed = start("seed", ["python:3.11-alpine", "sleep", "300"], restart="no")
            run(["stop", "--time", "1", seed])
            wait_until(
                lambda: admin.query_fresh(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname='game_ci' "
                    "AND usename='game_app' AND wait_event='PgSleep' AND xact_start IS NOT NULL;"
                ) == "1",
                "worker never entered its real uncommitted transaction",
            )
            if admin.sql("SELECT id, marker FROM durable_probe ORDER BY id;", DB) != ROWS:
                raise RuntimeError("pre-fence commit evidence did not match")
            nginx = start("nginx", [
                "--mount", f"type=bind,source={conf},target=/etc/nginx/nginx.conf,readonly",
                "--mount", f"type=bind,source={edge},target=/etc/nginx/edge-maintenance,readonly",
                "nginx:1.28-alpine",
            ])
            wait_until(
                lambda: probe(["exec", nginx, "wget", "-q", "-O", "/dev/null", "-T", "2",
                               "http://127.0.0.1/api/health"])[0] == 0,
                "Nginx did not admit an initial API request",
            )
            client = subprocess.Popen(
                docker_command(["exec", "-i", frontend, "python", "-u", "-c", CLIENT]),
                env=docker_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            expect_line(client, "READY")
            request = PreparationRequest(
                str(host), str(backup), "ci-" + uuid4().hex, "a" * 40, "b" * 40, project, DB,
            )
            port = RuntimePreparationPort(request, database, nginx, backend, admin, client, drift=drift)
            if drift:
                try:
                    G5Preparation().prepare(request, port)
                except DockerFenceError:
                    if not port.snapshot_taken:
                        raise RuntimeError("drift injection did not reach real pg_dump")
                else:
                    raise RuntimeError("post-snapshot writer drift incorrectly published PREPARED")
                if not (state / MARKER).is_file() or (state / MANIFEST).exists():
                    raise RuntimeError("failed preparation lost activation or published manifest")
                port.edge.assert_closed()
                port.sql.assert_closed()
                # Never undo restrictions or permit a second prepare over the incident.
                try:
                    G5Preparation().prepare(request, port)
                except StateError:
                    pass
                else:
                    raise RuntimeError("unsafe retry was accepted")
            else:
                manifest = G5Preparation().prepare(request, port)
                store = CutoverStore(request.host_root)
                if manifest.phase is not Phase.PREPARED or store.show() != manifest:
                    raise RuntimeError("combined runtime preparation did not persist PREPARED")
                port.assert_barriers()
                # Restore from the verified open FD, not a re-opened pathname;
                # use a separate disposable database, never overwrite the source.
                admin.sql("CREATE DATABASE isolated_restore_probe;")
                with store.verify_restore_allowed(manifest.identity, request.backup_root) as fd:
                    with os.fdopen(os.dup(fd), "rb") as archive:
                        payload = archive.read()
                    binary(["exec", "-i", database, "pg_restore", "--exit-on-error",
                            "-U", "postgres", "-d", "isolated_restore_probe"], input=payload)
                if admin.sql("SELECT id, marker FROM durable_probe ORDER BY id;",
                             "isolated_restore_probe") != ROWS:
                    raise RuntimeError("restored snapshot lost commits or included uncommitted data")
                if admin.sql("SELECT id, marker FROM durable_probe ORDER BY id;", DB) != ROWS:
                    raise RuntimeError("restore changed protected source")
                port.assert_barriers()
        finally:
            try:
                if client is not None and client.poll() is None:
                    client.kill()
                    client.wait(timeout=10)
            finally:
                cleanup_fixture(project)


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
        print("combined G5 runtime rehearsal is GitHub CI only", file=sys.stderr)
        return 2
    run_case(drift=False)
    run_case(drift=True)
    print("G5 combined real edge, SQL, Docker PREPARED and post-dump drift rehearsal passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
