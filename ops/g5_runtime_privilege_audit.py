"""Read-only, scoped PG15 privilege observations; not a provisioning policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ops.g5_pg15_writer_fence import IDENTIFIER, Pg15FenceTarget


class AuditError(RuntimeError):
    """The requested audit or its evidence is invalid."""


class ReadOnlySession(Protocol):
    def query(self, database: str, statement: str) -> str:
        """Run one statement in a fresh read-only session, then close it."""
        ...


TABLE_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"})
SEQUENCE_PRIVILEGES = frozenset({"USAGE", "SELECT", "UPDATE"})


@dataclass(frozen=True)
class RelationRule:
    """Explicit assertions for one public relation, not an exhaustive grant list."""

    name: str
    kind: str
    required: frozenset[str]
    forbidden: frozenset[str]

    def __post_init__(self):
        if (not isinstance(self.name, str) or not IDENTIFIER.fullmatch(self.name)
                or self.kind not in ("table", "sequence")
                or not isinstance(self.required, frozenset)
                or not isinstance(self.forbidden, frozenset)):
            raise AuditError("invalid relation rule")
        allowed = TABLE_PRIVILEGES if self.kind == "table" else SEQUENCE_PRIVILEGES
        if (not self.required and not self.forbidden
                or self.required & self.forbidden
                or not (self.required | self.forbidden) <= allowed):
            raise AuditError("invalid relation privileges")


@dataclass(frozen=True)
class AuditObservation:
    blockers: tuple[str, ...]


def inspect_runtime_privileges(
    target: Pg15FenceTarget, session: ReadOnlySession, rules: tuple[RelationRule, ...],
) -> AuditObservation:
    """Compare explicit table-level requirements and negative assertions.

    A positive result is only evidence for these assertions in one snapshot.
    It is not a minimal-grant certificate, DDL fence, or execution test.
    """
    if (not isinstance(target, Pg15FenceTarget) or target.database in {"template0", "template1"}
            or not isinstance(rules, tuple) or not rules
            or any(not isinstance(rule, RelationRule) for rule in rules)
            or len({rule.name for rule in rules}) != len(rules)):
        raise AuditError("invalid audit target or rules")

    app, admin, database = target.application_role, target.maintenance_role, target.database
    grantable_grantee = (
        f"(a.grantee=0 OR EXISTS (SELECT 1 FROM pg_roles r WHERE r.oid=a.grantee "
        f"AND pg_has_role('{app}', r.oid, 'MEMBER')))"
    )
    checks = [
        ("context", f"current_database()='{database}' AND current_user='{admin}' "
         "AND current_setting('transaction_read_only')='on' "
         "AND current_setting('server_version_num')::int BETWEEN 150000 AND 159999 "
         "AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper)"),
        ("role", f"EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{app}' "
         "AND NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))"),
        ("role_membership", "NOT EXISTS (SELECT 1 FROM pg_roles r "
         f"WHERE r.rolname<>'{app}' AND pg_has_role('{app}', r.oid, 'MEMBER'))"),
        ("database_owner", "NOT EXISTS (SELECT 1 FROM pg_database d "
         f"WHERE d.datname=current_database() AND pg_has_role('{app}', d.datdba, 'MEMBER'))"),
        ("schema_owner", "NOT EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname='public' "
         f"AND pg_has_role('{app}', n.nspowner, 'MEMBER'))"),
        ("schema_usage", f"has_schema_privilege('{app}', 'public', 'USAGE')"),
        ("schema_create", f"NOT has_schema_privilege('{app}', 'public', 'CREATE')"),
        ("database_create", f"NOT has_database_privilege('{app}', current_database(), 'CREATE')"),
        ("database_temp", f"NOT has_database_privilege('{app}', current_database(), 'TEMP')"),
        ("database_grant_option", "NOT EXISTS (SELECT 1 FROM pg_database d "
         "CROSS JOIN LATERAL aclexplode(d.datacl) a WHERE d.datname=current_database() "
         f"AND a.is_grantable AND {grantable_grantee})"),
        ("schema_grant_option", "NOT EXISTS (SELECT 1 FROM pg_namespace n "
         "CROSS JOIN LATERAL aclexplode(n.nspacl) a WHERE n.nspname='public' "
         f"AND a.is_grantable AND {grantable_grantee})"),
    ]
    for rule in rules:
        kind = "IN ('r','p')" if rule.kind == "table" else "='S'"
        relation = ("SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    f"WHERE n.nspname='public' AND c.relname='{rule.name}' "
                    f"AND c.relkind {kind}")
        # A missing or differently typed relation is independently a blocker,
        # including when all requested privileges are forbidden.
        oid = f"({relation})"
        checks.append((f"{rule.name}:exists", f"EXISTS ({relation})"))
        checks.append((f"{rule.name}:owner", f"NOT EXISTS ({relation} AND "
                       f"pg_has_role('{app}', c.relowner, 'MEMBER'))"))
        checks.append((f"{rule.name}:grant_option",
                       f"NOT EXISTS (SELECT 1 FROM pg_class c CROSS JOIN LATERAL "
                       f"aclexplode(c.relacl) a WHERE c.oid={oid} "
                       f"AND a.is_grantable AND {grantable_grantee})"
                       + (f" AND NOT EXISTS (SELECT 1 FROM pg_attribute col CROSS JOIN LATERAL "
                          f"aclexplode(col.attacl) a WHERE col.attrelid={oid} "
                          f"AND col.attnum>0 AND NOT col.attisdropped AND a.is_grantable "
                          f"AND {grantable_grantee})" if rule.kind == "table" else "")))
        function = "has_table_privilege" if rule.kind == "table" else "has_sequence_privilege"
        for privilege in sorted(rule.required):
            checks.append((f"{rule.name}:missing:{privilege}",
                           f"COALESCE({function}('{app}', {oid}, '{privilege}'), false)"))
        for privilege in sorted(rule.forbidden):
            effective = f"{function}('{app}', {oid}, '{privilege}')"
            if rule.kind == "table" and privilege in {"SELECT", "INSERT", "UPDATE", "REFERENCES"}:
                effective += f" OR has_any_column_privilege('{app}', {oid}, '{privilege}')"
            checks.append((f"{rule.name}:unexpected:{privilege}",
                           f"NOT COALESCE(({effective}), false)"))

    statement = "SELECT " + ", ".join(
        f"CASE WHEN ({condition}) THEN 1 ELSE 0 END" for _, condition in checks
    ) + ";"
    try:
        response = session.query(database, statement)
    except Exception:
        raise AuditError("PostgreSQL privilege observation failed") from None
    if not isinstance(response, str):
        raise AuditError("malformed PostgreSQL privilege observation")
    values = response.strip().split("|")
    if len(values) != len(checks) or any(value not in ("0", "1") for value in values):
        raise AuditError("malformed PostgreSQL privilege observation")
    return AuditObservation(tuple(name for (name, _), value in zip(checks, values) if value == "0"))
