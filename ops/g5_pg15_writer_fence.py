"""PG15 write-fence protocol for the G5 cutover laboratory (#174).

This module has NO CLI and NO installed SQL executor, credential loader,
release endpoint or production adapter. Never invoke on a live database until
the activation lease, multi-writer audit and PG15 integration are certified.

The database-level connection limit and NOLOGIN survive process crashes.
They do NOT prevent writes by PostgreSQL superusers or other privileged
channels; the coordinator must independently block and audit those writers.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol


IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")


class FenceError(RuntimeError):
    """The PG15 cutover may not assume a durable writer fence."""


@dataclass(frozen=True)
class Pg15FenceTarget:
    database: str
    application_role: str
    maintenance_role: str

    def __post_init__(self):
        for field in ("database", "application_role", "maintenance_role"):
            value = getattr(self, field)
            if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
                raise FenceError(f"unsafe PostgreSQL {field}")
        if (self.application_role == self.maintenance_role
                or self.application_role in {"postgres", "PUBLIC"}
                or self.application_role.startswith("pg_")
                or self.database == "postgres"):
            raise FenceError("application writer role and maintenance identity must be isolated")


class Pg15SqlSession(Protocol):
    """An audited, privileged connection to the *postgres* maintenance DB.

    query() must issue exactly one SQL statement, raise on any SQL/transport
    error, and return one unadorned psql scalar. Credentials must never be
    printed, interpolated into SQL, or exposed by exceptions.
    """
    def query(self, sql: str) -> str: ...
    def execute(self, sql: str) -> None: ...


class Pg15PersistentFence:
    """Fail-closed DB gate for an external, not-yet-implemented G5 adapter.

    Operation is intentionally one-way: no automatic LOGIN/connection-limit
    restore exists here. Missing or ambiguous evidence raises FenceError.
    A real adapter must hold the activated G5 release lock and close all
    other privileged writers before using this library.
    """

    def __init__(self, target: Pg15FenceTarget, session: Pg15SqlSession):
        if not isinstance(target, Pg15FenceTarget):
            raise FenceError("invalid PostgreSQL writer-fence target")
        self.target = target
        self.session = session

    def _scalar(self, sql: str) -> str:
        try:
            result = self.session.query(sql)
        except Exception as exc:
            # Do not print a connection string, SQL diagnostics or credentials.
            raise FenceError("PostgreSQL writer-fence statement failed") from exc
        if not isinstance(result, str) or not result.strip() or "\n" in result.strip():
            raise FenceError("PostgreSQL writer-fence evidence is missing or ambiguous")
        return result.strip()

    def _execute(self, sql: str) -> None:
        try:
            result = self.session.execute(sql)
        except Exception as exc:
            raise FenceError("PostgreSQL write-fence DDL failed") from exc
        if result is not None:
            raise FenceError("PostgreSQL write-fence DDL returned ambiguous evidence")

    def _expect(self, sql: str, expected: str, reason: str) -> None:
        if self._scalar(sql) != expected:
            raise FenceError(reason)

    def _require_authorized_context(self) -> None:
        """Reject a session targeting the game DB or a non-superuser executor."""
        admin = self.target.maintenance_role
        self._expect(
            "SELECT CASE WHEN current_database()='postgres' "
            f"AND current_user='{admin}' AND EXISTS ("
            "SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper) "
            "THEN 1 ELSE 0 END;",
            "1", "maintenance session is not an authorized PostgreSQL superuser",
        )

    def _require_least_privileged_app_role(self) -> None:
        app = self.target.application_role
        self._expect(
            "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles AS app "
            f"WHERE app.rolname='{app}' AND app.rolcanlogin "
            "AND NOT (app.rolsuper OR app.rolcreatedb OR app.rolcreaterole "
            "OR app.rolreplication OR app.rolbypassrls) "
            "AND NOT EXISTS (SELECT 1 FROM pg_roles AS privileged "
            "WHERE (privileged.rolsuper OR privileged.rolname IN "
            "('pg_write_all_data','pg_read_all_data','pg_execute_server_program',"
            "'pg_read_server_files','pg_write_server_files')) "
            "AND pg_has_role(app.oid, privileged.oid, 'MEMBER'))) "
            "THEN 1 ELSE 0 END;",
            "1", "application role is absent, elevated, or not a distinct LOGIN",
        )

    def _require_fresh_database(self) -> None:
        database = self.target.database
        result = self._scalar(
            f"SELECT datconnlimit FROM pg_database WHERE datname='{database}';"
        )
        # Missing DB or already-fenced DB is a prior incident, never a new
        # release permit. The original limit must be recovered by an operator
        # with independently audited durable state.
        try:
            limit = int(result)
        except ValueError as exc:
            raise FenceError("target database connection limit is invalid") from exc
        if limit < -1 or limit == 0:
            raise FenceError("target database is missing or already fenced")
        if str(limit) != result:
            raise FenceError("target database connection limit is ambiguous")

    def engage(self) -> None:
        """Restrict new non-superuser logins, revoke app login and drain sessions.

        Connection-limit 0 is deliberately set FIRST, so a failure between
        DDL statements cannot allow the app to reconnect unrestricted.
        Existing transactions are then terminated. No automatic reversal.
        """
        self._require_authorized_context()
        self._require_least_privileged_app_role()
        self._require_fresh_database()
        database = self.target.database
        app = self.target.application_role
        # Identifiers are strict ASCII-simple names, so quoted identifiers
        # cannot contain double quotes, whitespace or SQL metacharacters.
        self._execute(f'ALTER DATABASE "{database}" CONNECTION LIMIT 0;')
        self._execute(f'ALTER ROLE "{app}" NOLOGIN;')
        self._expect(
            "SELECT COALESCE(bool_and(pg_terminate_backend(pid)), true) "
            "FROM pg_stat_activity "
            f"WHERE datname='{database}' AND pid<>pg_backend_pid();",
            "t", "PostgreSQL refused to terminate an active connection",
        )
        self.assert_closed()

    def assert_closed(self) -> None:
        """Observe durable role, DB limit, sessions and prepared transactions.

        This is still not a guarantee against privileged external writers.
        The G5 coordinator must keep its universal barrier active as well.
        """
        database = self.target.database
        app = self.target.application_role
        self._require_authorized_context()
        self._expect(
            "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_database "
            f"WHERE datname='{database}' AND datconnlimit=0) "
            "AND EXISTS (SELECT 1 FROM pg_roles "
            f"WHERE rolname='{app}' AND NOT rolcanlogin) "
            "AND NOT EXISTS (SELECT 1 FROM pg_stat_activity "
            f"WHERE datname='{database}') "
            "AND NOT EXISTS (SELECT 1 FROM pg_prepared_xacts "
            f"WHERE database='{database}') "
            "THEN 1 ELSE 0 END;",
            "1", "PostgreSQL writer fence is not closed or sessions remain",
        )
