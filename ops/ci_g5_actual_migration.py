"""GitHub CI-only rehearsal of the actual shipped game migration and seed.

Uses the built backend image, PostgreSQL 15, a private internal Docker
network and synthetic credentials. The application role is fenced before
the real maintenance migration runs and is never reopened in this drill.
No production role provisioning or deployment entrypoint is provided.
"""
from __future__ import annotations

import os
import sys
import time
from uuid import uuid4

from ops.ci_g5_edge_admission import cleanup_fixture, probe, run
from ops.g5_migration_role_identity import validate_split
from ops.g5_pg15_writer_fence import Pg15FenceTarget, Pg15PersistentFence

IMAGE = "medievol-g5-backend:ci"
DATABASE = "game_migration_ci"
APP = "game_app"
ADMIN = "postgres"
APP_PASSWORD = "synthetic-ci-app-password"
ADMIN_PASSWORD = "synthetic-ci-admin-password"
PREVIOUS = "0019_privacy_active_unique"
CANDIDATE = "0020_wonder_funding"


class Admin:
    def __init__(self, container):
        self.container = container

    def sql(self, statement, database="postgres"):
        return run(["exec", self.container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                    "-U", ADMIN, "-d", database, "-Atqc", statement]).strip()

    def query_fresh(self, statement):
        return self.sql(statement)

    def execute_committed(self, statement):
        self.sql(statement)


def app_command(container, statement):
    return ["exec", "-e", "PGPASSWORD=" + APP_PASSWORD, container,
            "psql", "-X", "-w", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1",
            "-U", APP, "-d", DATABASE, "-Atqc", statement]


def grant_fixture_schema(admin):
    # Fixture only, not a deployment provisioning policy. Reapply after
    # migration for newly created tables and their sequences. The runtime
    # role must not control Alembic version metadata or own schema objects.
    admin.sql(
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC; "
        "GRANT USAGE ON SCHEMA public TO game_app; "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO game_app; "
        "REVOKE ALL ON TABLE alembic_version FROM game_app; "
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO game_app;",
        DATABASE,
    )


def expect_refused(container, statement, reason):
    code, _, stderr = probe(app_command(container, statement))
    if code == 0 or reason not in stderr:
        raise RuntimeError("expected explicit PostgreSQL refusal was not established")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
        print("actual G5 migration rehearsal is GitHub CI only", file=sys.stderr)
        return 2

    project = "bm-g5-edge-" + uuid4().hex
    label = "medievol.g5.edge-fixture=" + project
    app_url = f"postgresql+psycopg://{APP}:{APP_PASSWORD}@database:5432/{DATABASE}"
    migration_url = f"postgresql+psycopg://{ADMIN}:{ADMIN_PASSWORD}@database:5432/{DATABASE}"
    split = validate_split({
        "POSTGRES_DB": DATABASE, "POSTGRES_USER": ADMIN,
        "POSTGRES_PASSWORD": ADMIN_PASSWORD, "DB_URL": app_url,
        "G5_MIGRATION_DB_URL": migration_url,
    })
    if (split.application, split.maintenance, split.database) != (APP, ADMIN, DATABASE):
        raise RuntimeError("wrong role split")

    def backend(*args):
        # Always use the maintenance URL for the actual one-shot commands.
        # No app server or scheduler is started.
        return run(["run", "--rm", "--network", project, "--label", label,
                    "-e", "APP_ENV=test", "-e", "DATABASE_URL=" + migration_url,
                    IMAGE, *args])

    try:
        run(["network", "create", "--internal", "--label", label, project])
        container = run(["run", "-d", "--network", project, "--network-alias", "database",
                         "--label", label, "-e", "POSTGRES_PASSWORD=" + ADMIN_PASSWORD,
                         "postgres:15-alpine"]).strip()
        admin = Admin(container)
        for _ in range(80):
            code, output, _ = probe(["exec", container, "psql", "-X", "-U", ADMIN,
                                     "-d", "postgres", "-Atqc", "SHOW listen_addresses;"])
            if code == 0 and output.strip() == "*":
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("isolated final PostgreSQL server not ready")

        admin.execute_committed(f"CREATE ROLE {APP} LOGIN PASSWORD '{APP_PASSWORD}';")
        admin.execute_committed(f"CREATE DATABASE {DATABASE};")
        backend("alembic", "-c", "/app/alembic.ini", "upgrade", PREVIOUS)
        if admin.sql("SELECT version_num FROM alembic_version;", DATABASE) != PREVIOUS:
            raise RuntimeError("historical schema not established")
        grant_fixture_schema(admin)

        # The app can make a real committed write on the historical schema,
        # including use of the sequence, but cannot manipulate the schema or
        # migration ledger. This is a positive control before the fence.
        world_id = run(app_command(container, """
            INSERT INTO worlds(name, speed_modifier, resource_modifier, map_size,
                special_rules, created_at, is_active, lifecycle_status, lifecycle_changed_at)
            VALUES ('Historical CI world', 1, 1, 100, '', now(), true, 'open', now())
            RETURNING id;
        """)).strip()
        if not world_id.isdecimal():
            raise RuntimeError("historical app write did not return a world")
        expect_refused(container, "UPDATE alembic_version SET version_num='bad';", "permission denied")
        expect_refused(container, "CREATE TABLE public.forbidden_ci (id int);", "permission denied")
        expect_refused(container, "ALTER TABLE worlds ADD COLUMN forbidden_ci int;", "must be owner")

        gate = Pg15PersistentFence(Pg15FenceTarget(DATABASE, APP, ADMIN), admin)
        gate.engage()
        gate.assert_closed()
        expect_refused(container, "UPDATE worlds SET name='unexpected';", "not permitted to log in")

        # Real candidate image runs Alembic and canonical seed while the
        # runtime identity remains blocked. A failed migration fails CI.
        backend("alembic", "-c", "/app/alembic.ini", "upgrade", "head")
        gate.assert_closed()
        if admin.sql("SELECT version_num FROM alembic_version;", DATABASE) != CANDIDATE:
            raise RuntimeError("unexpected actual migration head; update explicit fixture baseline")
        backend("python", "-m", "app.seed")
        gate.assert_closed()
        first = admin.sql("SELECT count(*) FROM cities;", DATABASE)
        backend("python", "-m", "app.seed")
        gate.assert_closed()
        if first == "0" or first != admin.sql("SELECT count(*) FROM cities;", DATABASE):
            raise RuntimeError("canonical seed did not preserve city count across rerun")

        if admin.sql(
            f"SELECT id || '|' || name || '|' || wonder_rules_version FROM worlds WHERE id={world_id};",
            DATABASE,
        ) != f"{world_id}|Historical CI world|legacy-v1":
            raise RuntimeError("real migration changed historical world identity/rules")
        if admin.sql("SELECT wonder_rules_version FROM worlds WHERE name='Mundo 1';",
                     DATABASE) != "alliance-v2":
            raise RuntimeError("new seeded world did not receive current rules")
        grant_fixture_schema(admin)
        gate.assert_closed()
        # No runtime login is allowed, even to newly migrated tables.
        if admin.sql(
            "SELECT CASE WHEN has_table_privilege('game_app','wonder_funding','INSERT') "
            "AND has_table_privilege('game_app','wonder_contributions','INSERT') "
            "AND has_sequence_privilege('game_app','wonder_funding_id_seq','USAGE') "
            "AND NOT has_table_privilege('game_app','alembic_version','UPDATE') "
            "AND NOT has_schema_privilege('game_app','public','CREATE') "
            "THEN 1 ELSE 0 END;", DATABASE,
        ) != "1":
            raise RuntimeError("new schema runtime grants or migration isolation incorrect")
        expect_refused(container, "UPDATE worlds SET name='unexpected';", "not permitted to log in")
        gate.assert_closed()
        print("G5 actual Alembic 0019->0020, canonical seed and fenced role rehearsal passed")
        return 0
    finally:
        cleanup_fixture(project)


if __name__ == "__main__":
    raise SystemExit(main())
