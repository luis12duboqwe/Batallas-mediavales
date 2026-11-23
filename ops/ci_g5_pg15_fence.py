#!/usr/bin/env python3
"""CI-only PostgreSQL 15 writer-fence rehearsal in an isolated Docker container.

No VPS, mounts, volumes, host ports, external networks or real credentials.
This script refuses execution outside GitHub Actions CI. The PostgreSQL
fence library itself has no production executor or CLI.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from uuid import uuid4

from ops.g5_pg15_writer_fence import Pg15FenceTarget, Pg15PersistentFence


def run(args: list[str], *, timeout: int = 40, check: bool = True) -> subprocess.CompletedProcess:
    completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if check and completed.returncode != 0:
        # Never forward stderr or environment content from a DB process.
        raise RuntimeError(f"isolated PG15 command returned {completed.returncode}")
    return completed


class CIOnlyAdmin:
    """A new, autocommit psql session is used for every statement."""

    def __init__(self, container: str):
        self.container = container

    def _psql(self, sql: str, database: str = "postgres"):
        return run([
            "docker", "exec", self.container,
            "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
            "-d", database, "-Atqc", sql,
        ])

    def query_fresh(self, sql: str) -> str:
        return self._psql(sql).stdout.strip()

    def execute_committed(self, sql: str) -> None:
        self._psql(sql)
        return None


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
        print("CI-only PG15 fence rehearsal refused outside GitHub Actions", file=sys.stderr)
        return 2
    name = f"bm-g5-pg15-fence-{os.getpid()}-{uuid4().hex[:8]}"
    started = False
    try:
        run([
            "docker", "run", "--rm", "-d", "--network", "none", "--name", name,
            "-e", "POSTGRES_PASSWORD=synthetic-ci-only-not-a-secret",
            "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:15-alpine",
        ], timeout=90)
        started = True
        for _ in range(80):
            ready = run(["docker", "exec", name, "pg_isready", "-U", "postgres"], check=False)
            if ready.returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("isolated PG15 server did not become ready")

        admin = CIOnlyAdmin(name)
        admin.execute_committed("CREATE ROLE game_app LOGIN;")
        admin.execute_committed("CREATE DATABASE medievol_db OWNER game_app;")
        admin._psql(
            "CREATE TABLE durable_probe (id integer PRIMARY KEY, marker text NOT NULL); "
            "INSERT INTO durable_probe VALUES (1, 'commit-before-fence');",
            database="medievol_db",
        )

        # A live application session exists BEFORE the cutover. PG15 must
        # terminate it before a backup can be declared quiescent.
        run([
            "docker", "exec", "-d", name, "psql", "-X", "-U", "game_app",
            "-d", "medievol_db", "-Atqc", "SELECT pg_sleep(90);",
        ])
        for _ in range(30):
            sessions = admin.query_fresh(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname='medievol_db' AND usename='game_app';"
            )
            if sessions == "1":
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("test failed to create an active game writer")

        fence = Pg15PersistentFence(
            Pg15FenceTarget("medievol_db", "game_app", "postgres"), admin
        )
        fence.engage()
        fence.assert_closed()
        # Simulate a new coordinator/process checking persistent catalog
        # state rather than trusting the original Python object.
        Pg15PersistentFence(
            Pg15FenceTarget("medievol_db", "game_app", "postgres"), CIOnlyAdmin(name)
        ).assert_closed()

        if run(
            ["docker", "exec", name, "psql", "-X", "-U", "game_app",
             "-d", "medievol_db", "-Atqc", "SELECT 1;"],
            check=False,
        ).returncode == 0:
            raise RuntimeError("game_app unexpectedly reconnected after NOLOGIN")
        marker = admin._psql(
            "SELECT marker FROM durable_probe WHERE id=1;", database="medievol_db"
        ).stdout.strip()
        if marker != "commit-before-fence":
            raise RuntimeError("confirmed game transaction changed during write fence")
        print("PG15 G5 writer-fence rehearsal passed (isolated, not release certification)")
        return 0
    finally:
        if started:
            run(["docker", "rm", "-f", name], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
