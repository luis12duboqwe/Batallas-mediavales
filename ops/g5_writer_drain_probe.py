#!/usr/bin/env python3
"""Read-only, fail-closed G5 writer-drain inspection (BM-0093 / #174).

This is NOT a write barrier and MUST NOT authorize backup, restore, or
reopening writers. It collects one snapshot of Compose and PostgreSQL state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

WRITERS = frozenset({"backend", "worker", "migrate", "seed"})
PASSIVE = frozenset({"database", "frontend", "nginx", "caddy"})
SERVICES = WRITERS | PASSIVE
DB_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class ProbeError(RuntimeError):
    """Could not establish a trustworthy read-only inspection."""


def _application_role(values: dict[str, str], postgres_admin: str) -> str:
    """Find the runtime app identity without printing the URL or password."""
    raw = values.get("DB_URL", "")
    try:
        url = urlsplit(raw)
    except (TypeError, ValueError) as exc:
        raise ProbeError("Application database role/URL is invalid") from exc
    if url.scheme not in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise ProbeError("Application DB_URL must use a supported PostgreSQL driver")
    username = url.username
    if not username:
        raise ProbeError("Application DB_URL must contain a distinct login role")
    app_role = unquote(username)
    if (not DB_IDENTIFIER.fullmatch(app_role) or
            not DB_IDENTIFIER.fullmatch(postgres_admin)):
        raise ProbeError("Application or maintenance database role name is unsafe")
    if app_role == postgres_admin:
        raise ProbeError(
            "Application and maintenance database users are identical; G5 role isolation NO-GO"
        )
    return app_role


def _require_unprivileged_app_role(compose: list[str], admin: str, app_role: str) -> None:
    """Observe pg_roles and reject elevated roles or superuser membership.

    This checks only privilege separation, not a durable write-admission gate.
    """
    # Role identifiers are validated before SQL interpolation.
    if not DB_IDENTIFIER.fullmatch(admin) or not DB_IDENTIFIER.fullmatch(app_role):
        raise ProbeError("Cannot validate PostgreSQL role identity")
    sql = (
        "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles AS app "
        f"WHERE app.rolname='{app_role}' "
        "AND app.rolcanlogin "
        "AND NOT (app.rolsuper OR app.rolcreatedb OR app.rolcreaterole "
        "OR app.rolreplication OR app.rolbypassrls) "
        "AND NOT EXISTS (SELECT 1 FROM pg_roles AS privileged "
        "WHERE privileged.rolsuper "
        "AND pg_has_role(app.oid, privileged.oid, 'MEMBER'))) "
        "THEN 1 ELSE 0 END;"
    )
    result = _run(compose + [
        "exec", "-T", "database", "psql", "-X", "-v", "ON_ERROR_STOP=1",
        "-U", admin, "-d", "postgres", "-Atqc", sql,
    ])
    if result.strip() != "1":
        raise ProbeError(
            "Application PostgreSQL role is missing, elevated, or inherits superuser privileges"
        )


def decode_ps(raw: str) -> list[dict]:
    """Support Docker Compose JSON array, single object, and JSON lines."""
    if not raw.strip():
        raise ProbeError("Compose returned no container inventory")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        try:
            decoded = [json.loads(line) for line in raw.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise ProbeError("Invalid Compose container inventory") from exc
    if isinstance(decoded, dict):
        decoded = [decoded]
    if not isinstance(decoded, list) or not all(isinstance(row, dict) for row in decoded):
        raise ProbeError("Malformed Compose container inventory")
    return decoded


def inspect(
    config: dict, containers: list[dict], postgres_counts: str, edge_dir: Path
) -> list[str]:
    """Return blockers. Empty only means this instant's evidence is consistent."""
    errors: list[str] = []
    if not isinstance(config, dict):
        return ["Malformed Compose configuration"]
    services = config.get("services")
    if not isinstance(services, dict) or set(services) != SERVICES:
        return ["Unexpected or missing Compose services; writer topology is unknown"]

    for service in WRITERS:
        spec = services[service]
        if not isinstance(spec, dict) or spec.get("restart") != "no":
            errors.append(f"{service}: restart policy must be no during drain")

    nginx = services["nginx"]
    mounts = nginx.get("volumes", []) if isinstance(nginx, dict) else None
    if not isinstance(mounts, list):
        errors.append("Nginx G5 mount inventory is missing")
    else:
        expected = {
            "/etc/nginx/nginx.conf": edge_dir.parent.parent / "nginx.g5.conf",
            "/etc/nginx/edge-maintenance": edge_dir,
        }
        for target, expected_source in expected.items():
            matches = [m for m in mounts if isinstance(m, dict) and m.get("target") == target]
            if len(matches) != 1:
                errors.append(f"Missing read-only G5 Nginx mount: {target}")
                continue
            mount = matches[0]
            source = Path(str(mount.get("source", "")))
            if (mount.get("read_only") is not True or source.is_symlink()
                or source.resolve() != expected_source.resolve()):
                errors.append(f"Unsafe or misplaced G5 Nginx mount: {target}")

    if edge_dir.is_symlink() or edge_dir.parent.is_symlink() or not edge_dir.is_dir():
        errors.append("Edge maintenance directory absent or unsafe")
    elif (edge_dir / "open").exists() or (edge_dir / "open").is_symlink():
        errors.append("Edge maintenance admission is open or unsafe")

    counts: dict[str, int] = {}
    for row in containers:
        service, state = row.get("Service"), row.get("State")
        if not isinstance(service, str) or not isinstance(state, str):
            errors.append("Compose container record has no trustworthy service/state")
            continue
        if service not in SERVICES:
            errors.append("Unknown running or historical Compose service")
            continue
        if state.lower() == "running":
            counts[service] = counts.get(service, 0) + 1
        elif service in WRITERS and state.lower() not in {"exited", "stopped", "dead"}:
            errors.append(f"{service}: uncertain container state ({state})")

    for service in WRITERS:
        if counts.get(service, 0):
            errors.append(f"{service}: {counts[service]} active container(s)")
    for service in ("database", "nginx"):
        if counts.get(service, 0) != 1:
            errors.append(f"{service}: expected exactly one running container")

    match = re.fullmatch(r"([0-9]+)[|]([0-9]+)", postgres_counts.strip())
    if not match:
        errors.append("PostgreSQL probe did not return two numeric counts")
    else:
        sessions, prepared = map(int, match.groups())
        if sessions:
            errors.append(f"PostgreSQL still has {sessions} client session(s)")
        if prepared:
            errors.append(f"PostgreSQL still has {prepared} prepared transaction(s)")
    return errors


def _run(argv: list[str]) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError("Required read-only command unavailable or timed out") from exc
    if proc.returncode != 0:
        # Avoid echoing stderr: Docker diagnostics sometimes include env secrets.
        raise ProbeError(f"Read-only command returned nonzero ({argv[0]})")
    return proc.stdout


def _require_closed_edge(compose: list[str], url: str) -> None:
    """Observe HTTP 503 from the *running* G5 Nginx, never config alone."""
    try:
        response = subprocess.run(
            compose + ["exec", "-T", "nginx", "wget", "-S", "-O", "/dev/null",
                       "-T", "3", url],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError("Cannot verify actual Nginx maintenance response") from exc
    # BusyBox wget returns nonzero for 503; trust the HTTP status line,
    # not the exit status, which could represent a DNS or transport failure.
    lines = (line.strip().split() for line in response.stderr.splitlines())
    if not any(len(parts) >= 2 and parts[0] in {"HTTP/1.0", "HTTP/1.1", "HTTP/2"}
               and parts[1] == "503" for parts in lines):
        raise ProbeError("Running Nginx did not prove maintenance HTTP 503")


CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{12,64}$")


def verify_runtime_writer_restart_policies(containers: list[dict]) -> None:
    """Inspect *actual* Docker restart policy, not only Compose desired config.

    A newly applied overlay can say restart=no while old worker containers still
    carry unless-stopped. Those could relaunch after a crash and write again.
    """
    for row in containers:
        if row.get("Service") not in WRITERS:
            continue
        identity = row.get("ID")
        if not isinstance(identity, str) or not CONTAINER_ID_RE.fullmatch(identity):
            raise ProbeError("Writer container identity is missing or unsafe")
        result = _run([
            "docker", "inspect", "--type", "container",
            "--format", "{{.HostConfig.RestartPolicy.Name}}", identity
        ])
        if result.strip() != "no":
            raise ProbeError(
                f"{row['Service']}: runtime Docker restart policy is not no"
            )


def collect(env_file: Path, compose_files: list[Path], edge_dir: Path) -> list[str]:
    if not env_file.is_file() or any(not p.is_file() for p in compose_files):
        raise ProbeError("Environment or Compose file is missing")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from preflight import read_env  # stdlib-only; do not import app or start workers

    values = read_env(env_file)
    database = values.get("POSTGRES_DB", "")
    user = values.get("POSTGRES_USER", "")
    if not DB_IDENTIFIER.fullmatch(database) or not user:
        raise ProbeError("PostgreSQL identity missing or unsafe")
    app_role = _application_role(values, user)
    cmd = ["docker", "compose", "--env-file", str(env_file)]
    for file in compose_files:
        cmd += ["-f", str(file)]
    config = json.loads(_run(cmd + ["config", "--format", "json"]))
    containers = decode_ps(_run(cmd + ["ps", "--all", "--format", "json"]))
    # A read-only snapshot cannot become a revocable DB writer barrier when
    # the game itself authenticates as PostgreSQL's maintenance superuser.
    _require_unprivileged_app_role(cmd, user, app_role)
    sql = (
        "SELECT (SELECT count(*) FROM pg_stat_activity "
        f"WHERE datname='{database}' AND pid<>pg_backend_pid()), "
        "(SELECT count(*) FROM pg_prepared_xacts "
        f"WHERE database='{database}');"
    )
    counts = _run(cmd + [
        "exec", "-T", "database", "psql", "-X", "-v", "ON_ERROR_STOP=1",
        "-U", user, "-d", "postgres", "-Atqc", sql
    ])
    blockers = inspect(config, containers, counts, edge_dir)
    if blockers:
        return blockers
    # Desired Compose restart=no is insufficient if the existing container
    # still has a persistent restart policy from the previous release.
    verify_runtime_writer_restart_policies(containers)
    # Verify both the HTTP API and a new Socket.IO polling handshake.
    # This still cannot drain pre-existing connections or external writers.
    _require_closed_edge(cmd, "http://127.0.0.1/api/health")
    _require_closed_edge(cmd, "http://127.0.0.1/socket.io/?EIO=4&transport=polling")
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("-f", "--compose-file", type=Path, action="append", required=True)
    parser.add_argument("--edge-dir", type=Path, default=Path(".ops-state/edge-maintenance"))
    args = parser.parse_args()
    try:
        blockers = collect(args.env_file, args.compose_file, args.edge_dir)
    except (ProbeError, ValueError, TypeError, OSError) as exc:
        print(f"G5 DRAIN NO-GO: trustworthy evidence unavailable ({type(exc).__name__})", file=sys.stderr)
        return 2
    if blockers:
        for blocker in blockers:
            print(f"G5 DRAIN NO-GO: {blocker}", file=sys.stderr)
        return 2
    print("G5 DRAIN OBSERVATION PASS: point-in-time only; NOT backup/restore authorization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
