"""Opt-in disposable, networkless PostgreSQL 15 privilege and lock probes."""
import os
import subprocess
import time
from uuid import uuid4

import pytest

from ops.g5_pg15_writer_fence import Pg15FenceTarget
from ops.g5_runtime_privilege_audit import RelationRule, inspect_runtime_privileges


pytestmark = pytest.mark.skipif(
    os.environ.get("G5_PRIVILEGE_AUDIT_PG15") != "1",
    reason="requires opt-in disposable local postgres:15-alpine container",
)


@pytest.fixture(scope="module")
def pg():
    name = "g5-privilege-audit-" + uuid4().hex

    def docker(*args, check=True):
        return subprocess.run(["docker", *args], check=check, text=True, capture_output=True)

    def sql(statement, database="game_ci", *, readonly=False, check=True):
        args = ["exec"]
        if readonly:
            args += ["-e", "PGOPTIONS=-c default_transaction_read_only=on"]
        args += [name, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
                 "-d", database, "-Atqc", statement]
        return docker(*args, check=check)

    try:
        docker("run", "-d", "--name", name, "--network", "none", "--label",
               "medievol.g5.privilege-audit=" + name, "-e", "POSTGRES_PASSWORD=synthetic-fixture",
               "postgres:15-alpine")
        for _ in range(60):
            if docker("exec", name, "pg_isready", "-U", "postgres", check=False).returncode == 0:
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
        docker("rm", "-f", name, check=False)


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
        pg("CREATE ROLE inherited_writer; GRANT inherited_writer TO game_app; "
           "GRANT DELETE ON hero_items TO inherited_writer;")
        assert "hero_items:unexpected:DELETE" in observe()
        assert "role_membership" in observe()
    finally:
        pg("REVOKE inherited_writer FROM game_app; DROP OWNED BY inherited_writer; DROP ROLE inherited_writer;")
    try:
        pg("CREATE ROLE owner_writer; GRANT owner_writer TO game_app; ALTER ROLE game_app NOINHERIT; "
           "GRANT DELETE ON hero_items TO owner_writer; ALTER TABLE item_templates OWNER TO owner_writer; "
           "REVOKE ALL ON item_templates FROM owner_writer;")
        blockers = observe()
        assert "role_membership" in blockers
        assert "item_templates:owner" in blockers
        assert "hero_items:unexpected:DELETE" not in blockers
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
    assert failed.returncode != 0 and "permission denied" in failed.stderr
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
    assert failed.returncode != 0 and "permission denied" in failed.stderr
    assert pg("SELECT wood FROM cities WHERE id=1;").stdout.strip() == "100"
    assert pg("SELECT count(*) FROM wonder_funding;").stdout.strip() == "0"
    pg("GRANT USAGE ON SEQUENCE wonder_contributions_id_seq TO game_app;")
    assert observe() == ()
    pg(transaction)
    assert pg("SELECT wood FROM cities WHERE id=1;").stdout.strip() == "90"
    assert pg("SELECT count(*) FROM wonder_contributions WHERE wood=10;").stdout.strip() == "1"
