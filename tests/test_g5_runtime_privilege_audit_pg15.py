"""Opt-in disposable, networkless PostgreSQL 15 privilege and lock probes."""
import os
import json
import re
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import pytest

from ops.g5_pg15_writer_fence import Pg15FenceTarget
from ops.g5_runtime_privilege_audit import RelationRule, inspect_runtime_privileges


LABEL = "medievol.g5.privilege-audit"
SOCKET = "unix:///var/run/docker.sock"


def _guard():
    if any(os.environ.get(key) != value for key, value in (
        ("GITHUB_ACTIONS", "true"), ("CI", "true"),
        ("RUNNER_ENVIRONMENT", "github-hosted"),
        ("G5_PRIVILEGE_AUDIT_PG15", "1"),
    )):
        raise RuntimeError("disposable PG15 fixture requires an opted-in GitHub-hosted CI runner")


def _docker(config, *args, check=True):
    _guard()
    env = {key: value for key, value in os.environ.items() if not key.startswith("DOCKER_")}
    env["DOCKER_CONFIG"] = config
    try:
        result = subprocess.run(
            ["docker", "--host", SOCKET, *args], env=env, check=False,
            text=True, capture_output=True, timeout=45,
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("isolated Docker command unavailable or timed out") from None
    if result.returncode:
        if check:
            raise RuntimeError("isolated Docker command failed")
        category = "permission denied" if "permission denied" in result.stderr.lower() else ""
        return subprocess.CompletedProcess([], result.returncode, "", category)
    return result


def _verify_owner(config, container_id, owner):
    if (not re.fullmatch(r"[0-9a-f]{64}", container_id)
            or not re.fullmatch(r"g5-privilege-audit-[0-9a-f]{32}", owner)):
        raise RuntimeError("invalid isolated fixture identity")
    response = _docker(config, "inspect", "--type", "container", container_id)
    try:
        inspected = json.loads(response.stdout)
        if (not isinstance(inspected, list) or len(inspected) != 1
                or inspected[0]["Id"] != container_id
                or inspected[0]["Config"]["Labels"][LABEL] != owner):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("isolated fixture ownership unverified") from None


def _cleanup(config, container_id, owner):
    _verify_owner(config, container_id, owner)
    _docker(config, "rm", "--force", "--volumes", container_id)


def _hosted(monkeypatch):
    for key, value in (("GITHUB_ACTIONS", "true"), ("CI", "true"),
                       ("RUNNER_ENVIRONMENT", "github-hosted"), ("G5_PRIVILEGE_AUDIT_PG15", "1")):
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("key,value", [
    ("GITHUB_ACTIONS", "false"), ("CI", "false"),
    ("RUNNER_ENVIRONMENT", "self-hosted"), ("G5_PRIVILEGE_AUDIT_PG15", "0"),
])
def test_guard_rejects_non_hosted_or_not_opted_in(monkeypatch, key, value):
    _hosted(monkeypatch)
    monkeypatch.setenv(key, value)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("Docker must not run"))
    with pytest.raises(RuntimeError, match="GitHub-hosted"):
        _docker("/tmp/config", "ps")


def test_docker_uses_local_socket_clean_environment_and_timeout(monkeypatch):
    _hosted(monkeypatch)
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        monkeypatch.setenv(key, "untrusted-value")
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", run)
    _docker("/tmp/config", "ps")
    args, kwargs = calls[0]
    assert args == ["docker", "--host", SOCKET, "ps"]
    assert kwargs["timeout"] == 45 and kwargs["env"]["DOCKER_CONFIG"] == "/tmp/config"
    assert set(k for k in kwargs["env"] if k.startswith("DOCKER_")) == {"DOCKER_CONFIG"}


@pytest.mark.parametrize("failure", [
    subprocess.TimeoutExpired(["secret"], 45, output="secret"),
    OSError("secret"),
])
def test_docker_failure_is_sanitized(monkeypatch, failure):
    _hosted(monkeypatch)
    def run(*args, **kwargs):
        raise failure
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError) as error:
        _docker("/tmp/config", "ps")
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("inspection", [
    "not-json", "[]", '[{}]',
    json.dumps([{"Id": "b" * 64, "Config": {"Labels": {LABEL: "g5-privilege-audit-" + "c" * 32}}}]),
    json.dumps([{"Id": "a" * 64, "Config": {"Labels": {LABEL: "g5-privilege-audit-" + "c" * 32 + "extra"}}}]),
])
def test_cleanup_refuses_unowned_or_ambiguous_containers(monkeypatch, inspection):
    calls = []
    def docker(config, *args):
        calls.append(args)
        return subprocess.CompletedProcess([], 0, inspection, "")
    monkeypatch.setattr(sys.modules[__name__], "_docker", docker)
    with pytest.raises(RuntimeError, match="ownership"):
        _cleanup("/tmp/config", "a" * 64, "g5-privilege-audit-" + "c" * 32)
    assert len(calls) == 1 and calls[0][0] == "inspect"


def test_cleanup_requires_exact_id_and_label_before_removal(monkeypatch):
    owner, identity = "g5-privilege-audit-" + "c" * 32, "a" * 64
    calls = []
    def docker(config, *args):
        calls.append(args)
        data = [{"Id": identity, "Config": {"Labels": {LABEL: owner}}}]
        return subprocess.CompletedProcess([], 0, json.dumps(data), "")
    monkeypatch.setattr(sys.modules[__name__], "_docker", docker)
    _cleanup("/tmp/config", identity, owner)
    assert calls == [("inspect", "--type", "container", identity),
                     ("rm", "--force", "--volumes", identity)]
    with pytest.raises(RuntimeError, match="identity"):
        _cleanup("/tmp/config", "bad", owner)
    assert len(calls) == 2


def test_fixture_cleans_owned_container_when_start_fails(monkeypatch):
    _hosted(monkeypatch)
    identity = "a" * 64
    calls = []

    def docker(config, *args, **kwargs):
        calls.append(args)
        if args[0] == "create":
            return subprocess.CompletedProcess([], 0, identity, "")
        if args[0] == "start":
            raise RuntimeError("start failed")
        if args[0] == "inspect":
            label = next(arg for arg in calls[0] if arg.startswith(LABEL + "=")).split("=", 1)[1]
            return subprocess.CompletedProcess([], 0, json.dumps(
                [{"Id": identity, "Config": {"Labels": {LABEL: label}}}]), "")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(sys.modules[__name__], "_docker", docker)
    with pytest.raises(RuntimeError, match="start failed"):
        next(pg.__wrapped__())
    assert calls[-2:] == [("inspect", "--type", "container", identity),
                          ("rm", "--force", "--volumes", identity)]


@pytest.fixture(scope="module")
def pg():
    if os.environ.get("G5_PRIVILEGE_AUDIT_PG15") != "1":
        pytest.skip("requires opt-in disposable GitHub-hosted PG15 fixture")
    _guard()
    name = "g5-privilege-audit-" + uuid4().hex
    with tempfile.TemporaryDirectory(prefix="g5-privilege-docker-") as config:
        container_id = None
        try:
            container_id = _docker(
                config, "create", "--pull", "never", "--name", name, "--network", "none",
                "--label", LABEL + "=" + name, "-e", "POSTGRES_PASSWORD=synthetic-fixture",
                "postgres:15-alpine",
            ).stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{64}", container_id):
                raise RuntimeError("invalid isolated fixture container id")

            _verify_owner(config, container_id, name)

            def docker(*args, check=True):
                return _docker(config, *args, check=check)

            def sql(statement, database="game_ci", *, readonly=False, check=True):
                args = ["exec"]
                if readonly:
                    args += ["-e", "PGOPTIONS=-c default_transaction_read_only=on"]
                args += [container_id, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
                         "-d", database, "-Atqc", statement]
                return docker(*args, check=check)

            docker("start", container_id)
            for _ in range(60):
                if docker("exec", container_id, "pg_isready", "-U", "postgres", check=False).returncode == 0:
                    break
                time.sleep(1)
            else:
                pytest.fail("disposable PostgreSQL 15 did not start")
            sql("CREATE ROLE game_app;", "postgres")
            sql("CREATE DATABASE game_ci;", "postgres")
            sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC; "
                "REVOKE TEMP ON DATABASE game_ci FROM PUBLIC; "
                "GRANT USAGE ON SCHEMA public TO game_app; "
                "CREATE TABLE item_templates (id serial PRIMARY KEY, slot text); "
                "CREATE TABLE hero_items (id serial PRIMARY KEY, template_id int REFERENCES item_templates(id)); "
                "INSERT INTO item_templates(slot) VALUES ('weapon'); "
                "INSERT INTO hero_items(template_id) VALUES (1); "
                "GRANT SELECT ON item_templates TO game_app; "
                "GRANT SELECT, UPDATE ON hero_items TO game_app; "
                "GRANT USAGE ON SEQUENCE hero_items_id_seq TO game_app;")
            yield sql
        finally:
            if container_id and re.fullmatch(r"[0-9a-f]{64}", container_id):
                _cleanup(config, container_id, name)


class Reader:
    def __init__(self, sql):
        self.sql = sql

    def query(self, database, statement):
        return self.sql(statement, database, readonly=True).stdout.strip()


def test_effective_grants_and_adversarial_acl(pg):
    target = Pg15FenceTarget("game_ci", "game_app", "postgres")
    rules = (
        RelationRule("item_templates", "table", frozenset({"SELECT"}), frozenset({"UPDATE", "DELETE"})),
        RelationRule("hero_items", "table", frozenset({"SELECT", "UPDATE"}), frozenset({"DELETE"})),
        RelationRule("hero_items_id_seq", "sequence", frozenset({"USAGE"}), frozenset({"UPDATE"})),
    )
    observe = lambda: inspect_runtime_privileges(target, Reader(pg), rules).blockers
    assert observe() == ()
    try:
        pg("GRANT UPDATE (slot) ON item_templates TO PUBLIC;")
        assert "item_templates:unexpected:UPDATE" in observe()
    finally:
        pg("REVOKE UPDATE (slot) ON item_templates FROM PUBLIC;")
    try:
        pg("GRANT SELECT ON item_templates TO game_app WITH GRANT OPTION; "
           "GRANT UPDATE (slot) ON item_templates TO game_app WITH GRANT OPTION; "
           "GRANT USAGE ON SEQUENCE hero_items_id_seq TO game_app WITH GRANT OPTION; "
           "GRANT USAGE ON SCHEMA public TO game_app WITH GRANT OPTION; "
           "GRANT CONNECT ON DATABASE game_ci TO game_app WITH GRANT OPTION;")
        assert {"item_templates:grant_option", "hero_items_id_seq:grant_option",
                "schema_grant_option", "database_grant_option"} <= set(observe())
    finally:
        pg("REVOKE GRANT OPTION FOR SELECT, UPDATE ON item_templates FROM game_app; "
           "REVOKE GRANT OPTION FOR UPDATE (slot) ON item_templates FROM game_app; "
           "REVOKE GRANT OPTION FOR USAGE ON SEQUENCE hero_items_id_seq FROM game_app; "
           "REVOKE GRANT OPTION FOR USAGE ON SCHEMA public FROM game_app; "
           "REVOKE GRANT OPTION FOR CONNECT ON DATABASE game_ci FROM game_app;")
    try:
        pg("GRANT UPDATE (slot) ON item_templates TO game_app WITH GRANT OPTION;")
        assert "item_templates:grant_option" in observe()
    finally:
        pg("REVOKE UPDATE (slot) ON item_templates FROM game_app;")
    try:
        pg("CREATE ROLE inherited_writer; GRANT inherited_writer TO game_app; "
           "GRANT DELETE ON hero_items TO inherited_writer;")
        assert "hero_items:unexpected:DELETE" in observe()
        assert "role_membership" in observe()
    finally:
        pg("REVOKE inherited_writer FROM game_app; DROP OWNED BY inherited_writer; DROP ROLE inherited_writer;")
    try:
        pg("CREATE ROLE owner_writer; GRANT owner_writer TO game_app; ALTER ROLE game_app NOINHERIT; "
           "GRANT DELETE ON hero_items TO owner_writer WITH GRANT OPTION; ALTER TABLE item_templates OWNER TO owner_writer; "
           "REVOKE ALL ON item_templates FROM owner_writer;")
        blockers = observe()
        assert "role_membership" in blockers
        assert "item_templates:owner" in blockers
        assert "hero_items:unexpected:DELETE" not in blockers
        assert "hero_items:grant_option" in blockers
        assert pg("SET ROLE game_app; SET ROLE owner_writer; DELETE FROM hero_items WHERE false;").returncode == 0
    finally:
        pg("ALTER TABLE item_templates OWNER TO postgres; GRANT SELECT ON item_templates TO game_app; "
           "ALTER ROLE game_app INHERIT; REVOKE owner_writer FROM game_app; "
           "DROP OWNED BY owner_writer; DROP ROLE owner_writer;")
    try:
        pg("GRANT CREATE ON SCHEMA public TO PUBLIC; GRANT TEMP ON DATABASE game_ci TO PUBLIC;")
        assert {"schema_create", "database_temp"} <= set(observe())
    finally:
        pg("REVOKE CREATE ON SCHEMA public FROM PUBLIC; REVOKE TEMP ON DATABASE game_ci FROM PUBLIC;")
    try:
        pg("REVOKE USAGE ON SEQUENCE hero_items_id_seq FROM game_app;")
        assert "hero_items_id_seq:missing:USAGE" in observe()
    finally:
        pg("GRANT USAGE ON SEQUENCE hero_items_id_seq TO game_app;")
    try:
        pg("ALTER TABLE item_templates OWNER TO game_app; REVOKE UPDATE ON item_templates FROM game_app;")
        assert "item_templates:owner" in observe()
    finally:
        pg("ALTER TABLE item_templates OWNER TO postgres; GRANT SELECT ON item_templates TO game_app;")
    try:
        pg("ALTER SCHEMA public OWNER TO game_app;")
        assert "schema_owner" in observe()
    finally:
        pg("ALTER SCHEMA public OWNER TO pg_database_owner;")
    try:
        pg("ALTER DATABASE game_ci OWNER TO game_app;", "postgres")
        assert "database_owner" in observe()
    finally:
        pg("ALTER DATABASE game_ci OWNER TO postgres;", "postgres")
    try:
        pg("REVOKE UPDATE ON hero_items FROM game_app; GRANT UPDATE (template_id) ON hero_items TO game_app;")
        assert "hero_items:missing:UPDATE" in observe()
        forbidden = (RelationRule("hero_items", "table", frozenset({"SELECT"}), frozenset({"UPDATE"})),)
        assert "hero_items:unexpected:UPDATE" in inspect_runtime_privileges(target, Reader(pg), forbidden).blockers
    finally:
        pg("REVOKE UPDATE (template_id) ON hero_items FROM game_app; GRANT UPDATE ON hero_items TO game_app;")
    assert observe() == ()

    missing = (RelationRule("not_present", "table", frozenset(), frozenset({"SELECT"})),)
    assert "not_present:exists" in inspect_runtime_privileges(target, Reader(pg), missing).blockers

    class WritableReader:
        def query(self, database, statement):
            return pg(statement, database).stdout.strip()

    assert "context" in inspect_runtime_privileges(target, WritableReader(), rules).blockers


def test_joined_row_lock_and_narrow_lock_target(pg):
    joined = ("SELECT h.id FROM hero_items h JOIN item_templates t ON t.id=h.template_id "
              "FOR UPDATE")
    failed = pg("SET ROLE game_app; " + joined + ";", check=False)
    assert failed.returncode != 0 and failed.stderr == "permission denied"
    assert pg("SET ROLE game_app; " + joined + " OF h;").stdout.strip() == "1"
    try:
        pg("GRANT UPDATE ON item_templates TO game_app;")
        assert pg("SET ROLE game_app; " + joined + ";").stdout.strip() == "1"
    finally:
        pg("REVOKE UPDATE ON item_templates FROM game_app;")


def test_candidate_wonder_sql_shape_and_missing_sequence_privilege(pg):
    # This synthetic subset exercises SQL privileges, not the application path.
    pg("CREATE TABLE alliances (id int PRIMARY KEY); "
       "CREATE TABLE alliance_members (id int PRIMARY KEY, alliance_id int REFERENCES alliances(id)); "
       "CREATE TABLE cities (id int PRIMARY KEY, wood int); "
       "CREATE TABLE wonder_funding (id serial PRIMARY KEY, funded_wood int); "
       "CREATE TABLE wonder_contributions (id serial PRIMARY KEY, funding_id int REFERENCES wonder_funding(id), wood int); "
       "INSERT INTO alliances VALUES (1); INSERT INTO alliance_members VALUES (1,1); "
       "INSERT INTO cities VALUES (1,100); "
       "GRANT SELECT ON alliances TO game_app; "
       "GRANT SELECT, UPDATE ON alliance_members, cities TO game_app; "
       "GRANT SELECT, INSERT, UPDATE ON wonder_funding TO game_app; "
       "GRANT SELECT, INSERT ON wonder_contributions TO game_app; "
       "GRANT USAGE ON SEQUENCE wonder_funding_id_seq, wonder_contributions_id_seq TO game_app;")
    target = Pg15FenceTarget("game_ci", "game_app", "postgres")
    rules = (
        RelationRule("alliances", "table", frozenset({"SELECT"}), frozenset({"UPDATE"})),
        RelationRule("alliance_members", "table", frozenset({"SELECT", "UPDATE"}), frozenset({"DELETE"})),
        RelationRule("cities", "table", frozenset({"SELECT", "UPDATE"}), frozenset({"DELETE"})),
        RelationRule("wonder_funding", "table", frozenset({"SELECT", "INSERT", "UPDATE"}), frozenset({"DELETE"})),
        RelationRule("wonder_contributions", "table", frozenset({"SELECT", "INSERT"}), frozenset({"UPDATE", "DELETE"})),
        RelationRule("wonder_funding_id_seq", "sequence", frozenset({"USAGE"}), frozenset({"UPDATE"})),
        RelationRule("wonder_contributions_id_seq", "sequence", frozenset({"USAGE"}), frozenset({"UPDATE"})),
    )
    observe = lambda: inspect_runtime_privileges(target, Reader(pg), rules).blockers
    assert observe() == ()
    transaction = (
        "SET ROLE game_app; BEGIN; "
        "SELECT id FROM cities WHERE id=1 FOR UPDATE; "
        "SELECT m.id FROM alliance_members m JOIN alliances a ON a.id=m.alliance_id FOR UPDATE OF m; "
        "INSERT INTO wonder_funding(funded_wood) VALUES (0); "
        "UPDATE cities SET wood=wood-10 WHERE id=1; "
        "UPDATE wonder_funding SET funded_wood=10 WHERE id=currval('wonder_funding_id_seq'); "
        "INSERT INTO wonder_contributions(funding_id,wood) "
        "VALUES (currval('wonder_funding_id_seq'),10); COMMIT;"
    )
    pg("REVOKE USAGE ON SEQUENCE wonder_contributions_id_seq FROM game_app;")
    assert "wonder_contributions_id_seq:missing:USAGE" in observe()
    failed = pg(transaction, check=False)
    assert failed.returncode != 0 and failed.stderr == "permission denied"
    assert pg("SELECT wood FROM cities WHERE id=1;").stdout.strip() == "100"
    assert pg("SELECT count(*) FROM wonder_funding;").stdout.strip() == "0"
    pg("GRANT USAGE ON SEQUENCE wonder_contributions_id_seq TO game_app;")
    assert observe() == ()
    pg(transaction)
    assert pg("SELECT wood FROM cities WHERE id=1;").stdout.strip() == "90"
    assert pg("SELECT count(*) FROM wonder_contributions WHERE wood=10;").stdout.strip() == "1"
