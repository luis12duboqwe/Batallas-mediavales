"""Isolated PostgreSQL G5 writer-fence protocol regressions; no database used."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_pg15_writer_fence import FenceError, Pg15FenceTarget, Pg15PersistentFence


class FakePg:
    """Emulates PG15 catalog responses, not a production SQL executor."""

    def __init__(self):
        self.admin = True
        self.unprivileged = True
        self.limit = -1
        self.login = True
        self.sessions = 2
        self.prepared = 0
        self.terminate_ok = True
        self.fail_ddl = None
        self.calls = []

    def query_fresh(self, sql: str) -> str:
        self.calls.append(("query", sql))
        if "current_database()" in sql:
            return "1" if self.admin else "0"
        if "app.rolcanlogin" in sql:
            return "1" if self.unprivileged and self.login else "0"
        if "SELECT datconnlimit FROM pg_database" in sql:
            return str(self.limit)
        if "pg_terminate_backend" in sql:
            if not self.terminate_ok:
                return "f"
            self.sessions = 0
            return "t"
        if "AND NOT EXISTS (SELECT 1 FROM pg_prepared_xacts" in sql:
            return "1" if (
                self.limit == 0 and not self.login and
                self.sessions == 0 and self.prepared == 0
            ) else "0"
        if "FROM pg_database" in sql and "datconnlimit=0" in sql:
            return "1" if self.limit == 0 else "0"
        raise AssertionError(f"Unexpected synthetic query: {sql}")

    def execute_committed(self, sql: str) -> None:
        self.calls.append(("execute", sql))
        if self.fail_ddl is not None and self.fail_ddl in sql:
            raise ValueError("driver connection diagnostic: simulated password=SECRET")
        if sql.startswith('ALTER DATABASE "medievol_db" CONNECTION LIMIT 0;'):
            self.limit = 0
        elif sql.startswith('ALTER ROLE "game_app" NOLOGIN;'):
            self.login = False
        else:
            raise AssertionError(f"Unexpected synthetic DDL: {sql}")


@pytest.fixture
def target():
    return Pg15FenceTarget("medievol_db", "game_app", "postgres")


def test_pg15_barrier_is_one_way_and_ordered(target):
    connection = FakePg()
    barrier = Pg15PersistentFence(target, connection)
    barrier.engage()
    assert connection.limit == 0
    assert connection.login is False
    assert connection.sessions == 0
    assert [kind for kind, sql in connection.calls if kind == "execute"] == [
        "execute", "execute"
    ]
    strings = [sql for _, sql in connection.calls]
    assert strings[0].startswith("SELECT CASE WHEN current_database()")
    assert strings[1].startswith("SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles AS app")
    assert strings[2].startswith("SELECT datconnlimit FROM pg_database")
    assert strings[3] == 'ALTER DATABASE "medievol_db" CONNECTION LIMIT 0;'
    assert "datconnlimit=0" in strings[4]
    assert strings[5] == 'ALTER ROLE "game_app" NOLOGIN;'
    assert "pg_terminate_backend" in strings[6]
    assert "pg_prepared_xacts" in strings[-1]
    barrier.assert_closed()
    # Re-activation without a reconciliation protocol must fail closed.
    with pytest.raises(FenceError, match="not a distinct LOGIN"):
        barrier.engage()
    assert connection.limit == 0 and not connection.login


@pytest.mark.parametrize(
    ("attribute", "value", "reason"),
    [
        ("admin", False, "authorized"),
        ("unprivileged", False, "elevated"),
        ("login", False, "elevated"),
        ("limit", 0, "not a distinct LOGIN|already fenced"),
        ("limit", -2, "missing or already fenced"),
    ],
)
def test_invalid_context_never_alters_roles(target, attribute, value, reason):
    connection = FakePg()
    setattr(connection, attribute, value)
    with pytest.raises(FenceError, match=reason):
        Pg15PersistentFence(target, connection).engage()
    assert not any(kind == "execute" for kind, _ in connection.calls)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database", "postgres"),
        ("database", "game; DROP DATABASE postgres"),
        ("database", "medievol-db"),
        ("application_role", "postgres"),
        ("application_role", "pg_write_all_data"),
        ("application_role", "game_app;DROP ROLE"),
        ("maintenance_role", "game_app"),
    ],
)
def test_target_identity_rejects_sql_injection_and_privileged_app(target, field, value):
    with pytest.raises(FenceError):
        replace(target, **{field: value})


def test_partial_failure_after_database_gate_never_reopens_connections(target):
    connection = FakePg()
    connection.fail_ddl = "ALTER ROLE"
    with pytest.raises(FenceError, match="DDL failed") as failed:
        Pg15PersistentFence(target, connection).engage()
    assert "SECRET" not in str(failed.value)
    assert connection.limit == 0
    assert connection.login is True
    assert connection.sessions == 2
    assert not any("CONNECTION LIMIT -1" in sql for _, sql in connection.calls)


def test_failed_termination_keeps_existing_gate_closed_and_refuses_success(target):
    connection = FakePg()
    connection.terminate_ok = False
    with pytest.raises(FenceError, match="refused to terminate"):
        Pg15PersistentFence(target, connection).engage()
    assert connection.limit == 0
    assert connection.login is False
    assert connection.sessions == 2


@pytest.mark.parametrize("prepared,sessions", [(1, 0), (0, 1), (2, 3)])
def test_remaining_prepared_transactions_or_sessions_refuse_barrier(target, prepared, sessions):
    connection = FakePg()
    connection.prepared = prepared
    connection.terminate_ok = not sessions
    if sessions:
        with pytest.raises(FenceError, match="refused to terminate"):
            Pg15PersistentFence(target, connection).engage()
    else:
        with pytest.raises(FenceError, match="not closed"):
            Pg15PersistentFence(target, connection).engage()
    assert connection.limit == 0
    assert not connection.login


def test_false_scalar_and_bad_ddl_result_never_pass_as_proof(target):
    class FuzzyPg(FakePg):
        def query_fresh(self, sql: str):
            if "current_database()" in sql:
                return "1\n1"
            return super().query_fresh(sql)
    with pytest.raises(FenceError, match="ambiguous"):
        Pg15PersistentFence(target, FuzzyPg()).engage()

    class MisleadingDDL(FakePg):
        def execute_committed(self, sql: str):
            super().execute_committed(sql)
            return "looks good"
    with pytest.raises(FenceError, match="ambiguous"):
        Pg15PersistentFence(target, MisleadingDDL()).engage()
