"""Disposable CI-only actual game migration and supervised reopen laboratory.

This is not a deployment adapter, crash recovery mechanism or proof of
exclusion against a Docker/PostgreSQL administrator outside this fixture.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import asdict
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
from uuid import uuid4

from ops.ci_g5_actual_migration import (
    ADMIN, ADMIN_PASSWORD, APP, APP_PASSWORD, CANDIDATE, DATABASE, IMAGE,
    PREVIOUS, Admin, app_command, grant_fixture_schema,
)
from ops.ci_g5_edge_admission import cleanup_fixture, probe, run
from ops.ci_g5_integrated_runtime import binary, ready_db, wait_until
from ops.g5_cutover_lifecycle import G5Lifecycle
from ops.g5_cutover_prepare import BackupReceipt, PreparationRequest
from ops.g5_cutover_state import CutoverStore, Identity, Phase, StateError
from ops.g5_docker_writer_fence import DockerWriterFence
from ops.g5_edge_admission import EdgeAdmission
from ops.g5_pg15_writer_fence import Pg15FenceTarget, Pg15PersistentFence


_CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")


@dataclass(frozen=True)
class OriginalDatabase:
    database: str
    database_oid: int
    app_role: str
    app_role_oid: int
    maintenance_role: str
    maintenance_role_oid: int
    connection_limit: int
    login: bool
    server_version_num: int

    def __post_init__(self):
        names = (self.database, self.app_role, self.maintenance_role)
        oids = (self.database_oid, self.app_role_oid, self.maintenance_role_oid)
        if (any(not isinstance(n, str) or not _NAME.fullmatch(n) for n in names)
                or self.app_role == self.maintenance_role
                or any(type(oid) is not int or oid <= 0 for oid in oids)
                or self.app_role_oid == self.maintenance_role_oid
                or type(self.connection_limit) is not int
                or self.connection_limit < -1 or self.connection_limit == 0
                or self.login is not True
                or type(self.server_version_num) is not int
                or not 150000 <= self.server_version_num < 160000):
            raise StateError("invalid original PostgreSQL fixture identity or parameters")


def _encoded(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise StateError("invalid Docker inspection response") from None


@dataclass(frozen=True)
class OriginalContainer:
    identity: str
    image: str
    service: str
    policy_name: str
    policy_maximum_retry_count: int
    config: str = field(repr=False)
    host_config: str = field(repr=False)

    @classmethod
    def capture(cls, row, project, service):
        if not isinstance(row, dict):
            raise StateError("invalid Docker container inspection")
        identity, image = row.get("Id"), row.get("Image")
        config, host = row.get("Config"), row.get("HostConfig")
        if (not isinstance(identity, str) or not _CONTAINER_ID.fullmatch(identity)
                or not isinstance(image, str) or not _IMAGE_ID.fullmatch(image)
                or not isinstance(config, dict) or not isinstance(host, dict)):
            raise StateError("missing Docker identity or configuration")
        labels = config.get("Labels")
        if (not isinstance(labels, dict)
                or labels.get("com.docker.compose.project") != project
                or labels.get("com.docker.compose.service") != service
                or service not in {"backend", "worker", "migrate", "seed"}):
            raise StateError("Docker project or service mismatch")
        policy = host.get("RestartPolicy")
        if not isinstance(policy, dict) or set(policy) != {"Name", "MaximumRetryCount"}:
            raise StateError("invalid full restart policy")
        name, retries = policy["Name"], policy["MaximumRetryCount"]
        if (name not in {"no", "always", "unless-stopped", "on-failure"}
                or type(retries) is not int or retries < 0
                or (name != "on-failure" and retries != 0)):
            raise StateError("invalid restart policy or retry count")
        host_without_policy = {key: value for key, value in host.items() if key != "RestartPolicy"}
        return cls(identity, image, service, name, retries,
                   _encoded(config), _encoded(host_without_policy))

    def assert_fenced_identity(self, row, project):
        actual = self.capture(row, project, self.service)
        state = row.get("State")
        if (actual.identity != self.identity or actual.image != self.image
                or actual.config != self.config or actual.host_config != self.host_config
                or actual.policy_name != "no" or actual.policy_maximum_retry_count != 0
                or not isinstance(state, dict)
                or state.get("Status") not in ("created", "exited")
                or any(state.get(key) is not False for key in ("Running", "Paused", "Restarting"))):
            raise StateError("fenced container identity, configuration, policy or state drifted")


def _original_payload(database, containers):
    if not isinstance(database, OriginalDatabase) or not isinstance(containers, (tuple, list)):
        raise StateError("invalid original fixture receipt")
    if not containers or any(not isinstance(item, OriginalContainer) for item in containers):
        raise StateError("invalid original fixture inventory")
    if (len({item.identity for item in containers}) != len(containers)
            or len({item.service for item in containers}) != len(containers)):
        raise StateError("duplicate original fixture inventory")
    items = []
    for item in sorted(containers, key=lambda value: value.service):
        items.append({
            "identity": item.identity, "image": item.image, "service": item.service,
            "policy_name": item.policy_name,
            "policy_maximum_retry_count": item.policy_maximum_retry_count,
            "config_sha256": hashlib.sha256(item.config.encode()).hexdigest(),
            "host_config_sha256": hashlib.sha256(item.host_config.encode()).hexdigest(),
        })
    return {"database": asdict(database), "containers": items}


def _receipt_bytes(database, containers):
    payload = _original_payload(database, containers)
    digest = hashlib.sha256(_encoded(payload).encode()).hexdigest()
    return (_encoded({"original": payload, "sha256": digest}) + "\n").encode()


def _receipt_parent(path):
    path = os.fspath(path)
    if not isinstance(path, str) or not os.path.isabs(path) or os.path.normpath(path) != path:
        raise StateError("invalid original receipt path")
    parent, name = os.path.split(path)
    if not name or name in (".", ".."):
        raise StateError("invalid original receipt path")
    try:
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o022:
            os.close(fd)
            raise StateError("unsafe original receipt directory")
        return fd, name
    except OSError:
        raise StateError("unsafe original receipt directory") from None


def write_original_receipt(path, database, containers):
    data = _receipt_bytes(database, containers)
    parent, name = _receipt_parent(path)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                     os.O_CLOEXEC, 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
    except OSError:
        raise StateError("unable to persist original fixture receipt") from None
    finally:
        os.close(parent)
    require_original_receipt(path, database, containers)


def require_original_receipt(path, database, containers):
    expected = _receipt_bytes(database, containers)
    parent, name = _receipt_parent(path)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=parent)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or info.st_size != len(expected)):
                raise StateError("unsafe original fixture receipt")
            with os.fdopen(os.dup(fd), "rb") as stream:
                data = stream.read(len(expected) + 1)
            if data != expected:
                raise StateError("original fixture receipt differs")
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise StateError("original fixture receipt replaced")
            os.fsync(fd)
            os.fsync(parent)
        finally:
            os.close(fd)
    except OSError:
        raise StateError("unable to verify original fixture receipt") from None
    finally:
        os.close(parent)


def require_committed_receipt_locked(store: CutoverStore, identity: Identity):
    """Recheck the exact on-disk receipt; caller must hold hold_phase's lock.

    Do not call show() here: lifecycle callbacks already own the nonrecursive
    lock. The lifecycle also verifies the held entry on leaving the callback.
    This check does not itself permit any SQL, Docker, or edge change.
    """
    if not isinstance(store, CutoverStore) or not isinstance(identity, Identity):
        raise StateError("invalid receipt check target")
    store._check_process()
    with store._state_directory() as directory:
        manifest, stamp = store._matching(directory, identity)
        if manifest.phase is not Phase.COMMITTED_WRITERS_ALLOWED:
            raise StateError("exact committed receipt required")
        os.fsync(directory)
        store._check_entry(directory, stamp)


def inspect_container(identity):
    rows = json.loads(run(["inspect", "--type", "container", identity]))
    if not isinstance(rows, list) or len(rows) != 1:
        raise StateError("ambiguous fixture container inspection")
    return rows[0]


def original_database(admin):
    fields = admin.sql(
        "SELECT d.datname,d.oid,a.rolname,a.oid,m.rolname,m.oid,d.datconnlimit,"
        "a.rolcanlogin,current_setting('server_version_num') "
        "FROM pg_database d CROSS JOIN pg_roles a CROSS JOIN pg_roles m "
        f"WHERE d.datname='{DATABASE}' AND a.rolname='{APP}' AND m.rolname='{ADMIN}';"
    ).split("|")
    if len(fields) != 9 or fields[7] != "t":
        raise StateError("original PostgreSQL fixture identity unavailable")
    return OriginalDatabase(fields[0], int(fields[1]), fields[2], int(fields[3]),
                            fields[4], int(fields[5]), int(fields[6]), True, int(fields[8]))


class InjectedFailure(StateError):
    """Deliberate, specifically reached scenario fault."""


class ActualReopenPort:
    """Single-process CI adapter; every administrator channel belongs to CI."""

    def __init__(self, request, database, nginx, writers, admin, network_id, addresses, scenario):
        self.request, self.database, self.admin = request, database, admin
        self.writers, self.network_id, self.addresses = writers, network_id, addresses
        self.scenario = scenario
        self.edge = EdgeAdmission(request.host_root, request.compose_project, nginx, run, probe)
        self.sql = Pg15PersistentFence(Pg15FenceTarget(DATABASE, APP, ADMIN), admin)
        self.docker = DockerWriterFence(request.compose_project, run)
        self.store = CutoverStore(request.host_root)
        self.original_db = original_database(admin)
        self.originals = [OriginalContainer.capture(inspect_container(cid), request.compose_project, service)
                          for service, cid in writers.items()]
        self.original_path = str(Path(request.host_root) / ".ops-state" / "original.json")
        self.release = Path(request.host_root) / ".release-sha"
        self.release_identity = None
        write_original_receipt(self.original_path, self.original_db, self.originals)
        self.reopen_attempted = False
        self.postcommit_write = False

    def check_network(self):
        rows = json.loads(run(["network", "inspect", self.network_id]))
        if (len(rows) != 1 or rows[0].get("Id") != self.network_id
                or rows[0].get("Name") != self.request.compose_project
                or rows[0].get("Internal") is not True
                or rows[0].get("Labels", {}).get("medievol.g5.edge-fixture")
                != self.request.compose_project):
            raise StateError("fixture network identity changed")
        members = rows[0].get("Containers")
        if not isinstance(members, dict):
            raise StateError("fixture network membership unavailable")
        expected = set()
        for cid, address in self.addresses.items():
            row = inspect_container(cid)
            if row.get("Id") != cid or row.get("HostConfig", {}).get("PortBindings") not in (None, {}):
                raise StateError("fixture container identity or published ports changed")
            networks = row.get("NetworkSettings", {}).get("Networks")
            if (not isinstance(networks, dict) or set(networks) != {self.request.compose_project}
                    or networks[self.request.compose_project].get("NetworkID") != self.network_id):
                raise StateError("fixture container network changed")
            if not row.get("State", {}).get("Running"):
                if cid not in self.writers.values():
                    raise StateError("fixture nonwriter stopped")
                continue
            expected.add(cid)
            entry = members.get(cid, {})
            if (entry.get("IPv4Address", "").split("/")[0] != address
                    or networks[self.request.compose_project].get("IPAddress") != address):
                raise StateError("fixture network address changed")
        if set(members) != expected:
            raise StateError("unexpected fixture network member")

    def check_db_identity(self, *, fenced):
        row = self.admin.sql(
            "SELECT d.oid,a.oid,m.oid,d.datconnlimit,a.rolcanlogin,"
            "current_setting('server_version_num') FROM pg_database d "
            "CROSS JOIN pg_roles a CROSS JOIN pg_roles m "
            f"WHERE d.datname='{DATABASE}' AND a.rolname='{APP}' AND m.rolname='{ADMIN}';"
        )
        db = self.original_db
        limit, login = (0, "f") if fenced else (db.connection_limit, "t")
        if row != f"{db.database_oid}|{db.app_role_oid}|{db.maintenance_role_oid}|{limit}|{login}|{db.server_version_num}":
            raise StateError("PostgreSQL fixture identity or parameters changed")

    def check_original(self):
        require_original_receipt(self.original_path, self.original_db, self.originals)
        for original in self.originals:
            original.assert_fenced_identity(inspect_container(original.identity), self.request.compose_project)

    def close_admission(self):
        self.check_network()
        self.edge.close()

    def fence_database_writes(self):
        self.check_db_identity(fenced=False)
        self.sql.engage()

    def stop_writers(self):
        self.docker.engage()

    def verify_drain(self):
        self.check_network()
        self.edge.assert_closed()
        self.sql.assert_closed()
        self.docker.assert_closed()
        self.check_db_identity(fenced=True)
        self.check_original()
        return True

    def capture_snapshot(self):
        data = binary(["exec", self.database, "pg_dump", "-U", ADMIN, "-d", DATABASE, "-Fc"])
        if not data.startswith(b"PGDMP"):
            raise StateError("fixture dump missing")
        path = Path(self.request.backup_root) / "cutover.dump"
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(self.request.backup_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return BackupReceipt(str(path), hashlib.sha256(data).hexdigest())

    def verify_continuity(self, identity):
        if (identity.compose_project != self.request.compose_project
                or identity.postgres_db != DATABASE):
            raise StateError("fixture identity changed")
        return self.verify_drain()

    def migrate(self, identity):
        # Unknown errors never enter the automatic rejection/restore branch.
        self.oneshot("alembic", "-c", "/app/alembic.ini", "upgrade", "head")
        self.oneshot("python", "-m", "app.seed")
        self.oneshot("python", "-m", "app.seed")
        grant_fixture_schema(self.admin)
        if self.scenario == "precommit":
            raise InjectedFailure("injected precommit failure")

    def oneshot(self, *command):
        ip = self.addresses[self.database]
        url = f"postgresql+psycopg://{ADMIN}:{ADMIN_PASSWORD}@{ip}:5432/{DATABASE}"
        run(["run", "--rm", "--network", self.network_id, "--label",
             "medievol.g5.edge-fixture=" + self.request.compose_project,
             "-e", "APP_ENV=test", "-e", "DATABASE_URL=" + url, IMAGE, *command])

    def verify_candidate_readonly(self, identity):
        return (self.admin.sql("SELECT version_num FROM alembic_version;", DATABASE) == CANDIDATE
                and int(self.admin.sql("SELECT count(*) FROM cities;", DATABASE)) > 0)

    def publish_candidate(self, identity):
        fd = os.open(self.release, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(identity.candidate_sha + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise StateError("unsafe candidate publication")
            self.release_identity = (info.st_dev, info.st_ino)
        fd = os.open(self.request.host_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def require_publication(self, identity):
        if self.release_identity is None:
            raise StateError("candidate publication not pinned")
        try:
            fd = os.open(self.release, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
            try:
                info = os.fstat(fd)
                expected = (identity.candidate_sha + "\n").encode()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                        or (info.st_dev, info.st_ino) != self.release_identity
                        or info.st_size != len(expected)):
                    raise StateError("unsafe candidate publication")
                if os.read(fd, len(expected) + 1) != expected:
                    raise StateError("candidate publication mismatch")
                current = os.stat(self.release, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != self.release_identity:
                    raise StateError("candidate publication replaced")
            finally:
                os.close(fd)
        except OSError:
            raise StateError("candidate publication unavailable") from None

    def restore_previous(self, identity, verified_fd):
        raise StateError("this fixture does not classify migration rejection")

    def verify_previous_readonly(self, identity):
        return False

    def _restrict_after_failure(self):
        # Attempt each independent barrier even if another command is uncertain.
        errors = []
        actions = [
            self.edge.close,
            lambda: self.admin.execute_committed(f'ALTER DATABASE "{DATABASE}" CONNECTION LIMIT 0;'),
            lambda: self.admin.execute_committed(f'ALTER ROLE "{APP}" NOLOGIN;'),
            lambda: self.admin.execute_committed(
                f"SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity "
                f"WHERE datname='{DATABASE}' AND pid<>pg_backend_pid();"),
        ]
        for original in self.originals:
            actions.extend((
                lambda item=original: run(["update", "--restart=no", item.identity]),
                lambda item=original: run(["stop", "--time", "10", item.identity]),
            ))
        for action in actions:
            try:
                action()
            except Exception:
                errors.append(True)
        if errors:
            raise StateError("fixture fail-closed restriction uncertain")
        self.verify_drain()

    def reopen_writers(self, identity):
        self.reopen_attempted = True
        try:
            require_committed_receipt_locked(self.store, identity)
            self.verify_drain()
            self.require_publication(identity)
            self.admin.execute_committed(
                f'ALTER DATABASE "{DATABASE}" CONNECTION LIMIT {self.original_db.connection_limit};')
            self.admin.execute_committed(f'ALTER ROLE "{APP}" LOGIN;')
            self.check_db_identity(fenced=False)
            run(app_command(self.database, "UPDATE worlds SET name='Postcommit CI write' "
                            "WHERE name='Reopen CI historical';"))
            if self.admin.sql("SELECT count(*) FROM worlds WHERE name='Postcommit CI write';",
                              DATABASE) != "1":
                raise StateError("postcommit application write missing")
            self.postcommit_write = True
            if self.scenario == "midreopen":
                raise InjectedFailure("injected midway reopen failure")
            for service in ("backend", "worker"):
                original = next(item for item in self.originals if item.service == service)
                original.assert_fenced_identity(inspect_container(original.identity), self.request.compose_project)
                run(["start", original.identity])
                self.check_network()
                row = inspect_container(original.identity)
                current = OriginalContainer.capture(row, self.request.compose_project, service)
                if (current.identity != original.identity or current.image != original.image
                        or current.config != original.config or current.host_config != original.host_config
                        or not row["State"]["Running"]):
                    raise StateError("started candidate identity changed")
                policy = original.policy_name
                if policy == "on-failure" and original.policy_maximum_retry_count:
                    policy += ":" + str(original.policy_maximum_retry_count)
                run(["update", "--restart=" + policy, original.identity])
                restored = OriginalContainer.capture(
                    inspect_container(original.identity), self.request.compose_project, service)
                if (restored.policy_name, restored.policy_maximum_retry_count) != (
                        original.policy_name, original.policy_maximum_retry_count):
                    raise StateError("candidate restart policy mismatch")
                if self.scenario == "lost-response" and service == "backend":
                    raise InjectedFailure("injected lost response after backend start and policy update")
            backend = self.writers["backend"]
            wait_until(lambda: probe(["exec", backend, "python", "-c",
                       "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)"])[0] == 0,
                       "candidate backend health failed")
            if not self.verify_candidate_readonly(identity):
                raise StateError("candidate schema changed after start")
            # Do not advertise a completed rehearsal until real authenticated
            # player/Socket.IO and worker write evidence is implemented.
            raise StateError("real authenticated player/socket and worker evidence not yet implemented")
        except BaseException:
            self._restrict_after_failure()
            raise


def run_case(scenario, workspace):
    """Run exactly one disposable scenario; no public ports or external DB."""
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
        raise StateError("actual reopen fixture is GitHub CI only")
    if scenario not in {"precommit", "midreopen", "lost-response", "incomplete"}:
        raise StateError("unknown fixture scenario")
    if not isinstance(workspace, str) or not os.path.isabs(workspace):
        raise StateError("an absolute pre-existing fixture workspace is required")
    base = Path(workspace)
    if base.resolve() != base or base == Path(__file__).resolve().parents[1] or (
            Path(__file__).resolve().parents[1] in base.parents):
        raise StateError("fixture workspace must be outside the checkout")
    info = base.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise StateError("fixture workspace must be caller-owned mode 0700")
    project = "bm-g5-edge-" + uuid4().hex
    label = "medievol.g5.edge-fixture=" + project
    root = base / ("g5-reopen-" + uuid4().hex)
    root.mkdir(mode=0o700)
    host, backups = root / "host", root / "backups"
    host.mkdir(mode=0o700)
    backups.mkdir(mode=0o700)
    state = host / ".ops-state"
    state.mkdir(mode=0o700)
    edge = state / "edge-maintenance"
    edge.mkdir(mode=0o755)
    edge.chmod(0o755)
    (edge / "open").mkdir(mode=0o755)
    (edge / "open").chmod(0o755)
    conf = host / "nginx.g5.conf"
    shutil.copyfile(Path(__file__).resolve().parents[1] / "nginx.g5.conf", conf)
    conf.chmod(0o644)
    try:
        subnet_hint = f"10.{int(project[-4:-2], 16)}.{int(project[-2:], 16)}.0/24"
        network_id = run(["network", "create", "--internal", "--subnet", subnet_hint,
                          "--label", label, project]).strip()
        network = json.loads(run(["network", "inspect", network_id]))[0]
        if (network.get("Id") != network_id or network.get("Name") != project
                or network.get("Internal") is not True):
            raise StateError("isolated network not established")
        configs = network.get("IPAM", {}).get("Config", [])
        if len(configs) != 1:
            raise StateError("ambiguous fixture subnet")
        subnet = ipaddress.ip_network(configs[0]["Subnet"])
        if subnet.version != 4 or subnet.num_addresses < 32 or not subnet.is_private:
            raise StateError("invalid isolated fixture subnet")
        ips = {name: str(subnet.network_address + offset)
               for name, offset in (("database", 10), ("frontend", 11),
                                    ("backend", 12), ("worker", 13), ("nginx", 14))}

        def container(service, args, *, create=False, restart="no", extra=()):
            return run([
                "create" if create else "run", *( [] if create else ["-d"]),
                "--init", "--network", network_id, "--ip", ips[service],
                "--restart", restart, "--label", label,
                "--label", "com.docker.compose.project=" + project,
                "--label", "com.docker.compose.service=" + service,
                *extra, *args,
            ]).strip()

        database = container("database", ["-e", "POSTGRES_PASSWORD=" + ADMIN_PASSWORD,
                                           "postgres:15-alpine"])
        wait_until(lambda: ready_db(database), "fixture PostgreSQL not ready")
        admin = Admin(database)
        admin.sql(f"CREATE ROLE {APP} LOGIN PASSWORD '{APP_PASSWORD}';")
        admin.sql(f"CREATE DATABASE {DATABASE};")
        maintenance_url = f"postgresql+psycopg://{ADMIN}:{ADMIN_PASSWORD}@{ips['database']}:5432/{DATABASE}"
        run(["run", "--rm", "--network", network_id, "--label", label,
             "-e", "APP_ENV=test", "-e", "DATABASE_URL=" + maintenance_url,
             IMAGE, "alembic", "-c", "/app/alembic.ini", "upgrade", PREVIOUS])
        if admin.sql("SELECT version_num FROM alembic_version;", DATABASE) != PREVIOUS:
            raise StateError("historical schema not established")
        grant_fixture_schema(admin)
        inserted = run(app_command(database, """
            INSERT INTO worlds(name, speed_modifier, resource_modifier, map_size,
              special_rules, created_at, is_active, lifecycle_status, lifecycle_changed_at)
            VALUES ('Reopen CI historical', 1, 1, 100, '', now(), true, 'open', now())
            RETURNING id;
        """)).strip()
        if not inserted.isdecimal():
            raise StateError("pre-cutover application write not confirmed")
        app_url = f"postgresql+psycopg://{APP}:{APP_PASSWORD}@{ips['database']}:5432/{DATABASE}"
        env = ["-e", "APP_ENV=test", "-e", "DATABASE_URL=" + app_url,
               "-e", "SECRET_KEY=synthetic-fixture-key-not-for-production-12345"]
        backend = container("backend", [*env, IMAGE], create=True, restart="on-failure:3")
        worker = container("worker", [*env, IMAGE, "python", "-m", "app.worker"],
                           create=True, restart="unless-stopped")
        # Docker normalizes portions of HostConfig on first start. Capture the
        # actual running configuration, not the pre-start representation.
        run(["start", backend])
        run(["start", worker])
        wait_until(lambda: probe(["exec", backend, "python", "-c",
                   "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)"])[0] == 0,
                   "historical backend health failed")
        frontend = container("frontend", ["nginx:1.28-alpine"])
        nginx = container("nginx", [
            "--mount", f"type=bind,source={conf},target=/etc/nginx/nginx.conf,readonly",
            "--mount", f"type=bind,source={edge},target=/etc/nginx/edge-maintenance,readonly",
            "nginx:1.28-alpine",
        ], extra=("--add-host", "backend:" + ips["backend"],
                  "--add-host", "frontend:" + ips["frontend"]))
        request = PreparationRequest(str(host), str(backups), "ci-" + uuid4().hex,
                                     "a" * 40, "b" * 40, project, DATABASE)
        addresses = {database: ips["database"], frontend: ips["frontend"],
                     nginx: ips["nginx"], backend: ips["backend"], worker: ips["worker"]}
        port = ActualReopenPort(request, database, nginx, {"backend": backend, "worker": worker},
                                admin, network_id, addresses, scenario)
        try:
            G5Lifecycle().execute(request, port)
        except InjectedFailure:
            phase = port.store.show().phase
            expected = Phase.RECOVERY_REQUIRED if scenario == "precommit" else Phase.COMMITTED_WRITERS_ALLOWED
            if phase is not expected:
                raise StateError("unexpected failure phase")
            if port.reopen_attempted != (scenario != "precommit"):
                raise StateError("unexpected reopen attempt")
            port.verify_drain()
            if port.postcommit_write != (scenario != "precommit"):
                raise StateError("postcommit application write evidence missing")
            if scenario != "precommit" and admin.sql(
                    f"SELECT name FROM worlds WHERE id={inserted};", DATABASE) != "Postcommit CI write":
                raise StateError("confirmed postcommit write was lost")
            if admin.sql(f"SELECT count(*) FROM worlds WHERE id={inserted};", DATABASE) != "1":
                raise StateError("historical committed write missing")
            print(f"{scenario}: expected failure; {phase.value}; barriers remain closed")
            return
        raise StateError("fixture scenario unexpectedly completed")
    finally:
        try:
            cleanup_fixture(project)
        except BaseException:
            print(f"fixture cleanup uncertain; project={project}; workspace={root}",
                  file=sys.stderr)
            raise
        shutil.rmtree(root)


def main():
    if len(sys.argv) != 3:
        print("usage: python -m ops.ci_g5_actual_reopen "
              "{precommit,midreopen,lost-response,incomplete} WORKSPACE", file=sys.stderr)
        return 2
    run_case(sys.argv[1], sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
