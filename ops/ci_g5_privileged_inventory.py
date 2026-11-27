"""GitHub CI-only adversarial PG15 inventory observations, no live adapter."""
from __future__ import annotations

import os
from uuid import uuid4

from ops.ci_g5_edge_admission import cleanup_fixture, run
from ops.ci_g5_integrated_runtime import ready_db, wait_until
from ops.g5_pg15_writer_fence import Pg15FenceTarget, Pg15PersistentFence
from ops.g5_pg15_privileged_inventory import inspect_privileged_inventory


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

    def query(self, database, statement):
        return run(["exec", "-e", "PGOPTIONS=-c default_transaction_read_only=on",
                    self.container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                    "-U", "postgres", "-d", database, "-Atqc", statement]).strip()


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
        return 2
    project = "bm-g5-edge-" + uuid4().hex
    try:
        container = run(["run", "-d", "--network", "none", "--label",
                         "medievol.g5.edge-fixture=" + project,
                         "-e", "POSTGRES_PASSWORD=synthetic-ci-inventory",
                         "postgres:15-alpine", "-c", "max_prepared_transactions=4"]).strip()
        wait_until(lambda: ready_db(container), "isolated inventory DB not ready")
        admin = IsolatedAdmin(container)
        target = Pg15FenceTarget("game_ci", "game_app", "postgres")
        admin.sql("CREATE ROLE game_app LOGIN;")
        admin.sql("CREATE DATABASE game_ci;")
        # Restrict cross-database CONNECT even through PUBLIC defaults.
        admin.sql("REVOKE CONNECT ON DATABASE postgres, template1 FROM PUBLIC;")
        admin.sql("CREATE TABLE evidence (id int PRIMARY KEY);", "game_ci")

        def expect(*blockers, fenced=False):
            observation = inspect_privileged_inventory(target, admin, fenced=fenced)
            if set(observation.blockers) != set(blockers):
                raise RuntimeError("unexpected inventory result: " + ",".join(observation.blockers))

        # Real stock permission-checked pg_settings access is not a
        # privileged catalog mutation. Prove the default explicitly.
        if admin.sql("SELECT has_table_privilege('game_app','pg_catalog.pg_settings','UPDATE');",
                     "game_ci") != "t":
            raise RuntimeError("expected PG15 stock pg_settings UPDATE permission")
        expect()
        for create, remove, blocker, db in (
            ("CREATE ROLE other_admin LOGIN SUPERUSER;", "DROP ROLE other_admin;",
             "dedicated_roles", "postgres"),
            ("CREATE ROLE hidden_owner NOLOGIN;", "DROP ROLE hidden_owner;",
             "dedicated_roles", "postgres"),
            ("GRANT pg_write_all_data TO game_app;", "REVOKE pg_write_all_data FROM game_app;",
             "no_role_membership", "postgres"),
            ("CREATE DATABASE unrelated_ci;", "DROP DATABASE unrelated_ci;",
             "dedicated_databases", "postgres"),
            ("ALTER DATABASE game_ci OWNER TO game_app;", "ALTER DATABASE game_ci OWNER TO postgres;",
             "dedicated_databases", "postgres"),
            ("SELECT pg_create_physical_replication_slot('g5_probe');",
             "SELECT pg_drop_replication_slot('g5_probe');", "no_replication_slots", "postgres"),
            ("CREATE FUNCTION public.privileged_probe() RETURNS integer LANGUAGE SQL SECURITY DEFINER "
             "AS 'SELECT 1';", "DROP FUNCTION public.privileged_probe();",
             "no_custom_security_definers", "game_ci"),
            ("GRANT CONNECT ON DATABASE postgres TO game_app;",
             "REVOKE CONNECT ON DATABASE postgres FROM game_app;",
             "no_other_database_access", "postgres"),
            ("GRANT CONNECT ON DATABASE template1 TO PUBLIC;",
             "REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;",
             "no_other_database_access", "postgres"),
            ("GRANT EXECUTE ON FUNCTION pg_catalog.lo_export(oid,text) TO game_app;",
             "REVOKE EXECUTE ON FUNCTION pg_catalog.lo_export(oid,text) FROM game_app;",
             "no_sensitive_builtin_execute", "game_ci"),
            ("GRANT EXECUTE ON FUNCTION pg_catalog.lo_export(oid,text) TO PUBLIC;",
             "REVOKE EXECUTE ON FUNCTION pg_catalog.lo_export(oid,text) FROM PUBLIC;",
             "no_sensitive_builtin_execute", "postgres"),
            ("GRANT UPDATE ON pg_catalog.pg_settings TO game_app;",
             "REVOKE UPDATE ON pg_catalog.pg_settings FROM game_app;",
             "no_sensitive_catalog_access", "game_ci"),
            ("GRANT UPDATE ON pg_catalog.pg_authid TO game_app;",
             "REVOKE UPDATE ON pg_catalog.pg_authid FROM game_app;",
             "no_sensitive_catalog_access", "game_ci"),
            ("GRANT UPDATE (rolname) ON pg_catalog.pg_authid TO PUBLIC;",
             "REVOKE UPDATE (rolname) ON pg_catalog.pg_authid FROM PUBLIC;",
             "no_sensitive_catalog_access", "postgres"),
            ("GRANT SELECT ON pg_catalog.pg_authid TO game_app;",
             "REVOKE SELECT ON pg_catalog.pg_authid FROM game_app;",
             "no_sensitive_catalog_access", "game_ci"),
            ("GRANT SELECT (rolpassword) ON pg_catalog.pg_authid TO PUBLIC;",
             "REVOKE SELECT (rolpassword) ON pg_catalog.pg_authid FROM PUBLIC;",
             "no_sensitive_catalog_access", "postgres"),
            ("GRANT ALTER SYSTEM ON PARAMETER shared_preload_libraries TO game_app;",
             "REVOKE ALTER SYSTEM ON PARAMETER shared_preload_libraries FROM game_app;",
             "no_parameter_grants", "postgres"),
            ("GRANT ALTER SYSTEM ON PARAMETER shared_preload_libraries TO PUBLIC;",
             "REVOKE ALTER SYSTEM ON PARAMETER shared_preload_libraries FROM PUBLIC;",
             "no_parameter_grants", "postgres"),
            ("GRANT SET ON PARAMETER session_preload_libraries TO game_app;",
             "REVOKE SET ON PARAMETER session_preload_libraries FROM game_app;",
             "no_parameter_grants", "postgres"),
            ("CREATE FUNCTION public.native_probe(integer) RETURNS integer LANGUAGE internal "
             "AS 'int4abs';", "DROP FUNCTION public.native_probe(integer);",
             "no_native_routines", "game_ci"),
            ("CREATE FUNCTION public.maintenance_probe() RETURNS integer LANGUAGE SQL SECURITY DEFINER "
             "AS 'SELECT 1';", "DROP FUNCTION public.maintenance_probe();",
             "no_custom_security_definers", "postgres"),
            ("BEGIN; INSERT INTO evidence VALUES (1); PREPARE TRANSACTION 'g5_probe';",
             "ROLLBACK PREPARED 'g5_probe';", "no_prepared_transactions", "game_ci"),
            ("ALTER ROLE game_app SET session_preload_libraries TO '';",
             "ALTER ROLE game_app RESET session_preload_libraries;", "no_preload_overrides", "postgres"),
        ):
            admin.sql(create, db)
            expect(blocker)
            admin.sql(remove, db)
            expect()

        run(["exec", "-d", container, "psql", "-X", "-U", "postgres",
             "-d", "game_ci", "-Atqc", "SELECT pg_sleep(90);"])
        wait_until(lambda: admin.sql("SELECT count(*) FROM pg_stat_activity WHERE "
                                    "datname='game_ci' AND usename='postgres';") == "1",
                   "second maintenance session not established")
        expect("client_sessions")
        admin.sql("SELECT pg_terminate_backend(pid,5000) FROM pg_stat_activity "
                  "WHERE datname='game_ci' AND usename='postgres';")
        expect()

        # The exact app role may be active before fencing, but must be
        # disconnected by the durable fence.
        run(["exec", "-d", container, "psql", "-X", "-U", "game_app",
             "-d", "game_ci", "-Atqc", "SELECT pg_sleep(90);"])
        wait_until(lambda: admin.sql("SELECT count(*) FROM pg_stat_activity WHERE "
                                    "datname='game_ci' AND usename='game_app';") == "1",
                   "application session not established")
        expect()
        gate = Pg15PersistentFence(target, admin)
        gate.engage()
        expect(fenced=True)
        gate.assert_closed()
        admin.sql("CREATE ROLE rogue_admin NOLOGIN SUPERUSER;")
        expect("dedicated_roles", fenced=True)
        admin.sql("DROP ROLE rogue_admin;")
        expect(fenced=True)
        gate.assert_closed()
        print("PG15 dedicated-cluster privileged inventory: positive and adversarial observations passed")
        return 0
    finally:
        cleanup_fixture(project)


if __name__ == "__main__":
    raise SystemExit(main())
