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
    "no_other_database_access", "no_parameter_grants",
)
DATABASE_CHECKS = (
    "target_identity", "only_standard_extension", "no_foreign_tables",
    "no_event_triggers", "no_custom_security_definers", "no_preload_libraries",
    "no_native_routines", "no_sensitive_builtin_execute", "no_sensitive_catalog_access",
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
    target: Pg15FenceTarget, session: ReadOnlySession, *, fenced: bool,
    reopening_limit: int | None = None,
) -> InventoryObservation:
    """Reject topology outside a deliberately narrow dedicated-cluster policy.

    The maintenance session must use a read-only transaction. In the unfenced
    observation only runtime app sessions in the target DB are admitted; in
    the fenced observation no other client sessions are admitted. A mixed
    reopening observation retains NOLOGIN and zero client sessions, while
    requiring the exact previously captured nonzero database limit. All
    unexpected user roles, even NOLOGIN, and explicit role grants involving
    user roles are blockers. The target catalog inspection uses one temporary
    maintenance connection, closed before returning. Recheck cluster state
    after it closes. A caller still needs continuous external exclusivity.
    """
    if (not isinstance(target, Pg15FenceTarget) or type(fenced) is not bool
            or target.database in {'template0', 'template1'}
            or (reopening_limit is not None and (
                fenced is not True or type(reopening_limit) is not int
                or not -1 <= reopening_limit <= 2147483647 or reopening_limit == 0))):
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
    limit = (f"datconnlimit={reopening_limit}" if reopening_limit is not None
             else "datconnlimit=0" if fenced else "datconnlimit<>0")
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
        f"NOT EXISTS (SELECT 1 FROM pg_database WHERE datname<>'{db}' AND "
        f"datallowconn AND has_database_privilege('{app}',oid,'CONNECT'))",
        "NOT EXISTS (SELECT 1 FROM pg_parameter_acl p "
        "CROSS JOIN LATERAL aclexplode(p.paracl) AS a "
        f"WHERE a.grantee IN (0, (SELECT oid FROM pg_roles WHERE rolname='{app}')) "
        "AND a.privilege_type IN ('SET','ALTER SYSTEM'))",
    ))
    def catalog(database):
        return _select((
        f"current_database()='{database}' AND {identity}",
        "NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname<>'plpgsql')",
        "NOT EXISTS (SELECT 1 FROM pg_foreign_table)",
        "NOT EXISTS (SELECT 1 FROM pg_event_trigger)",
        "NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE p.prosecdef AND (p.oid>=16384 OR n.nspname NOT IN ('pg_catalog','information_schema')))",
        preload,
        "NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang "
        "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE "
        "(l.lanname IN ('internal','c') OR NOT l.lanpltrusted) "
        "AND (p.oid>=16384 OR n.nspname NOT IN ('pg_catalog','information_schema')))",
        # These server-file operations must never be executable by the
        # application identity, even if a catalog baseline is incomplete.
        # Owners retain the ability to grant privileges to themselves even
        # when the ordinary privilege is currently revoked.
        "NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='pg_catalog' AND "
        f"(p.proowner=(SELECT oid FROM pg_roles WHERE rolname='{app}') "
        "OR (p.proname IN ('lo_import','lo_export') "
        f"AND has_function_privilege('{app}',p.oid,'EXECUTE')))) AND "
        # Detect nonstandard grants of built-in routine execution relative to
        # the initdb ACL, rather than classifying standard PUBLIC execution
        # of an unrelated overload as elevated authority. Explicit app grants
        # are not part of the stock initial ACL. Membership is checked above.
        "NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "LEFT JOIN pg_init_privs i ON i.classoid='pg_proc'::regclass AND i.objoid=p.oid "
        "AND i.objsubid=0 AND i.privtype='i' "
        "CROSS JOIN LATERAL aclexplode(p.proacl) AS a "
        "WHERE n.nspname='pg_catalog' AND p.oid<16384 AND a.privilege_type='EXECUTE' "
        f"AND a.grantee IN (0,(SELECT oid FROM pg_roles WHERE rolname='{app}')) "
        f"AND has_function_privilege('{app}',p.oid,'EXECUTE') "
        "AND NOT EXISTS (SELECT 1 FROM aclexplode(COALESCE(i.initprivs,"
        "acldefault('f',p.proowner))) AS initial "
        "WHERE initial.grantee=a.grantee AND initial.privilege_type=a.privilege_type "
        "AND (NOT a.is_grantable OR initial.is_grantable)))",
        # Some subscription metadata columns are intentionally visible in
        # stock PG15. Check confidential columns and catalog mutation ACLs,
        # not arbitrary SELECT on any nonsecret column.
        "NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid=c.oid "
        "WHERE n.nspname='pg_catalog' AND a.attnum>0 AND NOT a.attisdropped "
        "AND ((c.relname='pg_authid' AND a.attname='rolpassword') OR "
        "(c.relname='pg_shadow' AND a.attname='passwd') OR "
        "(c.relname='pg_subscription' AND a.attname='subconninfo')) "
        f"AND has_column_privilege('{app}',c.oid,a.attnum,'SELECT')) "
        # The effective privilege inquiry can mask catalog writes under the
        # server's current system-catalog policy. Reject latent raw grants
        # too, and ownership, not only permissions currently usable.
        "AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='pg_catalog' AND c.relkind IN ('r','v','m','p','f','S','i','I','c','t') "
        f"AND (c.relowner=(SELECT oid FROM pg_roles WHERE rolname='{app}') "
        "OR EXISTS (SELECT 1 FROM aclexplode(c.relacl) a "
        f"WHERE a.grantee IN (0,(SELECT oid FROM pg_roles WHERE rolname='{app}')) "
        "AND a.privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE','TRIGGER','USAGE') "
        "AND NOT (c.relname='pg_settings' AND c.relkind='v' AND c.oid<16384 "
        "AND a.grantee=0 AND a.privilege_type='UPDATE' AND NOT a.is_grantable)) "
        "OR EXISTS (SELECT 1 FROM pg_attribute col CROSS JOIN LATERAL aclexplode(col.attacl) a "
        "WHERE col.attrelid=c.oid AND col.attnum>0 AND NOT col.attisdropped "
        f"AND a.grantee IN (0,(SELECT oid FROM pg_roles WHERE rolname='{app}')) "
        "AND a.privilege_type IN ('INSERT','UPDATE')))) "
        "AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='pg_catalog' AND c.relkind IN ('r','v','m','p','f') "
        # pg_settings has stock PUBLIC UPDATE with permission-checked
        # set_config rules. Exempt only that standard view's UPDATE; all
        # other catalog mutations and explicit additional grants still fail.
        f"AND (has_table_privilege('{app}',c.oid,'INSERT,DELETE,TRUNCATE,TRIGGER') "
        f"OR has_any_column_privilege('{app}',c.oid,'INSERT') "
        "OR ((c.relname<>'pg_settings' OR c.relkind<>'v' OR c.oid>=16384) "
        f"AND (has_table_privilege('{app}',c.oid,'UPDATE') "
        f"OR has_any_column_privilege('{app}',c.oid,'UPDATE'))) "
        "OR (c.relname='pg_settings' AND EXISTS (SELECT 1 FROM aclexplode(c.relacl) a "
        "WHERE a.privilege_type='UPDATE' "
        f"AND (a.grantee=(SELECT oid FROM pg_roles WHERE rolname='{app}') "
        "OR (a.grantee=0 AND a.is_grantable)))) "
        "OR (c.relname='pg_settings' AND EXISTS (SELECT 1 FROM pg_attribute col "
        "CROSS JOIN LATERAL aclexplode(col.attacl) a WHERE col.attrelid=c.oid "
        "AND col.attnum>0 AND NOT col.attisdropped AND a.privilege_type='UPDATE' "
        f"AND a.grantee IN (0,(SELECT oid FROM pg_roles WHERE rolname='{app}'))))))",
    ))
    first = _flags(session, "postgres", cluster, CLUSTER_CHECKS)
    # Do not connect to an untrusted or already ambiguous target.
    if first:
        return InventoryObservation(first)
    maintenance = _flags(session, "postgres", catalog("postgres"), DATABASE_CHECKS)
    second = _flags(session, db, catalog(db), DATABASE_CHECKS)
    last = _flags(session, "postgres", cluster, CLUSTER_CHECKS)
    return InventoryObservation(tuple(dict.fromkeys((*maintenance, *second, *last))))
