"""Strict read-only observations for a dedicated PG15 deployment cluster.

This inventory is deliberately not an authorization or a write barrier.
It cannot prove who possesses maintenance credentials or Docker/root access,
nor continuity between observations. No production executor or CLI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ops.g5_pg15_writer_fence import Pg15FenceTarget


class InventoryError(RuntimeError):
    """Evidence unavailable or malformed."""


class ReadOnlySession(Protocol):
    def query(self, database: str, statement: str) -> str:
        """One fresh, read-only session, closed before returning."""
        ...


CLUSTER_CHECKS = (
    "maintenance_identity", "dedicated_databases", "dedicated_roles",
    "no_role_membership", "role_state", "client_sessions",
    "no_prepared_transactions", "no_replication_slots", "no_subscriptions",
    "known_backend_types", "no_preload_libraries", "no_preload_overrides",
)
DATABASE_CHECKS = (
    "target_identity", "only_standard_extension", "no_foreign_tables",
    "no_event_triggers", "no_custom_security_definers", "no_preload_libraries",
)


@dataclass(frozen=True)
class InventoryObservation:
    blockers: tuple[str, ...]


def _flags(session, database, sql, names):
    try:
        response = session.query(database, sql)
    except Exception:
        raise InventoryError("PostgreSQL inventory query failed") from None
    if not isinstance(response, str):
        raise InventoryError("malformed PostgreSQL inventory")
    fields = response.strip().split("|")
    if len(fields) != len(names) or any(value not in ("1", "0") for value in fields):
        raise InventoryError("malformed PostgreSQL inventory")
    return tuple(name for name, value in zip(names, fields) if value == "0")


def _select(checks):
    return "SELECT " + ", ".join(
        "CASE WHEN (" + condition + ") THEN 1 ELSE 0 END" for condition in checks
    ) + ";"


def inspect_privileged_inventory(
    target: Pg15FenceTarget, session: ReadOnlySession, *, fenced: bool
) -> InventoryObservation:
    """Reject topology outside a deliberately narrow dedicated-cluster policy.

    The maintenance session must use a read-only transaction. In the unfenced
    observation only runtime app sessions in the target DB are admitted; in
    the fenced observation no other client sessions are admitted. All
    unexpected user roles, even NOLOGIN, and explicit role grants involving
    user roles are blockers. The target catalog inspection uses one temporary
    maintenance connection, closed before returning. Recheck cluster state
    after it closes. A caller still needs continuous external exclusivity.
    """
    if (not isinstance(target, Pg15FenceTarget) or type(fenced) is not bool
            or target.database in {'template0', 'template1'}):
        raise InventoryError("invalid privileged inventory target")
    db, app, admin = target.database, target.application_role, target.maintenance_role
    # Pg15FenceTarget already validates all identifiers. Do not interpolate
    # arbitrary connection URLs, role names or executor data here.
    identity = (
        f"current_user='{admin}' AND current_setting('transaction_read_only')='on' "
        "AND current_setting('server_version_num')::int BETWEEN 150000 AND 159999 "
        "AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper AND rolcanlogin)"
    )
    preload = " AND ".join(f"current_setting('{key}')=''" for key in (
        "shared_preload_libraries", "session_preload_libraries", "local_preload_libraries"
    ))
    role_login = "NOT rolcanlogin" if fenced else "rolcanlogin"
    limit = "datconnlimit=0" if fenced else "datconnlimit<>0"
    other_sessions = "" if fenced else f" AND (usename='{app}' AND datname='{db}') IS NOT TRUE"
    cluster = _select((
        f"current_database()='postgres' AND {identity}",
        f"EXISTS (SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba "
        f"WHERE d.datname='{db}' AND {limit} AND NOT d.datistemplate "
        f"AND d.datallowconn AND r.rolname='{admin}') "
        f"AND NOT EXISTS (SELECT 1 FROM pg_database WHERE datname NOT IN "
        f"('postgres','template0','template1','{db}'))",
        "NOT EXISTS (SELECT 1 FROM pg_roles WHERE "
        f"rolname NOT IN ('{app}','{admin}') AND NOT "
        "(oid<16384 AND left(rolname,3)='pg_' AND NOT rolcanlogin))",
        "NOT EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid "
        "JOIN pg_roles u ON u.oid=m.member "
        "WHERE NOT (r.oid<16384 AND u.oid<16384 AND left(r.rolname,3)='pg_' "
        "AND left(u.rolname,3)='pg_'))",
        f"EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{app}' AND {role_login} "
        "AND NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))",
        "NOT EXISTS (SELECT 1 FROM pg_stat_activity WHERE backend_type='client backend' "
        f"AND pid<>pg_backend_pid(){other_sessions})",
        "NOT EXISTS (SELECT 1 FROM pg_prepared_xacts)",
        "NOT EXISTS (SELECT 1 FROM pg_replication_slots)",
        "NOT EXISTS (SELECT 1 FROM pg_subscription)",
        "NOT EXISTS (SELECT 1 FROM pg_stat_activity WHERE backend_type IS NULL OR "
        "backend_type NOT IN ('client backend','autovacuum launcher','autovacuum worker',"
        "'background writer','checkpointer','logical replication launcher','walwriter','archiver'))",
        preload,
        "NOT EXISTS (SELECT 1 FROM pg_db_role_setting s CROSS JOIN LATERAL unnest(s.setconfig) AS v(setting) "
        "WHERE split_part(v.setting,'=',1) IN ('shared_preload_libraries',"
        "'session_preload_libraries','local_preload_libraries'))",
    ))
    catalog = _select((
        f"current_database()='{db}' AND {identity}",
        "NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname<>'plpgsql')",
        "NOT EXISTS (SELECT 1 FROM pg_foreign_table)",
        "NOT EXISTS (SELECT 1 FROM pg_event_trigger)",
        "NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE p.prosecdef AND (p.oid>=16384 OR n.nspname NOT IN ('pg_catalog','information_schema')))",
        preload,
    ))
    first = _flags(session, "postgres", cluster, CLUSTER_CHECKS)
    # Do not connect to an untrusted or already ambiguous target.
    if first:
        return InventoryObservation(first)
    second = _flags(session, db, catalog, DATABASE_CHECKS)
    last = _flags(session, "postgres", cluster, CLUSTER_CHECKS)
    return InventoryObservation(tuple(dict.fromkeys((*second, *last))))
