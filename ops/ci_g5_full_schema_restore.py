"""GitHub-CI-only, disposable PG15 full-schema rollback laboratory (#205).

No production adapter, database replacement, writer reopening or RPO claim.
The only permitted destructive scope is public in a newly owned fixture.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from ops.g5_pg15_writer_fence import Pg15FenceTarget, Pg15PersistentFence


ROOT = Path(__file__).resolve().parents[1]
DB = "g5_full_schema"
APP = "game_app"
PASSWORD = "synthetic-g5-fixture-only"
PREVIOUS = "0019_privacy_active_unique"
CANDIDATE = "0020_wonder_funding"
SCENARIOS = ("rollback", "restore-failure", "tampered", "drift", "dependency")


class RehearsalError(RuntimeError):
    """Evidence is missing; the fixture must remain fenced."""


def require(condition, message):
    if not condition:
        raise RehearsalError(message)


def command(args, *, input=None, check=True, timeout=90):
    result = subprocess.run(args, input=input, capture_output=True, timeout=timeout,
                            check=False)
    if check:
        require(result.returncode == 0, "isolated command failed")
    return result


def docker(args, **kwargs):
    # Never inherit a remote Docker context/host, TLS configuration or SSH path.
    return command(["docker", "--host", "unix:///var/run/docker.sock", *args], **kwargs)


def canonical_schema(payload: bytes) -> tuple[str, ...]:
    """Compare every pg_dump schema TOC block, ignoring ordering and banners.

    Ownership, ACL, constraints, indexes, defaults, types, functions and schema
    objects remain intact. OIDs and random psql restrict tokens are not identity.
    """
    text = payload.decode("utf-8")
    # Only discard the generated outer trailer, never lines within SQL bodies
    # (comments/defaults/functions can contain blank or "--"-prefixed literals).
    text = text.rsplit("\n--\n-- PostgreSQL database dump complete\n--", 1)[0]
    blocks = re.split(r"(?m)^--\n-- Name: ", text)
    return tuple(sorted(block.strip("\n") for block in blocks[1:]))


@dataclass(frozen=True)
class Snapshot:
    path: Path
    sha256: str
    device: int
    inode: int
    size: int

    @classmethod
    def capture(cls, path, payload):
        require(payload.startswith(b"PGDMP"), "snapshot is not a custom archive")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            info = os.fstat(stream.fileno())
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return cls(path, hashlib.sha256(payload).hexdigest(), info.st_dev,
                   info.st_ino, info.st_size)

    def open_verified(self):
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            self.read_verified(fd)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def read_verified(self, fd):
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid()
                and (info.st_dev, info.st_ino, info.st_size) ==
                (self.device, self.inode, self.size), "snapshot identity changed")
        os.lseek(fd, 0, os.SEEK_SET)
        with os.fdopen(os.dup(fd), "rb") as stream:
            payload = stream.read()
        require(hashlib.sha256(payload).hexdigest() == self.sha256,
                "snapshot checksum changed")
        return payload


class Admin:
    def __init__(self, container):
        self.container = container

    def sql(self, sql, database=DB, *, check=True):
        return docker(["exec", self.container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                       "-U", "postgres", "-d", database, "-Atqc", sql], check=check)

    def scalar(self, sql, database=DB):
        return self.sql(sql, database).stdout.decode().strip()

    def query_fresh(self, sql):
        return self.scalar(sql, "postgres")

    def execute_committed(self, sql):
        self.sql(sql, "postgres")


class Fixture:
    def __init__(self, image):
        self.name = "bm-g5-full-" + uuid4().hex
        self.network = self.name + "-net"
        self.executor = self.name + "-alembic"
        self.label = "bm.g5.full-schema=" + self.name
        self.image = image
        self.admin = Admin(self.name)
        self.identity = None
        self.rejected = False
        self.resources = []

    def start(self):
        self.resources.append(("network", self.network))
        docker(["network", "create", "--internal", "--label", self.label, self.network])
        self.resources.append(("container", self.name))
        docker(["run", "--detach", "--label", self.label, "--name", self.name,
                "--network", self.network,
                "-e", "POSTGRES_PASSWORD=" + PASSWORD, "postgres:15-alpine"])
        for _ in range(100):
            ready = self.admin.sql("SHOW listen_addresses;", "postgres", check=False)
            if ready.returncode == 0 and ready.stdout.strip() == b"*":
                break
            time.sleep(0.2)
        else:
            raise RehearsalError("PG15 final postmaster unavailable")
        self.admin.sql(f"CREATE ROLE {APP} LOGIN PASSWORD '{PASSWORD}';", "postgres")
        self.admin.sql("CREATE ROLE fixture_owner NOLOGIN;", "postgres")
        self.admin.sql(f"CREATE DATABASE {DB};", "postgres")
        self.identity = self.database_identity()
        require(self.admin.scalar("SHOW server_version_num;")[:2] == "15",
                "fixture must use PG15")

    def database_identity(self):
        return self.admin.scalar(
            f"SELECT oid||':'||datname||':'||datdba FROM pg_database WHERE datname='{DB}';",
            "postgres")

    def migrate(self, revision):
        self.resources.append(("container", self.executor))
        result = docker([
            "run", "--label", self.label, "--name", self.executor,
            "--network", "container:" + self.name,
            "-e", "APP_ENV=test", "-e",
            f"DATABASE_URL=postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1:5432/{DB}",
            self.image, "alembic", "-c", "alembic.ini", "upgrade", revision,
        ], timeout=180, check=False)
        require(docker(["inspect", "--format", "{{.State.Running}}",
                        self.executor]).stdout.strip() == b"false",
                "migration executor still running")
        require(result.returncode == 0, "real Alembic migration failed")
        docker(["rm", self.executor])
        self.resources.remove(("container", self.executor))
        require(self.admin.scalar("SELECT version_num FROM alembic_version;") == revision,
                "Alembic ledger mismatch")

    def app(self, sql):
        return docker(["exec", "-e", "PGPASSWORD=" + PASSWORD, self.name,
                       "psql", "-X", "-w", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1",
                       "-U", APP, "-d", DB, "-Atqc", sql], check=False)

    def seed(self):
        self.admin.sql(
            "INSERT INTO worlds(name,lifecycle_status,lifecycle_changed_at,is_active) "
            "VALUES ('seed-world','open',CURRENT_TIMESTAMP,true);"
            "INSERT INTO alliances(name,world_id) SELECT 'seed-alliance',id FROM worlds;"
            "ALTER TABLE alliances OWNER TO fixture_owner;"
            f"GRANT USAGE ON SCHEMA public TO {APP};"
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {APP};"
            f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP};"
            f"GRANT UPDATE(name) ON worlds TO {APP};")
        result = self.app("UPDATE worlds SET name='app-confirmed' RETURNING name;")
        require(result.returncode == 0 and b"app-confirmed" in result.stdout,
                "application positive write control failed")
        require(self.admin.scalar("SELECT name FROM worlds;") == "app-confirmed",
                "app write not committed")
        docker(["exec", "--detach", "-e", "PGPASSWORD=" + PASSWORD, self.name,
                "psql", "-X", "-h", "127.0.0.1", "-U", APP, "-d", DB,
                "-Atqc", "SELECT pg_sleep(120);"])
        for _ in range(50):
            if self.admin.scalar(
                f"SELECT count(*) FROM pg_stat_activity WHERE datname='{DB}' "
                f"AND usename='{APP}';", "postgres") == "1":
                return
            time.sleep(0.1)
        raise RehearsalError("pre-fence app session missing")

    def fence(self):
        return Pg15PersistentFence(Pg15FenceTarget(DB, APP, "postgres"), self.admin)

    def closed(self):
        # Fresh adapter observes durable state, not a remembered Python flag.
        require(self.database_identity() == self.identity, "database identity drift")
        self.fence().assert_closed()
        result = self.app("SELECT 1;")
        require(result.returncode != 0 and re.search(
            rb"FATAL:.*(?:not permitted to log in|too many connections for database)",
            result.stderr), "app login not explicitly refused")
        self.fence().assert_closed()

    def dump(self, *options):
        return docker(["exec", self.name, "pg_dump", "-U", "postgres", "-d", DB,
                       *options]).stdout

    def inventory(self):
        """All table rows (including ledger) and sequence state, without OIDs."""
        tables = json.loads(self.admin.scalar(
            "SELECT coalesce(json_agg(c.relname ORDER BY c.relname),'[]') "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind IN ('r','p');"))
        sequences = json.loads(self.admin.scalar(
            "SELECT coalesce(json_agg(c.relname ORDER BY c.relname),'[]') "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='S';"))
        quote = lambda name: '"' + name.replace('"', '""') + '"'
        rows = {name: self.admin.scalar(
            f"SELECT coalesce(jsonb_agg(j ORDER BY j::text),'[]') FROM "
            f"(SELECT to_jsonb(t) AS j FROM public.{quote(name)} t) s;")
                for name in tables}
        state = {name: self.admin.scalar(
            f"SELECT last_value||':'||is_called FROM public.{quote(name)};")
                 for name in sequences}
        schema = canonical_schema(self.dump("--schema-only"))
        require(schema, "empty catalog evidence")
        database = self.admin.scalar(
            "SELECT jsonb_build_object('owner',pg_get_userbyid(datdba),'acl',datacl,"
            "'encoding',encoding,'collate',datcollate,'ctype',datctype,"
            "'connection_limit',datconnlimit,'allow_connections',datallowconn) "
            f"FROM pg_database WHERE datname='{DB}';", "postgres")
        namespace = self.admin.scalar(
            "SELECT jsonb_build_object('owner',pg_get_userbyid(nspowner),'acl',nspacl) "
            "FROM pg_namespace WHERE nspname='public';")
        return {"catalog": schema, "rows": rows, "sequences": state,
                "database": database, "namespace": namespace}

    def scope(self):
        # Unknown namespaces are refused, never cascaded away. pg_depend also
        # catches external dependents (e.g. rewrite rules of a foreign view).
        require(self.admin.scalar(
            "SELECT count(*) FROM pg_namespace WHERE nspname NOT IN "
            "('public','pg_catalog','information_schema','pg_toast');"
        ) == "0", "object outside fixture scope")
        require(self.admin.scalar(
            "SELECT count(*) FROM pg_depend d "
            "CROSS JOIN LATERAL pg_identify_object(d.classid,d.objid,d.objsubid) obj "
            "CROSS JOIN LATERAL pg_identify_object(d.refclassid,d.refobjid,d.refobjsubid) ref "
            "WHERE ref.schema='public' AND obj.schema IS NOT NULL "
            "AND obj.schema NOT IN ('public','pg_toast');"
        ) == "0", "dependency outside fixture scope")

    def reject_candidate(self):
        result = self.admin.sql("SELECT 1/0;", check=False)
        require(result.returncode == 1 and b"division by zero" in result.stderr,
                "known rejection not confirmed")
        self.closed()  # SQL executor returned, migration container gone, no sessions.
        self.rejected = True

    def restore(self, receipt, fd, candidate, *, fail=False):
        self.closed()
        require(self.rejected, "no confirmed candidate rejection")
        require(not any(kind == "container" and name == self.executor
                        for kind, name in self.resources), "executor not stopped")
        payload = receipt.read_verified(fd)
        self.scope()
        require(self.inventory() == candidate, "candidate catalog/data drift")
        self.closed()
        # Convert the verified custom archive to SQL without opening its path.
        sql = docker(["exec", "-i", self.name, "pg_restore", "--exit-on-error", "--file=-"],
                     input=payload).stdout
        require(b"CREATE DATABASE" not in sql and b"\\connect" not in sql,
                "archive may not replace database")
        # Pause AFTER destructive DDL inside the same transaction; independently
        # observe persistent login rejection while the restore is actually active.
        # PG15 omits CREATE SCHEMA for the initdb-owned public namespace.
        bootstrap = (b"" if re.search(rb"(?m)^CREATE SCHEMA public;", sql) else
                     b"CREATE SCHEMA public AUTHORIZATION pg_database_owner;\n"
                     b"GRANT USAGE ON SCHEMA public TO PUBLIC;\n")
        transaction = (b"BEGIN;\nDROP SCHEMA public CASCADE;\n" + bootstrap +
                       b"SELECT pg_sleep(2);\n" + sql
                       + (b"\nSELECT 1/0;\n" if fail else b"\n")
                       + b"COMMIT;\n")
        with tempfile.TemporaryFile() as stream:
            stream.write(transaction)
            stream.seek(0)
            process = subprocess.Popen(
                ["docker", "--host", "unix:///var/run/docker.sock", "exec", "-i",
                 "-e", "PGAPPNAME=g5_restore", self.name, "psql", "-X",
                 "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DB],
                stdin=stream, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    if self.admin.scalar(
                        f"SELECT count(*) FROM pg_stat_activity WHERE datname='{DB}' "
                        "AND application_name='g5_restore' AND wait_event='PgSleep';",
                        "postgres") == "1":
                        break
                    require(process.poll() is None, "restore exited before active probe")
                    time.sleep(0.02)
                else:
                    raise RehearsalError("restore active probe unavailable")
                result = self.app("SELECT 1;")
                require(result.returncode != 0 and re.search(
                    rb"FATAL:.*(?:not permitted to log in|too many connections for database)",
                    result.stderr), "app connected during restore")
                require(self.admin.scalar(
                    f"SELECT datconnlimit FROM pg_database WHERE datname='{DB}';",
                    "postgres") == "0", "database barrier changed during restore")
                _, stderr = process.communicate(timeout=120)
                if fail:
                    require(process.returncode == 3 and b"division by zero" in stderr,
                            "restore failure not positively established")
                else:
                    require(process.returncode == 0, "full schema restore failed")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        self.closed()

    def cleanup(self):
        failures = []
        for kind, name in reversed(self.resources):
            # Reconcile a failed create/start (including lost acknowledgement).
            listing = docker(
                ["ps", "--all", "--filter", "label=" + self.label,
                 "--format", "{{.Names}}"] if kind == "container" else
                ["network", "ls", "--filter", "label=" + self.label,
                 "--format", "{{.Name}}"], check=False)
            if listing.returncode != 0:
                failures.append(kind)
                continue
            if name not in listing.stdout.decode().splitlines():
                continue
            # Official PG image creates an anonymous data volume: remove it too.
            args = ["rm", "--force", "--volumes", name] if kind == "container" else [
                "network", "rm", name]
            if docker(args, check=False).returncode != 0:
                failures.append(kind)
        self.resources.clear()
        require(not failures, "fixture cleanup failed")


def rehearse(image, scenario):
    fixture = Fixture(image)
    try:
        fixture.start()
        fixture.migrate(PREVIOUS)
        fixture.seed()
        fixture.fence().engage()
        fixture.closed()
        fixture.scope()
        baseline = fixture.inventory()
        with tempfile.TemporaryDirectory(prefix="bm-g5-full-") as directory:
            receipt = Snapshot.capture(Path(directory) / "previous.dump",
                                       fixture.dump("--format=custom"))
            fd = receipt.open_verified()
            try:
                docker(["exec", "-i", fixture.name, "pg_restore", "--list"],
                       input=receipt.read_verified(fd))
                fixture.closed()
                require(fixture.inventory() == baseline, "snapshot/drain drift")
                fixture.migrate(CANDIDATE)
                require(fixture.admin.scalar(
                    "SELECT to_regclass('public.wonder_funding') IS NOT NULL "
                    "AND to_regclass('public.wonder_contributions') IS NOT NULL "
                    "AND EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='worlds' AND column_name='wonder_rules_version');"
                ) == "t", "0020 objects missing")
                fixture.admin.sql(
                    "UPDATE worlds SET name='candidate-committed',"
                    "wonder_rules_version='funded-v2';")
                require(fixture.admin.scalar("SELECT name FROM worlds;") ==
                        "candidate-committed", "candidate mutation not committed")
                candidate = fixture.inventory()
                require(candidate != baseline, "candidate has no observable mutation")
                fixture.reject_candidate()
                if scenario == "tampered":
                    with receipt.path.open("r+b") as stream:
                        stream.seek(-1, os.SEEK_END)
                        stream.write(b"X")
                elif scenario == "drift":
                    fixture.admin.sql("UPDATE worlds SET name='unexpected-drift';")
                elif scenario == "dependency":
                    fixture.admin.sql(
                        "CREATE SCHEMA outside_guard;"
                        "CREATE VIEW outside_guard.dependent AS SELECT * FROM worlds;")
                before_attempt = fixture.inventory()
                if scenario in ("tampered", "drift", "dependency"):
                    try:
                        fixture.restore(receipt, fd, candidate)
                    except RehearsalError as error:
                        expected = {"tampered": "snapshot checksum changed",
                                    "drift": "candidate catalog/data drift",
                                    "dependency": "object outside fixture scope"}[scenario]
                        require(str(error) == expected, "unclassified adversarial failure")
                    else:
                        raise RehearsalError("unsafe restore was accepted")
                    require(fixture.inventory() == before_attempt,
                            "rejected restore modified fixture")
                    if scenario == "dependency":
                        require(fixture.admin.scalar(
                            "SELECT name FROM outside_guard.dependent;") ==
                            "candidate-committed", "outside dependency was deleted")
                else:
                    failed = scenario == "restore-failure"
                    fixture.restore(receipt, fd, candidate, fail=failed)
                    expected = candidate if failed else baseline
                    restored = fixture.inventory()
                    for category in expected:
                        require(restored[category] == expected[category],
                                f"restored {category} not equivalent")
                    if not failed:
                        require(fixture.admin.scalar(
                            "SELECT to_regclass('public.wonder_funding') IS NULL "
                            "AND to_regclass('public.wonder_contributions') IS NULL;"
                        ) == "t", "candidate-only objects survived restore")
                fixture.closed()
                return {"scenario": scenario, "result": "passed", "postgres": 15,
                        "previous": PREVIOUS, "candidate": CANDIDATE,
                        "snapshot_sha256": receipt.sha256,
                        "catalog_blocks": len(baseline["catalog"]),
                        "tables": len(baseline["rows"]),
                        "sequences": len(baseline["sequences"]),
                        "same_database": True, "app_barrier_closed": True}
            finally:
                os.close(fd)
    finally:
        fixture.cleanup()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=(*SCENARIOS, "all"), default="all")
    args = parser.parse_args(argv)
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
        print("full-schema restore refused outside GitHub Actions CI", file=sys.stderr)
        return 2
    try:
        sha = command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.decode().strip()
        image = "bm-g5-full-schema-head:" + sha
        # Only a locally built HEAD image; never accept an arbitrary registry image.
        if docker(["image", "inspect", image], check=False).returncode != 0:
            docker(["build", "--tag", image, str(ROOT / "batalla_medieval_backend")],
                   timeout=900)
        for scenario in SCENARIOS if args.scenario == "all" else (args.scenario,):
            evidence = rehearse(image, scenario)
            evidence.update(head=sha, cleanup="containers, anonymous volumes, network, snapshot removed")
            print(json.dumps(evidence, sort_keys=True), flush=True)
        return 0
    except RehearsalError as error:
        print(f"full-schema rehearsal failed closed: {error}", file=sys.stderr)
        return 1
    except (subprocess.TimeoutExpired, OSError):
        print("full-schema rehearsal failed closed; no release authorization", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
