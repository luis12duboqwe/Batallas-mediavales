"""Read-only G5 database connection split preflight, without a deployment CLI.

The legacy Compose bundle still uses DB_URL for migrate/seed. This validator
is ONLY for opt-in docker-compose.g5-migration.yml and does not mutate roles.
All validation messages omit passwords and full connection strings.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote


_ROLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")
_SCHEMES = frozenset({"postgresql", "postgresql+psycopg", "postgresql+psycopg2"})


class RoleSplitError(ValueError):
    """G5 database routing must not be enabled on this environment."""


@dataclass(frozen=True)
class SplitRoles:
    application: str
    maintenance: str
    database: str


def _url(value: str, database: str, label: str) -> tuple[str, str]:
    if (not isinstance(value, str) or not value or "$" in value or
            any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise RoleSplitError(f"{label} must have a literal PostgreSQL URL")
    try:
        parsed = urlsplit(value)
        role = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        host = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise RoleSplitError(f"{label} has malformed connection identity") from None
    if (parsed.scheme not in _SCHEMES or host != "database" or
            port not in (None, 5432) or
            unquote(parsed.path) != "/" + database or
            parsed.query or parsed.fragment or
            not _ROLE.fullmatch(role) or
            not password or any(ord(ch) < 32 for ch in password)):
        raise RoleSplitError(f"{label} does not target the audited Compose PostgreSQL")
    return role, password


def validate_split(values: dict[str, str]) -> SplitRoles:
    """Require app and migration identities separate on the SAME PG15 database.

    This is static routing attestation only. It does not prove the app role
    exists, its privilege membership, or that the DB is currently fenced.
    """
    if not isinstance(values, dict):
        raise RoleSplitError("G5 environment is not a mapping")
    database = values.get("POSTGRES_DB", "")
    admin = values.get("POSTGRES_USER", "")
    if (not isinstance(database, str) or not _ROLE.fullmatch(database)
            or not isinstance(admin, str) or not _ROLE.fullmatch(admin)
            or admin == "PUBLIC" or admin.startswith("pg_")):
        raise RoleSplitError("G5 database/maintenance identity is invalid")
    app, app_password = _url(values.get("DB_URL"), database, "DB_URL")
    migration, migration_password = _url(
        values.get("G5_MIGRATION_DB_URL"), database, "G5_MIGRATION_DB_URL"
    )
    if app in {admin, "postgres", "PUBLIC"} or app.startswith("pg_"):
        raise RoleSplitError("G5 application must use a separate non-administrative role")
    if migration != admin:
        raise RoleSplitError("G5 migration role does not match the inspected maintenance identity")
    raw_admin_password = values.get("POSTGRES_PASSWORD")
    if not isinstance(raw_admin_password, str) or not raw_admin_password:
        raise RoleSplitError("G5 maintenance database credential is missing")
    if raw_admin_password != migration_password:
        raise RoleSplitError("G5 migration credential differs from the maintenance identity")
    if app_password == migration_password:
        raise RoleSplitError("G5 application and migration passwords must be distinct")
    return SplitRoles(app, migration, database)
