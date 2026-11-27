"""Disposable GitHub-CI rehearsal between two immutable G5 backend releases."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from uuid import uuid4

from ops.ci_g5_actual_migration import (
    ADMIN, ADMIN_PASSWORD, APP, APP_PASSWORD, CANDIDATE, DATABASE, Admin,
    grant_fixture_schema,
)
from ops.ci_g5_actual_reopen import (
    OriginalContainer, PLAYER_CLIENT, original_database,
    require_committed_receipt_locked, write_original_receipt,
)
from ops.ci_g5_edge_admission import cleanup_fixture, probe, run
from ops.ci_g5_integrated_runtime import binary, ready_db, wait_until
from ops.g5_cutover_lifecycle import G5Lifecycle
from ops.g5_cutover_prepare import BackupReceipt, PreparationRequest
from ops.g5_cutover_state import CutoverStore, Phase, StateError
from ops.g5_docker_writer_fence import DockerWriterFence
from ops.g5_edge_admission import EdgeAdmission
from ops.g5_pg15_writer_fence import Pg15FenceTarget, Pg15PersistentFence


PREVIOUS_SHA = "6ec2f118d4423359707176538d7f835bdb43c0e9"
PREVIOUS_REVISION = "0019_privacy_active_unique"
_SHA = re.compile(r"[0-9a-f]{40}")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
_SCENARIOS = {"success", "pull", "backup", "create", "wrong-image", "retry", "replace"}
_TEST_SECRET = "disposable-g5-transition-ci-key-not-production-2026"


def release_pair(previous_sha: str, candidate_sha: str,
                 previous_image_id: str, candidate_image_id: str) -> tuple[str, str]:
    """Validate immutable source and image identities before transition."""
    if (not isinstance(previous_sha, str) or not _SHA.fullmatch(previous_sha)
            or not isinstance(candidate_sha, str) or not _SHA.fullmatch(candidate_sha)
            or previous_sha == candidate_sha
            or not isinstance(previous_image_id, str) or not _IMAGE_ID.fullmatch(previous_image_id)
            or not isinstance(candidate_image_id, str) or not _IMAGE_ID.fullmatch(candidate_image_id)
            or previous_image_id == candidate_image_id):
        raise StateError("G5 transition requires distinct immutable source and image identities")
    return previous_sha, candidate_sha


def image_provenance(row: dict, expected_sha: str) -> str:
    """Return the immutable image ID only when build labels match source SHA."""
    if not isinstance(row, dict):
        raise StateError("image provenance unavailable")
    image_id = row.get("Id")
    config = row.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if (not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id)
            or not isinstance(labels, dict)
            or labels.get("org.opencontainers.image.revision") != expected_sha
            or labels.get("medievol.g5.source-sha") != expected_sha
            or labels.get("medievol.g5.scope") != "github-ci-disposable"):
        raise StateError("image source provenance mismatch")
    return image_id


def recovery_is_authorized(*, approved: bool, marker_operation: str,
                           operation_id: str, migration_started: bool,
                           baseline_sha256: str, current_sha256: str,
                           previous_image_id: str, observed_image_id: str,
                           phase: Phase | None) -> bool:
    """Require explicit supervision and positive no-mutation/identity evidence."""
    if (approved is not True or marker_operation != operation_id
            or migration_started is not False
            or not isinstance(baseline_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", baseline_sha256)
            or current_sha256 != baseline_sha256
            or previous_image_id != observed_image_id
            or phase not in (None, Phase.RECOVERY_REQUIRED)):
        raise StateError("supervised previous-release recovery evidence is incomplete")
    return True


class EvidenceLog:
    """Append-only, fsync'd, secret-free, hash-chained fixture evidence."""

    def __init__(self, path: Path):
        self.path = path
        self.previous = "0" * 64
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        finally:
            os.close(fd)

    def append(self, event: str, **fields) -> None:
        body = {"event": event, "fields": fields, "previous": self.previous}
        digest = hashlib.sha256(json.dumps(
            body, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()).hexdigest()
        line = json.dumps(body | {"sha256": digest}, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode() + b"\n"
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise StateError("unsafe transition evidence log")
            view = memoryview(line)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise StateError("transition evidence write failed")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        self.previous = digest

    def verify(self) -> list[dict]:
        info = self.path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise StateError("unsafe transition evidence log")
        previous = "0" * 64
        rows = []
        for line in self.path.read_bytes().splitlines():
            try:
                row = json.loads(line)
                body = {key: row[key] for key in ("event", "fields", "previous")}
                digest = hashlib.sha256(json.dumps(
                    body, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()).hexdigest()
            except (ValueError, TypeError, KeyError):
                raise StateError("transition evidence log is invalid") from None
            if row.get("previous") != previous or row.get("sha256") != digest:
                raise StateError("transition evidence chain is broken")
            previous = digest
            rows.append(row)
        self.previous = previous
        return rows


def _git(repo: Path, *args, check=True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        timeout=120, check=False,
    )
    if check and result.returncode:
        raise StateError("immutable release source unavailable")
    return result.stdout.strip()


def _git_exists(repo: Path, *args) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), *args], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=120, check=False,
    ).returncode == 0


def _ensure_commit(repo: Path, sha: str) -> None:
    if _git_exists(repo, "cat-file", "-e", sha + "^{commit}"):
        return
    subprocess.run(
        ["git", "-C", str(repo), "fetch", "--no-tags", "--depth=1", "origin", sha],
        capture_output=True, timeout=180, check=False,
    )
    if _git(repo, "rev-parse", sha + "^{commit}", check=False) != sha:
        raise StateError("required historical release SHA could not be fetched exactly")


@contextmanager
def _worktree(repo: Path, parent: Path, sha: str):
    target = parent / ("source-" + sha[:12])
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach", str(target), sha],
        capture_output=True, timeout=180, check=True,
    )
    try:
        yield target
    finally:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(target)],
            capture_output=True, timeout=60, check=False,
        )


def _docker_json(*args) -> dict:
    raw = run(list(args))
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise StateError("invalid Docker identity response") from None
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, dict):
        raise StateError("ambiguous Docker identity response")
    return value


def _local_docker(args, timeout=600):
    env = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH"):
        env.pop(key, None)
    try:
        result = subprocess.run(
            ["docker", "--host", "unix:///var/run/docker.sock", *args],
            env=env, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        raise StateError("local Docker image acquisition failed or timed out") from None
    if result.returncode:
        raise StateError("local Docker image acquisition failed")
    return result.stdout


def _container(identity: str) -> dict:
    if not isinstance(identity, str) or not _CONTAINER_ID.fullmatch(identity):
        raise StateError("invalid container identity")
    rows = json.loads(run(["inspect", "--type", "container", identity]))
    if not isinstance(rows, list) or len(rows) != 1 or rows[0].get("Id") != identity:
        raise StateError("container identity changed")
    return rows[0]


def _container_ip(identity: str, network: str) -> str:
    networks = _container(identity).get("NetworkSettings", {}).get("Networks")
    address = networks.get(network, {}).get("IPAddress") if isinstance(networks, dict) else None
    try:
        return str(ipaddress.IPv4Address(address))
    except (ipaddress.AddressValueError, TypeError):
        raise StateError("private fixture container address unavailable") from None


def _image(image: str) -> dict:
    rows = json.loads(run(["image", "inspect", image]))
    if not isinstance(rows, list) or len(rows) != 1:
        raise StateError("image reference is ambiguous")
    return rows[0]


def _build_image(repo: Path, sha: str, tag: str, context: Path) -> tuple[str, str]:
    env = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH"):
        env.pop(key, None)
    row = subprocess.run(
        [
            "docker", "--host", "unix:///var/run/docker.sock", "build",
            "--tag", tag,
            "--label", "org.opencontainers.image.revision=" + sha,
            "--label", "medievol.g5.source-sha=" + sha,
            "--label", "medievol.g5.scope=github-ci-disposable",
            "--file", str(context / "Dockerfile"), str(context),
        ],
        env=env, capture_output=True, text=True, timeout=1200, check=False,
    )
    if row.returncode:
        raise StateError("isolated immutable release image build failed")
    inspected = _image(tag)
    image_id = image_provenance(inspected, sha)
    if not isinstance(inspected.get("RepoDigests"), list):
        raise StateError("image digest evidence unavailable")
    base = _image("python:3.11-slim")
    repo_digests = base.get("RepoDigests")
    if not isinstance(repo_digests, list) or not any(
        isinstance(value, str) and "@sha256:" in value for value in repo_digests
    ):
        raise StateError("base image immutable digest unavailable")
    return image_id, next(value for value in repo_digests if "@sha256:" in value)


def _app_call(image: str, network: str, nginx_alias: str, action: str, payload: dict):
    command = [
        "run", "--rm", "--network", network,
        "--label", "medievol.g5.edge-fixture=" + network,
        image, "python", "-c", PLAYER_CLIENT,
        "http://" + nginx_alias, action,
        json.dumps(payload, separators=(",", ":")),
    ]
    try:
        return json.loads(run(command))
    except (ValueError, TypeError):
        raise StateError("fixture HTTP or Socket.IO response was invalid") from None


def _api_version(image: str, network: str, nginx_alias: str, expected: int) -> None:
    probe_code = r'''
import httpx, sys
response = httpx.get("http://"+sys.argv[1]+"/api/building/wonder/funding",
                     params={"city_id":1,"world_id":1}, timeout=8, trust_env=False)
print(response.status_code)
'''
    output = run([
        "run", "--rm", "--network", network, image, "python", "-c",
        probe_code, nginx_alias,
    ]).strip()
    if output != str(expected):
        raise StateError("Nginx routed to the wrong G5 release version")


class TransitionPort:
    """G5 lifecycle adapter for two immutable images on one isolated DB volume."""

    def __init__(self, request, root, evidence, project, network_id, volume,
                 database, frontend, nginx, previous, previous_worker,
                 candidate_id, candidate_worker, images, scenario, baseline):
        self.request, self.root, self.evidence = request, root, evidence
        self.project, self.network_id, self.volume = project, network_id, volume
        self.database, self.frontend, self.nginx = database, frontend, nginx
        self.previous, self.previous_worker = previous, previous_worker
        self.database_address = _container_ip(database, project)
        self.frontend_address = _container_ip(frontend, project)
        self.nginx_address = _container_ip(nginx, project)
        self.previous_address = _container_ip(previous, project)
        self.candidate_id, self.candidate_worker = candidate_id, candidate_worker
        self.images, self.scenario, self.baseline = images, scenario, baseline
        self.admin = Admin(database)
        self.edge = EdgeAdmission(str(root / "host"), project, nginx, run, probe)
        self.sql = Pg15PersistentFence(Pg15FenceTarget(DATABASE, APP, ADMIN), self.admin)
        self.docker = DockerWriterFence(project, run)
        self.store = CutoverStore(str(root / "host"))
        self.previous_started_at = {
            previous: _container(previous)["State"]["StartedAt"],
            previous_worker: _container(previous_worker)["State"]["StartedAt"],
        }
        self.original_db = original_database(self.admin)
        self.originals = [
            OriginalContainer.capture(_container(cid), project, service)
            for cid, service in ((previous, "backend"), (previous_worker, "worker"))
        ]
        write_original_receipt(
            root / "host" / ".ops-state" / "original.json",
            self.original_db, self.originals,
        )
        self.migration_started = False
        self.candidate_created = False
        self.published = False
        self.player_worker_verified = False
        self.release_receipt = root / "host" / ".release.json"

    def _identity(self):
        return _container(self.database)["Id"] == self.database and (
            _container(self.nginx)["Id"] == self.nginx
        )

    def _assert_persistent_resources(self):
        network = _docker_json("network", "inspect", self.network_id)
        volume_info = _docker_json("volume", "inspect", self.volume)
        mountpoint = volume_info.get("Mountpoint")
        db = _container(self.database)
        mounts = [row for row in db.get("Mounts", [])
                  if row.get("Type") == "volume" and row.get("Name") == self.volume
                  and row.get("Destination") == "/var/lib/postgresql/data"]
        if (network.get("Id") != self.network_id or network.get("Internal") is not True
                or not isinstance(mountpoint, str) or len(mounts) != 1
                or mounts[0].get("Source") != mountpoint or not self._identity()):
            raise StateError("database volume or private network identity changed")
        for cid in (self.database, self.frontend, self.nginx, self.previous,
                    self.previous_worker):
            row = _container(cid)
            if row.get("HostConfig", {}).get("PortBindings") not in (None, {}):
                raise StateError("fixture container unexpectedly publishes a port")

    def _check_old_stopped(self):
        for cid in (self.previous, self.previous_worker):
            row = _container(cid)
            if (row["State"].get("Running") is not False
                    or row["State"].get("StartedAt") != self.previous_started_at[cid]):
                raise StateError("previous release was restarted or changed")

    def _database_hash(self) -> str:
        payload = binary(["exec", self.database, "pg_dump", "-U", ADMIN,
                          "-d", DATABASE, "-Fc"])
        if not payload.startswith(b"PGDMP"):
            raise StateError("isolated PostgreSQL dump verification failed")
        return hashlib.sha256(payload).hexdigest()

    def close_admission(self):
        self.evidence.append("edge_close_started")
        self.edge.close()
        self.evidence.append("edge_closed")

    def fence_database_writes(self):
        self.evidence.append("database_fence_started")
        self.sql.engage()
        self.evidence.append("database_fenced")

    def stop_writers(self):
        self.evidence.append("previous_writer_stop_started")
        self.docker.engage()
        self.evidence.append("previous_writers_stopped")

    def verify_drain(self):
        self._assert_persistent_resources()
        self.edge.assert_closed()
        self.sql.assert_closed()
        self.docker.assert_closed()
        self._check_old_stopped()
        return True

    def capture_snapshot(self):
        self.evidence.append("backup_started")
        payload = binary(["exec", self.database, "pg_dump", "-U", ADMIN,
                          "-d", DATABASE, "-Fc"])
        if not payload.startswith(b"PGDMP"):
            raise StateError("isolated PostgreSQL snapshot missing")
        digest = hashlib.sha256(payload).hexdigest()
        self.baseline = digest
        self.evidence.append("pre_migration_database_fingerprint", sha256=digest)
        if self.scenario == "backup":
            raise StateError("injected snapshot failure before migration")
        backup_dir = self.root / "backups"
        backup_path = backup_dir / "cutover.dump"
        fd = os.open(backup_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(backup_dir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self.evidence.append("backup_complete", sha256=digest)
        return BackupReceipt(str(backup_path), digest)

    def verify_continuity(self, identity):
        if (identity.compose_project != self.project or identity.postgres_db != DATABASE):
            raise StateError("transition project or database identity changed")
        self.verify_drain()
        return True

    def migrate(self, identity):
        self.evidence.append("candidate_container_create_started")
        source_image = self.images["previous"] if self.scenario == "wrong-image" else self.images["candidate"]
        self._create_candidate(source_image)
        self.candidate_created = True
        if source_image != self.images["candidate"]:
            self.evidence.append("wrong_candidate_image_detected")
            raise StateError("candidate container image does not match candidate provenance")
        self.evidence.append("candidate_containers_created_stopped")
        self.migration_started = True
        self.evidence.append("migration_started", image_id=self.images["candidate"])
        maintenance_url = (
            f"postgresql+psycopg://{ADMIN}:{ADMIN_PASSWORD}@{self.database_address}:5432/{DATABASE}"
        )
        self._oneshot(self.images["candidate"], "alembic", "-c", "/app/alembic.ini",
                      "upgrade", "head", maintenance_url)
        self.sql.assert_closed()
        if self.admin.sql("SELECT version_num FROM alembic_version;", DATABASE) != CANDIDATE:
            raise StateError("candidate migration did not reach expected Alembic revision")
        grant_fixture_schema(self.admin)
        self._oneshot(self.images["candidate"], "python", "-m", "app.seed", maintenance_url)
        self.sql.assert_closed()
        self._oneshot(self.images["candidate"], "python", "-m", "app.seed", maintenance_url)
        self.sql.assert_closed()
        self.evidence.append("migration_and_seed_complete", revision=CANDIDATE)

    def _create_candidate(self, image_id):
        for service, alias, command in (
            ("backend", "candidate-backend", []),
            ("worker", "candidate-worker", ["python", "-m", "app.worker"]),
        ):
            name = self.project + "-candidate-" + service
            command = [
                "create", "--name", name, "--network", self.project,
                "--network-alias", alias,
                "--label", "medievol.g5.edge-fixture=" + self.project,
                "--label", "com.docker.compose.project=" + self.project + "-candidate",
                "--label", "com.docker.compose.service=" + service,
                "--restart=no",
                "-e", "APP_ENV=test",
                "-e", "DATABASE_URL=" + (
                    f"postgresql+psycopg://{APP}:{APP_PASSWORD}@{self.database_address}:5432/{DATABASE}"
                ),
                "-e", "SECRET_KEY=" + _TEST_SECRET,
                image_id, *command,
            ]
            created = run(command).strip()
            if not _CONTAINER_ID.fullmatch(created):
                raise StateError("candidate container creation identity missing")
            row = _container(created)
            expected_labels = row.get("Config", {}).get("Labels", {})
            if (row.get("Image") != image_id or row.get("State", {}).get("Status") != "created"
                    or row.get("State", {}).get("Running") is not False
                    or expected_labels.get("com.docker.compose.project") != self.project + "-candidate"
                    or row.get("HostConfig", {}).get("RestartPolicy", {}).get("Name") != "no"):
                raise StateError("candidate container was not created stopped with exact image identity")
            if service == "backend":
                self.candidate_id = created
                if self.scenario == "create":
                    self.evidence.append("candidate_container_create_failed",
                                         created_stopped=True, migration_started=False)
                    raise StateError("injected candidate worker creation failure")
            else:
                self.candidate_worker = created

    def _oneshot(self, image, *command):
        database_url = command[-1]
        args = [
            "run", "--rm", "--network", self.project,
            "--label", "medievol.g5.edge-fixture=" + self.project,
            "-e", "APP_ENV=test", "-e", "DATABASE_URL=" + database_url,
            image, *command[:-1],
        ]
        run(args)

    def verify_candidate_readonly(self, identity):
        self.verify_drain()
        candidate = image_provenance(_image(self.images["candidate"]), identity.candidate_sha)
        return (
            candidate == self.images["candidate"]
            and self.admin.sql("SELECT version_num FROM alembic_version;", DATABASE) == CANDIDATE
            and all(self._candidate_container(cid, stopped=True)
                    for cid in (self.candidate_id, self.candidate_worker))
        )

    def publish_candidate(self, identity):
        row = {
            "operation_id": identity.operation_id,
            "previous_sha": identity.previous_sha,
            "candidate_sha": identity.candidate_sha,
            "previous_image_id": self.images["previous"],
            "candidate_image_id": self.images["candidate"],
            "database": DATABASE,
            "volume": self.volume,
            "network_id": self.network_id,
        }
        data = json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        fd = os.open(self.release_receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(self.release_receipt.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        self.published = True
        self.evidence.append("candidate_release_published", image_id=self.images["candidate"])

    def restore_previous(self, identity, verified_fd):
        raise StateError("transition rehearsal never restores a database snapshot")

    def verify_previous_readonly(self, identity):
        return False

    def reopen_writers(self, identity):
        require_committed_receipt_locked(self.store, identity)
        try:
            self._reopen_candidate(identity)
        except BaseException:
            self._restrict_after_failure()
            raise

    def _reopen_candidate(self, identity):
        self.evidence.append("candidate_reopen_started")
        self.verify_drain()
        if not self.published or self.migration_started is not True:
            raise StateError("candidate release is not durably published")
        self._require_release_receipt(identity)
        self._assert_persistent_resources()
        if not all(self._candidate_container(cid, stopped=True)
                   for cid in (self.candidate_id, self.candidate_worker)):
            raise StateError("candidate runtime identity changed before commit activation")
        self.admin.execute_committed(
            f'ALTER DATABASE "{DATABASE}" CONNECTION LIMIT {self.original_db.connection_limit};'
        )
        self.admin.execute_committed(f'ALTER ROLE "{APP}" LOGIN;')
        if self.scenario == "replace":
            self.evidence.append("candidate_replacement_failed", migration_started=True)
            raise StateError("injected candidate replacement failure after durable COMMITTED")
        for cid in (self.candidate_id, self.candidate_worker):
            if not _container(cid)["State"].get("Running"):
                run(["start", cid])
        if not all(self._candidate_container(cid, stopped=False)
                   for cid in (self.candidate_id, self.candidate_worker)):
            raise StateError("candidate runtime image or network identity changed")
        wait_until(lambda: probe([
            "exec", self.candidate_id, "python", "-c",
            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)",
        ])[0] == 0, "candidate backend health failed")
        self.candidate_address = _container_ip(self.candidate_id, self.project)
        self._check_old_stopped()
        self._route_nginx_to_candidate()
        self._open_edge()
        _api_version(self.images["candidate"], self.project, self.nginx_address, 401)
        _app_call(self.images["candidate"], self.project, self.nginx_address, "socket",
                  {"token": self.access_token, "user": self.user_id})
        self._prove_player_and_worker()
        self.evidence.append("candidate_http_socket_worker_verified")

    def _candidate_container(self, cid, *, stopped):
        if not isinstance(cid, str) or not _CONTAINER_ID.fullmatch(cid):
            return False
        row = _container(cid)
        networks = row.get("NetworkSettings", {}).get("Networks")
        status = row.get("State", {})
        return (
            row.get("Image") == self.images["candidate"]
            and row.get("Config", {}).get("Labels", {}).get(
                "com.docker.compose.project"
            ) == self.project + "-candidate"
            and row.get("HostConfig", {}).get("RestartPolicy", {}).get("Name") == "no"
            and row.get("HostConfig", {}).get("PortBindings") in (None, {})
            and isinstance(networks, dict) and len(networks) == 1
            and networks.get(self.project, {}).get("NetworkID") == self.network_id
            and status.get("Running") is (not stopped)
            and (not stopped or status.get("Status") == "created")
        )

    def _require_release_receipt(self, identity):
        try:
            raw = self.release_receipt.read_bytes()
            row = json.loads(raw)
            info = self.release_receipt.stat(follow_symlinks=False)
        except (OSError, ValueError):
            raise StateError("candidate release receipt unavailable") from None
        expected = {
            "operation_id": identity.operation_id,
            "previous_sha": identity.previous_sha,
            "candidate_sha": identity.candidate_sha,
            "previous_image_id": self.images["previous"],
            "candidate_image_id": self.images["candidate"],
            "database": DATABASE,
            "volume": self.volume,
            "network_id": self.network_id,
        }
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or row != expected or raw != json.dumps(
                    expected, sort_keys=True, separators=(",", ":")
                ).encode() + b"\n"):
            raise StateError("candidate release receipt identity mismatch")

    def _restrict_after_failure(self):
        actions = [
            self.edge.close,
            lambda: self.admin.execute_committed(
                f'ALTER DATABASE "{DATABASE}" CONNECTION LIMIT 0;'
            ),
            lambda: self.admin.execute_committed(f'ALTER ROLE "{APP}" NOLOGIN;'),
            lambda: self.admin.execute_committed(
                f"SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity "
                f"WHERE datname='{DATABASE}' AND pid<>pg_backend_pid();"
            ),
        ]
        for cid in (self.candidate_id, self.candidate_worker):
            if isinstance(cid, str) and _CONTAINER_ID.fullmatch(cid):
                row = _container(cid)
                if row["State"].get("Running") is True:
                    actions.extend((
                        lambda item=cid: run(["update", "--restart=no", item]),
                        lambda item=cid: run(["stop", "--time", "10", item]),
                    ))
                elif row["State"].get("Status") not in {"created", "exited"}:
                    raise StateError("candidate container state is uncertain after failure")
        errors = []
        for action in actions:
            try:
                action()
            except Exception:
                errors.append(True)
        if errors:
            raise StateError("one or more post-commit restrictions are uncertain")
        self.edge.assert_closed()
        self.sql.assert_closed()
        self._check_old_stopped()

    def supervised_recover_previous(self):
        """Resume only the exact old service after explicit no-mutation proof."""
        rows = self.evidence.verify()
        if (self.migration_started
                or any(row.get("event") == "migration_started" for row in rows)
                or self._database_hash() != self.baseline):
            raise StateError("database mutation evidence blocks previous release recovery")
        self._check_old_stopped()
        marker = self.root / "host" / ".ops-state" / "g5-cutover-activated"
        try:
            marker_stat = marker.stat(follow_symlinks=False)
            marker_data = marker.read_text()
        except OSError:
            raise StateError("G5 activation marker cannot be verified") from None
        if (not stat.S_ISREG(marker_stat.st_mode) or marker_stat.st_uid != os.geteuid()
                or stat.S_IMODE(marker_stat.st_mode) != 0o600 or marker_stat.st_nlink != 1
                or marker_data != f"version=1\noperation_id={self.request.operation_id}\n"):
            raise StateError("G5 activation marker identity mismatch")
        if self.admin.sql("SELECT version_num FROM alembic_version;", DATABASE) != PREVIOUS_REVISION:
            raise StateError("previous schema revision is not positively established")
        for cid in (self.candidate_id, self.candidate_worker):
            if isinstance(cid, str) and _CONTAINER_ID.fullmatch(cid):
                if _container(cid)["State"].get("Running") is not False:
                    raise StateError("candidate writer is running during previous-release recovery")
        for cid in (self.previous, self.previous_worker):
            row = _container(cid)
            original = next(item for item in self.originals if item.identity == cid)
            original.assert_fenced_identity(row, self.project)
        if _container(self.previous)["Image"] != self.images["previous"]:
            raise StateError("previous release image changed before recovery")

        self.admin.execute_committed(
            f'ALTER DATABASE "{DATABASE}" CONNECTION LIMIT {self.original_db.connection_limit};'
        )
        self.admin.execute_committed(f'ALTER ROLE "{APP}" LOGIN;')
        for cid in (self.previous, self.previous_worker):
            run(["start", cid])
            row = _container(cid)
            if row.get("Image") != self.images["previous"] or row["State"].get("Running") is not True:
                raise StateError("previous release recovery identity is uncertain")
        run(["exec", self.nginx, "nginx", "-t"])
        run(["exec", self.nginx, "nginx", "-s", "reload"])
        self._open_edge()
        wait_until(lambda: probe([
            "exec", self.nginx, "wget", "-q", "-O", "/dev/null", "-T", "2",
            "http://127.0.0.1/api/health",
        ])[0] == 0, "supervised previous release health failed")
        _api_version(self.images["previous"], self.project, self.nginx_address, 404)
        _app_call(self.images["previous"], self.project, self.nginx_address, "socket",
                  {"token": self.access_token, "user": self.user_id})

        if self.release_receipt.exists():
            raise StateError("failed transition unexpectedly published candidate identity")
        self.evidence.append("supervised_previous_release_reopened",
                             previous_image_id=self.images["previous"],
                             snapshot_restore=False, marker_retained=True,
                             legacy_authorized=False)

    def _route_nginx_to_candidate(self):
        config = self.root / "host" / "nginx.g5.conf"
        current = config.read_text()
        updated = current.replace(
            "server " + self.previous_address + ":8000;",
            "server " + self.candidate_address + ":8000;",
        )
        if updated == current or updated.count("server " + self.candidate_address + ":8000;") != 1:
            raise StateError("Nginx release route could not be switched exactly")
        fd = os.open(config, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
        with os.fdopen(fd, "w") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        run(["exec", self.nginx, "nginx", "-t"])
        run(["exec", self.nginx, "nginx", "-s", "reload"])
        self.evidence.append("nginx_candidate_route_reloaded")

    def _open_edge(self):
        self.edge.assert_closed()
        state = self.root / "host" / ".ops-state" / "edge-maintenance"
        marker = state / "open"
        marker.mkdir(mode=0o755)
        marker.chmod(0o755)
        directory = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def _prove_player_and_worker(self):
        _app_call(self.images["candidate"], self.project, self.nginx_address, "join",
                  {"world": self.world_id, "token": self.access_token})
        city = int(self.admin.sql(
            f"SELECT id FROM cities WHERE owner_id={self.user_id} AND world_id={self.world_id} "
            "ORDER BY id LIMIT 1;", DATABASE
        ))
        quotes = _app_call(self.images["candidate"], self.project, self.nginx_address, "available",
                           {"world": self.world_id, "city": city, "token": self.access_token})
        quote = next((item for item in quotes if item.get("name") == "warehouse"
                      and item.get("can_upgrade") is True), None)
        if quote is None:
            raise StateError("candidate version did not expose a writable building path")
        queued = _app_call(
            self.images["candidate"], self.project, self.nginx_address, "upgrade",
            {"world": self.world_id, "city": city, "token": self.access_token,
             "building": "warehouse"},
        )
        queue_id, level = queued.get("id"), queued.get("target_level")
        if type(queue_id) is not int or type(level) is not int:
            raise StateError("candidate HTTP write did not create a durable queue")
        if self.admin.sql(
            f"SELECT count(*) FROM building_queue WHERE id={queue_id} AND city_id={city};",
            DATABASE,
        ) != "1":
            raise StateError("candidate HTTP write was not persistent")
        self.admin.sql(
            f"UPDATE building_queue SET finish_time=now()-interval '2 seconds' "
            f"WHERE id={queue_id} AND city_id={city};", DATABASE
        )
        wait_until(lambda: self.admin.sql(
            f"SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM building_queue WHERE id={queue_id}) "
            f"AND EXISTS (SELECT 1 FROM buildings WHERE city_id={city} "
            f"AND name='warehouse' AND level={level}) THEN 1 ELSE 0 END;", DATABASE
        ) == "1", "candidate worker did not persist queue completion")
        self.player_worker_verified = True


def _create_container(project, network, service, image, *, alias=None, mounts=(),
                      environment=(), command=(), restart="no", extra=()):
    args = [
        "create", "--name", project + "-" + service, "--network", network,
        "--label", "medievol.g5.edge-fixture=" + project,
        "--label", "com.docker.compose.project=" + project,
        "--label", "com.docker.compose.service=" + service,
        "--restart=" + restart,
    ]
    if alias:
        args.extend(["--network-alias", alias])
    for mount_type, source, target, read_only in mounts:
        specification = f"type={mount_type},source={source},target={target}"
        if read_only:
            specification += ",readonly"
        args.extend(["--mount", specification])
    for item in environment:
        args.extend(["-e", item])
    args.extend(extra)
    args.append(image)
    args.extend(command)
    identity = run(args).strip()
    if not _CONTAINER_ID.fullmatch(identity):
        raise StateError("fixture container identity missing")
    return identity


def _wait_for_db(container):
    wait_until(lambda: ready_db(container), "isolated PostgreSQL not ready")


def _fixture(scenario: str, workspace: Path, approved_recovery: bool):
    repo = Path(__file__).resolve().parents[1]
    root = Path(tempfile.mkdtemp(prefix="bm-g5-transition-", dir=workspace))
    os.chmod(root, 0o700)
    host = root / "host"
    backups = root / "backups"
    state = host / ".ops-state"
    edge = state / "edge-maintenance"
    for directory, mode in ((host, 0o700), (backups, 0o700), (state, 0o700),
                            (edge, 0o755)):
        directory.mkdir(mode=mode)
        directory.chmod(mode)
    (edge / "open").mkdir(mode=0o755)
    (edge / "open").chmod(0o755)
    project = "bm-g5-edge-" + uuid4().hex
    evidence = EvidenceLog(state / "transition.jsonl")
    containers, volumes, networks = [], [], []
    image_tags = []
    preserve = False
    candidate_sha = _git(repo, "rev-parse", "HEAD")
    if not _SHA.fullmatch(candidate_sha) or candidate_sha == PREVIOUS_SHA:
        raise StateError("candidate checkout SHA is invalid or equals previous release")
    if _git(repo, "show", f"{candidate_sha}:batalla_medieval_backend/alembic/versions/0020_wonder_funding_rules.py") == "":
        raise StateError("candidate source does not contain Alembic revision 0020")
    _ensure_commit(repo, PREVIOUS_SHA)
    if _git(repo, "show", f"{PREVIOUS_SHA}:batalla_medieval_backend/alembic/versions/0019_privacy_active_case_uniqueness.py") == "":
        raise StateError("historical source does not contain Alembic revision 0019")
    if _git_exists(
        repo, "cat-file", "-e",
        f"{PREVIOUS_SHA}:batalla_medieval_backend/alembic/versions/0020_wonder_funding_rules.py",
    ):
        raise StateError("historical source unexpectedly includes Alembic revision 0020")

    try:
        previous_tag = "medievol-g5-release-previous:" + project
        candidate_tag = "medievol-g5-release-candidate:" + project
        _local_docker(["pull", "python:3.11-slim"])
        _local_docker(["pull", "postgres:15-alpine"])
        _local_docker(["pull", "nginx:1.28-alpine"])
        image_tags.append(previous_tag)
        with _worktree(repo, root, PREVIOUS_SHA) as old_tree:
            previous_image, base_digest = _build_image(
                repo, PREVIOUS_SHA, previous_tag,
                old_tree / "batalla_medieval_backend",
            )
        network = project
        volume = project + "-pgdata"
        networks.append(network)
        volumes.append(volume)
        run(["network", "create", "--internal", "--label",
             "medievol.g5.edge-fixture=" + project, network])
        run(["volume", "create", "--label", "medievol.g5.edge-fixture=" + project, volume])
        database = _create_container(
            project, network, "database", "postgres:15-alpine", alias="database",
            environment=("POSTGRES_PASSWORD=" + ADMIN_PASSWORD,),
            mounts=(("volume", volume, "/var/lib/postgresql/data", False),), restart="no",
        )
        containers.append(database)
        run(["start", database])
        _wait_for_db(database)
        admin = Admin(database)
        admin.sql(f"CREATE ROLE {APP} LOGIN PASSWORD '{APP_PASSWORD}';")
        admin.sql(f"CREATE DATABASE {DATABASE};")
        database_address = _container_ip(database, network)
        maintenance_url = (
            f"postgresql+psycopg://{ADMIN}:{ADMIN_PASSWORD}@{database_address}:5432/{DATABASE}"
        )
        _oneshot = [
            "run", "--rm", "--network", network,
            "--label", "medievol.g5.edge-fixture=" + project,
            "-e", "APP_ENV=test", "-e", "DATABASE_URL=" + maintenance_url,
        ]
        run([*_oneshot, previous_image, "alembic", "-c", "/app/alembic.ini",
             "upgrade", PREVIOUS_REVISION])
        if admin.sql("SELECT version_num FROM alembic_version;", DATABASE) != PREVIOUS_REVISION:
            raise StateError("previous image failed to establish Alembic 0019")
        run([*_oneshot, previous_image, "python", "-m", "app.seed"])
        grant_fixture_schema(admin)

        frontend = _create_container(project, network, "frontend", "nginx:1.28-alpine",
                                    alias="frontend", restart="no")
        containers.append(frontend)
        run(["start", frontend])
        old_backend = _create_container(
            project, network, "backend", previous_image, alias="previous",
            environment=("APP_ENV=test",
                         "DATABASE_URL=" + f"postgresql+psycopg://{APP}:{APP_PASSWORD}@{database_address}:5432/{DATABASE}",
                         "SECRET_KEY=" + _TEST_SECRET),
            restart="no",
        )
        old_worker = _create_container(
            project, network, "worker", previous_image, alias="previous-worker",
            environment=("APP_ENV=test",
                         "DATABASE_URL=" + f"postgresql+psycopg://{APP}:{APP_PASSWORD}@{database_address}:5432/{DATABASE}",
                         "SECRET_KEY=" + _TEST_SECRET),
            command=("python", "-m", "app.worker"), restart="no",
        )
        containers.extend((old_backend, old_worker))
        run(["start", old_backend])
        run(["start", old_worker])
        config = host / "nginx.g5.conf"
        raw_config = (repo / "nginx.g5.conf").read_text()
        previous_address = _container_ip(old_backend, network)
        frontend_address = _container_ip(frontend, network)
        config_contents = raw_config.replace("server backend:8000;",
                                             "server " + previous_address + ":8000;")
        config_contents = config_contents.replace("server frontend:80;",
                                                  "server " + frontend_address + ":80;")
        if config_contents == raw_config:
            raise StateError("fixture Nginx config has no backend upstream to replace")
        config.write_text(config_contents)
        config.chmod(0o644)
        nginx = _create_container(
            project, network, "nginx", "nginx:1.28-alpine", alias="nginx",
            mounts=(("bind", config, "/etc/nginx/nginx.conf", True),
                    ("bind", edge, "/etc/nginx/edge-maintenance", True)),
            restart="no",
        )
        containers.append(nginx)
        run(["start", nginx])
        wait_until(lambda: probe([
            "exec", nginx, "wget", "-q", "-O", "/dev/null", "-T", "2",
            "http://127.0.0.1/api/health",
        ])[0] == 0, "previous release was not reachable through Nginx")
        if admin.sql("SELECT version_num FROM alembic_version;", DATABASE) != PREVIOUS_REVISION:
            raise StateError("previous application changed the Alembic revision")
        nginx_address = _container_ip(nginx, network)
        _api_version(previous_image, network, nginx_address, 404)

        identity = original_database(admin)
        world_id_raw = admin.sql("SELECT id FROM worlds WHERE name='Mundo 1';", DATABASE)
        if not world_id_raw.isdecimal():
            raise StateError("historical world was not seeded")
        user = _app_call(previous_image, network, nginx_address, "register", {
            "username": "g5_transition_player",
            "email": "g5-transition@example.com",
            "password": "G5-Transition-Player-2026!",
        })
        user_id = user.get("id")
        if type(user_id) is not int or user_id <= 0:
            raise StateError("previous release HTTP write was not established")
        token = admin.sql(
            f"SELECT verification_token FROM users WHERE id={user_id} AND NOT is_verified;",
            DATABASE,
        )
        _app_call(previous_image, network, nginx_address, "verify", {"token": token})
        access = _app_call(previous_image, network, nginx_address, "login", {
            "username": "g5_transition_player", "password": "G5-Transition-Player-2026!",
        }).get("access_token")
        if not isinstance(access, str) or not access:
            raise StateError("previous release login did not issue an access token")
        _app_call(previous_image, network, nginx_address, "socket",
                  {"token": access, "user": user_id})
        baseline = binary(["exec", database, "pg_dump", "-U", ADMIN,
                           "-d", DATABASE, "-Fc"])
        if not baseline.startswith(b"PGDMP"):
            raise StateError("pre-transition database fingerprint unavailable")
        baseline_hash = hashlib.sha256(baseline).hexdigest()
        evidence.append(
            "previous_release_ready", previous_sha=PREVIOUS_SHA,
            previous_image_id=previous_image,
            database_oid=identity.database_oid, volume=volume,
            network_id=_docker_json("network", "inspect", network)["Id"],
            database_sha256=baseline_hash,
        )

        if scenario == "pull":
            evidence.append("candidate_acquisition_failed", mutation_started=False)
            if _container(old_backend)["State"].get("Running") is not True:
                raise StateError("previous release was not left running after acquisition failure")
            if admin.sql("SELECT version_num FROM alembic_version;", DATABASE) != PREVIOUS_REVISION:
                raise StateError("candidate acquisition failure changed the schema")
            if probe(["exec", nginx, "wget", "-q", "-O", "/dev/null", "-T", "2",
                      "http://127.0.0.1/api/health"])[0] != 0:
                raise StateError("previous release became unavailable after candidate acquisition failure")
            evidence.append("previous_service_still_available")
            print("pull: previous service remained active; no marker, migration, or snapshot restore")
            return

        with _worktree(repo, root, candidate_sha) as current_tree:
            image_tags.append(candidate_tag)
            candidate_image, candidate_base_digest = _build_image(
                repo, candidate_sha, candidate_tag,
                current_tree / "batalla_medieval_backend",
            )
        image_tags.append(candidate_tag)
        release_pair(PREVIOUS_SHA, candidate_sha, previous_image, candidate_image)
        evidence.append(
            "candidate_image_provenance", previous_sha=PREVIOUS_SHA,
            candidate_sha=candidate_sha, previous_image_id=previous_image,
            candidate_image_id=candidate_image, base_image_digest=base_digest,
        )
        if candidate_base_digest != base_digest:
            evidence.append("base_digest_changed_between_builds",
                            previous=base_digest, candidate=candidate_base_digest)
            raise StateError("release builds did not share the same immutable base image")
        images = {"previous": previous_image, "candidate": candidate_image}
        project_network_id = _docker_json("network", "inspect", network)["Id"]
        port = TransitionPort(
            PreparationRequest(
                str(host), str(backups), "ci-" + uuid4().hex,
                PREVIOUS_SHA, candidate_sha, project, DATABASE,
            ),
            root, evidence, project, project_network_id, volume, database, frontend,
            nginx, old_backend, old_worker, "", "", images, scenario, baseline_hash,
        )
        port.access_token, port.user_id, port.world_id = access, user_id, int(world_id_raw)
        try:
            result = G5Lifecycle().execute(port.request, port)
        except BaseException as exc:
            if scenario == "replace":
                manifest = port.store.show()
                if (manifest.phase is not Phase.COMMITTED_WRITERS_ALLOWED
                        or port.migration_started is not True):
                    preserve = True
                    raise StateError(
                        "replacement failure phase or mutation evidence is uncertain"
                    ) from exc
                port.edge.assert_closed()
                port.sql.assert_closed()
                port._check_old_stopped()
                if any(_container(cid)["State"].get("Running") for cid in
                       (port.candidate_id, port.candidate_worker)):
                    preserve = True
                    raise StateError("candidate replacement failure left a writer running") from exc
                if not (state / "g5-cutover-activated").is_file():
                    preserve = True
                    raise StateError("replacement failure lost G5 activation marker") from exc
                evidence.append("replacement_failure_closed",
                                phase=manifest.phase.value, snapshot_restore=False)
                print("replace: candidate replacement failed after COMMITTED; writers and edge remain closed")
                return
            if scenario not in {"backup", "create", "wrong-image", "retry"}:
                preserve = True
                evidence.append("uncertain_failure", phase=str(type(exc).__name__))
                raise
            try:
                evidence.append("pre_mutation_failure", scenario=scenario,
                                migration_started=port.migration_started)
                if scenario == "retry":
                    try:
                        G5Lifecycle().execute(port.request, port)
                    except StateError:
                        evidence.append("unsafe_retry_rejected")
                    else:
                        raise StateError("unsafe G5 operation retry was accepted")
                current_hash = port._database_hash()
                manifest = None
                try:
                    manifest = port.store.show()
                except StateError as state_error:
                    if str(state_error) != "cutover manifest is missing":
                        raise
                phase = manifest.phase if manifest else None
                marker = (state / "g5-cutover-activated").read_text()
                match = re.search(r"^operation_id=([A-Za-z0-9_-]+)$", marker, re.MULTILINE)
                marker_operation = match.group(1) if match else ""
                previous_observed = _container(old_backend).get("Image")
                recovery_is_authorized(
                    approved=approved_recovery, marker_operation=marker_operation,
                    operation_id=port.request.operation_id,
                    migration_started=port.migration_started,
                    baseline_sha256=port.baseline, current_sha256=current_hash,
                    previous_image_id=images["previous"],
                    observed_image_id=previous_observed, phase=phase,
                )
                port.supervised_recover_previous()
                evidence.append("supervised_previous_release_recovery_complete",
                                manifest_phase=phase.value if phase else "PREPARED_NOT_PERSISTED",
                                snapshot_restore=False, marker_retained=True)
                print(f"{scenario}: supervised previous release recovery; marker retained; no snapshot restore")
                return
            except BaseException:
                preserve = True
                raise
        if (scenario != "success" or result.phase is not Phase.COMMITTED_WRITERS_ALLOWED
                or port.store.show() != result or not port.player_worker_verified):
            preserve = True
            raise StateError("release transition did not meet all success assertions")
        evidence.append("transition_complete", phase=result.phase.value,
                        previous_sha=PREVIOUS_SHA, candidate_sha=candidate_sha,
                        previous_image_id=images["previous"],
                        candidate_image_id=images["candidate"],
                        base_image_digest=base_digest,
                        volume=volume, network_id=project_network_id)
        print("success: distinct 0019/0020 releases; HTTP, authenticated Socket.IO, version, "
              "candidate write and worker persistence verified")
    finally:
        if preserve:
            print(f"uncertain fixture preserved closed for reconciliation: project={project}; root={root}",
                  file=sys.stderr)
        else:
            try:
                _export_evidence(evidence.path, workspace, scenario, project)
                cleanup_fixture(project)
                for volume in volumes:
                    run(["volume", "rm", volume])
                for tag in image_tags:
                    run(["image", "rm", tag])
                shutil.rmtree(root)
            except BaseException:
                print(f"fixture cleanup uncertain; project={project}; root={root}", file=sys.stderr)
                raise


def _export_evidence(source: Path, workspace: Path, scenario: str, project: str):
    if not source.exists():
        return
    data = source.read_bytes()
    destination = workspace / f"g5-release-transition-{scenario}-{project}.jsonl"
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        print("G5 release transition rehearsal is GitHub CI only", file=sys.stderr)
        return 2
    if len(argv) not in (2, 3) or argv[0] not in _SCENARIOS:
        print(
            "usage: python -m ops.ci_g5_release_transition "
            "{success,pull,backup,create,wrong-image,retry,replace} "
            "PRIVATE_WORKSPACE [--approve-previous-recovery]",
            file=sys.stderr,
        )
        return 2
    workspace = Path(argv[1])
    if (not workspace.is_absolute() or not workspace.is_dir()
            or workspace.stat().st_uid != os.geteuid()
            or stat.S_IMODE(workspace.stat().st_mode) != 0o700):
        print("workspace must be an existing caller-owned mode-0700 directory", file=sys.stderr)
        return 2
    approved = argv[2:] == ["--approve-previous-recovery"]
    recovery_cases = {"backup", "create", "wrong-image", "retry"}
    if (argv[2:] and not approved) or (argv[0] in recovery_cases and not approved):
        print("pre-migration service recovery requires explicit --approve-previous-recovery",
              file=sys.stderr)
        return 2
    try:
        _fixture(argv[0], workspace, approved)
    except BaseException as exc:
        print(f"G5 release transition failed closed: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
