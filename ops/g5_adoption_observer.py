"""Read-only, fail-closed collection of G5 adoption observations.

This module has no production CLI and never authorizes a deployment action.
All external commands use argv, a fixed timeout, bounded output, and an
injectable runner so tests can use disposable fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time
from typing import Callable, Sequence

from ops.g5_adoption_plan import (
    CheckoutObservation,
    ContainerObservation,
    EdgeObservation,
    HostInventory,
    HostObservations,
    ImageObservation,
    MetadataObservation,
    MetadataState,
    ProxyRoute,
    TargetIdentity,
)
from ops.g5_incident_inspect import inspect_incident
from ops.g5_migration_role_identity import RoleSplitError, validate_split
from ops.g5_writer_drain_probe import decode_ps


class ObservationError(RuntimeError):
    """Trustworthy, complete host evidence could not be collected."""


@dataclass(frozen=True)
class ObserverRequest:
    checkout: Path
    env_file: Path
    compose_files: tuple[Path, ...]
    project: str


Runner = Callable[..., str]
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}\Z")
_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SERVICES = frozenset({
    "backend", "frontend", "worker", "database", "nginx", "caddy", "migrate", "seed"
})
_REQUIRED = frozenset({"backend", "frontend", "worker", "database", "nginx", "caddy"})
_MAX_OUTPUT = 4 * 1024 * 1024
_TIMEOUT = 20


def _run(argv: Sequence[str], *, timeout: int, max_output_bytes: int) -> str:
    """Run a bounded argv command without a shell or forwarding diagnostics."""
    process = None
    selector = selectors.DefaultSelector()
    output = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        process = subprocess.Popen(
            list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False, close_fds=True,
        )
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        deadline = time.monotonic() + timeout
        total = 0
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fd, min(65536, max_output_bytes - total + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                total += len(chunk)
                if total > max_output_bytes:
                    raise BufferError
                output[key.data].extend(chunk)
        if process.wait(timeout=max(0.001, deadline - time.monotonic())) != 0:
            raise ObservationError("required read-only observation command returned nonzero")
    except (OSError, subprocess.SubprocessError, TimeoutError, BufferError):
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise ObservationError("required read-only observation command failed or timed out") from None
    finally:
        selector.close()
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
    try:
        return bytes(output["stdout"]).decode("utf-8")
    except UnicodeDecodeError:
        raise ObservationError("read-only observation output is not valid UTF-8") from None


def _command(runner: Runner, *argv: str, limit: int = _MAX_OUTPUT) -> str:
    try:
        output = runner(argv, timeout=_TIMEOUT, max_output_bytes=limit)
    except ObservationError:
        raise
    except Exception:
        raise ObservationError("required read-only observation command failed") from None
    if not isinstance(output, str) or len(output.encode("utf-8", errors="replace")) > limit:
        raise ObservationError("read-only observation output is missing or oversized")
    return output


def _json(raw: str, label: str):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ObservationError(f"{label} observation is malformed") from None


def _compose_argv(request: ObserverRequest) -> list[str]:
    args = [
        "docker", "compose", "--project-name", request.project,
        "--project-directory", str(request.checkout.absolute()),
        "--env-file", str(request.env_file.absolute()),
    ]
    for path in request.compose_files:
        args.extend(("-f", str(path.absolute())))
    return args


def _read_metadata_unlocked(checkout: Path) -> MetadataObservation:
    """Observe release and G5 state without creating files or acquiring a new lock."""
    for transient in (".release.env.next", ".release.env.previous"):
        path = checkout / transient
        if path.exists() or path.is_symlink():
            return MetadataObservation(MetadataState.INCIDENT)
    try:
        if any(name.startswith((".release-sha.", ".release.env.rollback."))
               for name in os.listdir(checkout)):
            return MetadataObservation(MetadataState.INCIDENT)
    except OSError:
        return MetadataObservation(MetadataState.INCIDENT)

    def safe_private_file(path: Path) -> bool:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            return False
        return (
            stat.S_ISREG(info.st_mode) and info.st_uid in (0, os.geteuid())
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
            and info.st_size > 0
        )

    release_path = checkout / ".release-sha"
    try:
        info = release_path.lstat()
    except FileNotFoundError:
        release_sha = None
    except OSError:
        return MetadataObservation(MetadataState.INCIDENT)
    else:
        if (not stat.S_ISREG(info.st_mode) or info.st_size > 128 or info.st_nlink != 1
                or info.st_uid not in (0, os.geteuid())
                or stat.S_IMODE(info.st_mode) != 0o600):
            return MetadataObservation(MetadataState.INCIDENT)
        fd = None
        try:
            fd = os.open(
                release_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            )
            opened = os.fstat(fd)
            before = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            opened_stamp = (
                opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns
            )
            raw = os.read(fd, 129)
            after_fd = os.fstat(fd)
            after_path = release_path.lstat()
            after = (after_path.st_dev, after_path.st_ino, after_path.st_size,
                     after_path.st_mtime_ns)
        except OSError:
            return MetadataObservation(MetadataState.INCIDENT)
        finally:
            if fd is not None:
                os.close(fd)
        after_fd_stamp = (
            after_fd.st_dev, after_fd.st_ino, after_fd.st_size, after_fd.st_mtime_ns
        )
        if (before != opened_stamp or opened_stamp != after_fd_stamp or before != after
                or not stat.S_ISREG(after_fd.st_mode) or after_fd.st_nlink != 1
                or len(raw) != after_fd.st_size):
            return MetadataObservation(MetadataState.INCIDENT)
        release_sha = raw.decode("ascii", errors="ignore").strip()
        if not _SHA.fullmatch(release_sha):
            return MetadataObservation(MetadataState.INCIDENT)

    state_dir = checkout / ".ops-state"
    state_stamp = None
    try:
        state_info = state_dir.lstat()
        if not stat.S_ISDIR(state_info.st_mode) or state_info.st_uid != os.geteuid():
            return MetadataObservation(MetadataState.INCIDENT)
        if stat.S_IMODE(state_info.st_mode) != 0o700:
            return MetadataObservation(MetadataState.INCIDENT)
        state_stamp = (
            state_info.st_dev, state_info.st_ino, state_info.st_mode,
            state_info.st_uid, state_info.st_mtime_ns, state_info.st_ctime_ns,
        )
        names = {path.name for path in state_dir.iterdir()}
    except FileNotFoundError:
        names = set()
    except OSError:
        return MetadataObservation(MetadataState.INCIDENT)
    try:
        after_info = state_dir.lstat()
    except FileNotFoundError:
        if state_stamp is not None:
            return MetadataObservation(MetadataState.INCIDENT)
    except OSError:
        return MetadataObservation(MetadataState.INCIDENT)
    else:
        after_stamp = (
            after_info.st_dev, after_info.st_ino, after_info.st_mode,
            after_info.st_uid, after_info.st_mtime_ns, after_info.st_ctime_ns,
        )
        if state_stamp != after_stamp or not stat.S_ISDIR(after_info.st_mode):
            return MetadataObservation(MetadataState.INCIDENT)
        try:
            if names != {path.name for path in state_dir.iterdir()}:
                return MetadataObservation(MetadataState.INCIDENT)
        except OSError:
            return MetadataObservation(MetadataState.INCIDENT)
    known = {"g5-cutover-activated", "g5-cutover.json", "recovery-required"}
    legacy_names = {"deploy.lock", "releases", "deployments"}
    recognized = known | legacy_names
    unknown_names = {
        name for name in names
        if name not in recognized
        and not name.startswith("recovery-required.")
        and not (name.startswith(".g5-cutover-") and name.endswith(".tmp"))
    }
    if unknown_names:
        return MetadataObservation(MetadataState.INCIDENT)
    has_g5 = bool(names & known) or any(
        name.startswith("recovery-required.") or
        (name.startswith(".g5-cutover-") and name.endswith(".tmp"))
        for name in names
    )
    if names and not has_g5:
        for name in ("releases", "deployments"):
            directory = state_dir / name
            if name in names:
                try:
                    info = directory.lstat()
                except OSError:
                    return MetadataObservation(MetadataState.INCIDENT)
                if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid())
                        or stat.S_IMODE(info.st_mode) != 0o700):
                    return MetadataObservation(MetadataState.INCIDENT)
    if has_g5:
        try:
            evidence = inspect_incident(str(checkout))
        except Exception:
            return MetadataObservation(MetadataState.INCIDENT)
        if evidence.observed_phase is None:
            return MetadataObservation(MetadataState.INCIDENT)
        from ops.g5_cutover_state import CutoverStore, Phase

        # Re-read only under the existing state directory's shared lock. This
        # does not create the state directory or deploy.lock; if either view
        # changed after inspect_incident, treat the metadata as an incident.
        try:
            store = CutoverStore(str(checkout))
            with store._locked(shared=True) as directory:
                manifest, _ = store._load(directory)
        except Exception:
            return MetadataObservation(MetadataState.INCIDENT)
        if (manifest is None or manifest.phase is not evidence.observed_phase
                or manifest.identity.operation_id != evidence.operation_id
                or manifest.phase is not Phase.COMMITTED_WRITERS_ALLOWED):
            return MetadataObservation(MetadataState.INCIDENT)
        try:
            confirmation = inspect_incident(str(checkout))
        except Exception:
            return MetadataObservation(MetadataState.INCIDENT)
        if (confirmation.operation_id != evidence.operation_id
                or confirmation.observed_phase is not evidence.observed_phase):
            return MetadataObservation(MetadataState.INCIDENT)
        return MetadataObservation(
            MetadataState.G5_MANAGED,
            marker_operation_id=evidence.operation_id,
            manifest=manifest,
        )
    current_env = checkout / ".release.env"
    env_exists = current_env.exists() or current_env.is_symlink()
    if release_sha is None:
        if env_exists or bool(names & legacy_names):
            return MetadataObservation(MetadataState.LEGACY_UNMANAGED)
        return MetadataObservation(MetadataState.ABSENT)
    if not safe_private_file(current_env):
        return MetadataObservation(MetadataState.INCIDENT)
    return MetadataObservation(MetadataState.LEGACY_MANAGED, legacy_release_sha=release_sha)


def _read_metadata(checkout: Path) -> MetadataObservation:
    """Read metadata under an existing shared deploy lock, never creating it."""
    state_dir = checkout / ".ops-state"
    lock_path = state_dir / "deploy.lock"
    try:
        before = lock_path.lstat()
    except FileNotFoundError:
        result = _read_metadata_unlocked(checkout)
        return (result if result.state is MetadataState.ABSENT
                else MetadataObservation(MetadataState.INCIDENT))
    except OSError:
        return MetadataObservation(MetadataState.INCIDENT)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid not in (0, os.geteuid())
            or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1):
        return MetadataObservation(MetadataState.INCIDENT)
    fd = None
    try:
        fd = os.open(
            lock_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        )
        opened = os.fstat(fd)
        stamp = (
            before.st_dev, before.st_ino, before.st_mode, before.st_uid,
            before.st_nlink, before.st_size, before.st_mtime_ns, before.st_ctime_ns,
        )
        if stamp != (
            opened.st_dev, opened.st_ino, opened.st_mode, opened.st_uid,
            opened.st_nlink, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns,
        ):
            return MetadataObservation(MetadataState.INCIDENT)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return MetadataObservation(MetadataState.INCIDENT)
        result = _read_metadata_unlocked(checkout)
        current = lock_path.lstat()
        if stamp != (
            current.st_dev, current.st_ino, current.st_mode, current.st_uid,
            current.st_nlink, current.st_size, current.st_mtime_ns, current.st_ctime_ns,
        ):
            return MetadataObservation(MetadataState.INCIDENT)
        return result
    except OSError:
        return MetadataObservation(MetadataState.INCIDENT)
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(fd)


def _container_rows(runner: Runner, request: ObserverRequest) -> list[dict]:
    raw = _command(
        runner, "docker", "ps", "-a", "--no-trunc",
        "--filter", f"label=com.docker.compose.project={request.project}",
        "--format", "{{json .}}",
    )
    rows = decode_ps(raw)
    ids = [row.get("ID") for row in rows]
    if not ids or any(not isinstance(value, str) or not value for value in ids):
        raise ObservationError("Compose container inventory is empty or incomplete")
    inspected = _json(_command(runner, "docker", "inspect", "--type", "container", *ids),
                      "container")
    if not isinstance(inspected, list) or len(inspected) != len(ids):
        raise ObservationError("Compose container inspection is incomplete")
    return inspected


def _compose_environment(config: dict) -> dict[str, str]:
    values: dict[str, str] = {}
    services = config.get("services")
    if not isinstance(services, dict):
        raise ObservationError("effective Compose services are missing")
    for service in ("database", "backend", "worker", "migrate", "seed"):
        spec = services.get(service)
        if not isinstance(spec, dict):
            continue
        environment = _environment_map(spec.get("environment", {}))
        for key, value in environment.items():
            if service == "database":
                values.setdefault(key, value)
            elif key == "DATABASE_URL":
                target = "G5_MIGRATION_DB_URL" if service in {"migrate", "seed"} else "DB_URL"
                values.setdefault(target, value)
    return values


def _environment_map(raw: object) -> dict[str, str]:
    if isinstance(raw, list):
        raw = dict(
            item.split("=", 1) for item in raw
            if isinstance(item, str) and "=" in item
        )
    if not isinstance(raw, dict):
        return {}
    return {
        key: value for key, value in raw.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _restart_matches(desired: str, actual: object) -> bool:
    if not isinstance(actual, dict):
        return False
    expected_name, separator, retries = desired.partition(":")
    if actual.get("Name") != expected_name:
        return False
    try:
        expected_retries = int(retries) if separator else 0
    except ValueError:
        return False
    return type(actual.get("MaximumRetryCount")) is int and (
        actual["MaximumRetryCount"] == expected_retries
    )


def _compose_fingerprint(config: dict, labels: Sequence[dict]) -> str:
    """Hash resolved Compose data and the non-secret runtime provenance labels."""
    payload = {
        "config": config,
        "container_labels": sorted(
            (
                row["com.docker.compose.project"],
                row["com.docker.compose.service"],
                row["com.docker.compose.config-hash"],
                row["com.docker.compose.project.working_dir"],
                row["com.docker.compose.project.config_files"],
                row["com.docker.compose.oneoff"],
            )
            for row in labels
        ),
    }
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


def _network_identity(
    runner: Runner, containers: list[dict], config: dict, project: str
) -> str:
    network_ids: set[str] = set()
    for row in containers:
        settings = row.get("NetworkSettings")
        networks = settings.get("Networks") if isinstance(settings, dict) else None
        if not isinstance(networks, dict) or len(networks) != 1:
            raise ObservationError("container network inventory is incomplete or has a bypass network")
        network = next(iter(networks.values()))
        network_id = network.get("NetworkID") if isinstance(network, dict) else None
        if not isinstance(network_id, str) or not _SHA256.fullmatch(network_id):
            raise ObservationError("container network identity is missing")
        network_ids.add(network_id)
        labels = row.get("Config", {}).get("Labels", {})
        service = labels.get("com.docker.compose.service")
        network_name = next(iter(networks))
        if labels.get(f"com.docker.compose.network") not in (None, "web"):
            raise ObservationError("container network Compose label is unexpected")
        expected_name = config["networks"]["web"].get("name") or f"{project}_web"
        if network_name != expected_name:
            raise ObservationError("container is attached to an unexpected Compose network")
        aliases = network.get("Aliases") if isinstance(network, dict) else None
        if not isinstance(aliases, list) or service not in aliases:
            raise ObservationError("Compose service network alias is unavailable")
    networks = config.get("networks")
    if not isinstance(networks, dict) or set(networks) != {"web"} or len(network_ids) != 1:
        raise ObservationError("effective Compose network topology is unexpected")
    network_id = next(iter(network_ids))
    observed = _json(
        _command(runner, "docker", "network", "inspect", network_id),
        "Docker network",
    )
    if not isinstance(observed, list) or len(observed) != 1:
        raise ObservationError("Docker network inspection is incomplete")
    network = observed[0]
    labels = network.get("Labels") or {}
    running_count = sum(
        row.get("State", {}).get("Running") is True
        for row in containers
    )
    if (network.get("Id") != network_id or network.get("Driver") != "bridge"
            or labels.get("com.docker.compose.project") != project
            or labels.get("com.docker.compose.network") != "web"
            or len(network.get("Containers") or {}) != running_count):
        raise ObservationError("Docker network identity or membership is unexpected")
    return network_id


def _validate_mounts(
    runner: Runner, service: str, row: dict, config: dict, project: str, checkout: Path
) -> str | None:
    actual = row.get("Mounts")
    if not isinstance(actual, list):
        raise ObservationError("container mount inventory is unavailable")
    spec = config["services"][service]
    wanted = spec.get("volumes", [])
    if not isinstance(wanted, list) or len(wanted) != len(actual):
        raise ObservationError("runtime mounts differ from effective Compose mounts")
    by_target = {mount.get("target"): mount for mount in wanted if isinstance(mount, dict)}
    if len(by_target) != len(wanted):
        raise ObservationError("effective Compose mount inventory is malformed")
    volume_id = None
    for mount in actual:
        target = mount.get("Destination")
        expected = by_target.get(target)
        if expected is None:
            raise ObservationError("runtime mount is not declared by effective Compose")
        expected_type = expected.get("type")
        if mount.get("Type") != expected_type:
            raise ObservationError("runtime mount type differs from effective Compose")
        if mount.get("RW") is not (not bool(expected.get("read_only", False))):
            raise ObservationError("runtime mount access differs from effective Compose")
        source = expected.get("source")
        if expected_type == "volume":
            volume_spec = config.get("volumes", {}).get(source, {})
            expected_name = volume_spec.get("name") or f"{project}_{source}"
            if mount.get("Name") != expected_name:
                raise ObservationError("runtime volume differs from effective Compose")
            if target == "/var/lib/postgresql/data":
                volume_id = expected_name
                observed = _json(
                    _command(runner, "docker", "volume", "inspect", expected_name),
                    "PostgreSQL volume",
                )
                if not isinstance(observed, list) or len(observed) != 1:
                    raise ObservationError("PostgreSQL volume inspection is incomplete")
                volume = observed[0]
                labels = volume.get("Labels") or {}
                if (volume.get("Name") != expected_name or volume.get("Driver") != "local"
                        or labels.get("com.docker.compose.project") != project
                        or labels.get("com.docker.compose.volume") != source):
                    raise ObservationError("PostgreSQL volume identity or provenance is unexpected")
        elif expected_type == "bind":
            try:
                source_path = Path(source)
                resolved = str(
                    source_path.resolve() if source_path.is_absolute()
                    else (checkout / source_path).resolve()
                )
            except (TypeError, OSError):
                raise ObservationError("effective bind mount source is malformed") from None
            if mount.get("Source") != resolved:
                raise ObservationError("runtime bind mount differs from effective Compose")
        else:
            raise ObservationError("unsupported effective Compose mount type")
    return volume_id


def _image_observations(runner: Runner, rows: list[dict], checkout_sha: str) -> tuple[ImageObservation, ...]:
    result: dict[str, ImageObservation] = {}
    for row in rows:
        labels = row.get("Config", {}).get("Labels") or {}
        service = labels.get("com.docker.compose.service")
        if service not in {"backend", "frontend", "worker"}:
            continue
        image_id = row.get("Image")
        if not isinstance(image_id, str) or not _SHA256.fullmatch(image_id.removeprefix("sha256:")):
            raise ObservationError("runtime image identity is missing")
        image_data = _json(_command(runner, "docker", "image", "inspect", image_id), "image")
        if not isinstance(image_data, list) or len(image_data) != 1:
            raise ObservationError("runtime image provenance is incomplete")
        image = image_data[0]
        image_config = image.get("Config") or {}
        image_labels = image_config.get("Labels") or {}
        source_sha = image_labels.get("org.opencontainers.image.revision")
        digests = image.get("RepoDigests")
        matching = [value for value in digests or [] if isinstance(value, str) and "@sha256:" in value]
        if (not isinstance(source_sha, str) or source_sha != checkout_sha or
                len(matching) != 1 or image.get("Id") != image_id):
            raise ObservationError("runtime image digest or source provenance is unverifiable")
        result[service] = ImageObservation(service, matching[0], image_id, source_sha)
    if set(result) != {"backend", "frontend", "worker"}:
        raise ObservationError("backend, frontend, and worker image evidence is incomplete")
    return tuple(result[name] for name in ("backend", "frontend", "worker"))


def _pg_snapshot(
    runner: Runner, rows: list[dict], values: dict[str, str]
) -> tuple[str, int, str, str, str]:
    db_row = next(
        (row for row in rows
         if (row.get("Config", {}).get("Labels") or {}).get("com.docker.compose.service")
         == "database"),
        None,
    )
    app_row = next(
        (row for row in rows
         if (row.get("Config", {}).get("Labels") or {}).get("com.docker.compose.service")
         == "backend"),
        None,
    )
    if db_row is None or app_row is None:
        raise ObservationError("PostgreSQL or application container is missing")
    maintenance = values.get("POSTGRES_USER", "")
    database = values.get("POSTGRES_DB", "")
    if not _IDENTIFIER.fullmatch(maintenance) or not _IDENTIFIER.fullmatch(database):
        raise ObservationError("effective PostgreSQL identity is missing or unsafe")
    sql = (
        "SET TRANSACTION READ ONLY; "
        "SELECT json_build_array(current_user, current_database(), "
        "(SELECT oid FROM pg_database WHERE datname=current_database()), "
        "(SELECT system_identifier::text FROM pg_control_system()), "
        "current_setting('server_version_num'))::text;"
    )
    output = _command(
        runner, "docker", "exec", "-i", db_row["Id"], "psql", "-X", "-1", "-q",
        "-v", "ON_ERROR_STOP=1", "-U", maintenance, "-d", database, "-Atqc", sql,
    ).strip()
    admin = _json(output, "PostgreSQL maintenance connection")
    if (not isinstance(admin, list) or len(admin) != 5 or admin[0] != maintenance
            or admin[1] != database or type(admin[2]) is not int
            or not isinstance(admin[3], str) or not admin[3].isdigit()
            or not str(admin[4]).startswith("15")):
        raise ObservationError("effective PostgreSQL maintenance identity is unverified")

    app_python = (
        "import json,os; from sqlalchemy import create_engine; "
        "e=create_engine(os.environ['DATABASE_URL'],connect_args={'connect_timeout':3}); "
        "c=e.connect(); c.exec_driver_sql('SET TRANSACTION READ ONLY'); "
        "r=c.exec_driver_sql(\"SELECT current_user,session_user,current_database(),"
        "(SELECT oid FROM pg_database WHERE datname=current_database()),"
        "(SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls "
        "FROM pg_roles WHERE rolname=current_user),"
        "EXISTS (SELECT 1 FROM pg_roles p WHERE (p.rolsuper OR p.rolname IN "
        "('pg_write_all_data','pg_read_all_data','pg_execute_server_program',"
        "'pg_read_server_files','pg_write_server_files')) "
        "AND pg_has_role(current_user,p.oid,'MEMBER'))\").one(); "
        "print(json.dumps(list(r))); c.close(); e.dispose()"
    )
    app_output = _command(
        runner, "docker", "exec", app_row["Id"], "python", "-c", app_python,
    ).strip()
    app = _json(app_output, "application PostgreSQL connection")
    try:
        split = validate_split(values)
    except (RoleSplitError, TypeError, ValueError):
        raise ObservationError("effective application/maintenance role split is invalid") from None
    if (not isinstance(app, list) or len(app) != 6 or app[0] != split.application
            or app[1] != split.application or app[2] != database or app[3] != admin[2]
            or app[4] is not False or app[5] is not False):
        raise ObservationError("effective application database identity is unverified")

    # Hash only the schema-only dump. Never return or print SQL or user data.
    dump = _command(
        runner, "docker", "exec", "-i", db_row["Id"], "pg_dump", "--schema-only",
        "--no-owner", "--no-privileges", "-U", maintenance, "-d", database,
        limit=_MAX_OUTPUT,
    )
    schema_sha = hashlib.sha256(dump.encode("utf-8")).hexdigest()
    return database, admin[2], schema_sha, admin[3], split.application


def _caddy_routes(config: dict) -> tuple[dict, ...]:
    apps = config.get("apps")
    http = apps.get("http") if isinstance(apps, dict) else None
    servers = http.get("servers") if isinstance(http, dict) else None
    if not isinstance(servers, dict) or len(servers) != 1:
        raise ObservationError("loaded Caddy server inventory is incomplete")
    server = next(iter(servers.values()))
    if not isinstance(server, dict) or not isinstance(server.get("routes"), list):
        raise ObservationError("loaded Caddy route inventory is incomplete")
    found: list[dict] = []

    def visit(routes: list[dict]) -> None:
        for route in routes:
            if not isinstance(route, dict):
                raise ObservationError("loaded Caddy route is malformed")
            paths = []
            for matcher in route.get("match", []):
                if not isinstance(matcher, dict):
                    raise ObservationError("loaded Caddy matcher is malformed")
                if "path" in matcher:
                    value = matcher["path"]
                    if not isinstance(value, list):
                        raise ObservationError("loaded Caddy path matcher is malformed")
                    paths.extend(value)
                elif set(matcher) != {"host"}:
                    raise ObservationError("loaded Caddy route uses an unverified matcher")
            path = "/" if not paths else paths[0] if len(paths) == 1 else None
            if path != "/":
                raise ObservationError("loaded Caddy route contains a bypass path")
            handlers = route.get("handle")
            if not isinstance(handlers, list) or not handlers:
                raise ObservationError("loaded Caddy route has no handlers")
            for handler in handlers:
                if not isinstance(handler, dict):
                    raise ObservationError("loaded Caddy handler is malformed")
                kind = handler.get("handler")
                if kind == "reverse_proxy":
                    upstreams = handler.get("upstreams")
                    if not isinstance(upstreams, list) or len(upstreams) != 1:
                        raise ObservationError("loaded Caddy upstream inventory is incomplete")
                    dial = upstreams[0].get("dial") if isinstance(upstreams[0], dict) else None
                    found.append({"path": path, "dial": dial})
                elif kind == "subroute":
                    nested = handler.get("routes")
                    if not isinstance(nested, list):
                        raise ObservationError("loaded Caddy subroute is malformed")
                    visit(nested)
                elif kind not in {"headers", "encode"}:
                    raise ObservationError("loaded Caddy route has an unverified terminal handler")

    visit(server["routes"])
    if len(found) != 1:
        raise ObservationError("loaded Caddy route inventory is incomplete or has a bypass")
    return tuple(found)


def _runtime_routes(
    runner: Runner, caddy: dict, _nginx: dict, _services: dict[str, dict]
) -> EdgeObservation:
    caddy_id = caddy["Id"]
    # Caddy's admin endpoint reports its currently loaded config. The Compose
    # Caddyfile sets admin off; that is deliberately a blocker, not evidence.
    caddy_raw = _command(
        runner, "docker", "exec", caddy_id, "wget", "-qO-",
        "http://127.0.0.1:2019/config/",
    )
    caddy_config = _json(caddy_raw, "live Caddy configuration")
    if not isinstance(caddy_config, dict):
        raise ObservationError("live Caddy configuration is unavailable")
    # Caddy's admin JSON is its live adapted runtime configuration. Resolve
    # the Compose DNS target only after checking it is the sole proxy upstream.
    caddy_routes = _caddy_routes(caddy_config)
    if caddy_routes[0].get("dial") != "nginx:80":
        raise ObservationError("loaded Caddy route bypasses or differs from Nginx")
    # Nginx has no read-only API for its in-memory configuration here.
    # `nginx -T`, a file hash, a route response, or an endpoint-supplied
    # "loaded-runtime" string cannot authenticate what its workers loaded.
    raise ObservationError(
        "Nginx loaded configuration cannot be authenticated with a read-only runtime interface"
    )


def _collect_once(request: ObserverRequest, runner: Runner) -> HostInventory:
    checkout = request.checkout.absolute()
    if (not checkout.is_dir() or checkout.is_symlink()
            or not request.env_file.is_file() or request.env_file.is_symlink()
            or not request.compose_files or any(
                not path.is_file() or path.is_symlink() for path in request.compose_files
            )
            or not _PROJECT.fullmatch(request.project)):
        raise ObservationError("checkout, environment, Compose files, or project is invalid")
    sha = _command(runner, "git", "-C", str(checkout), "rev-parse", "--verify", "HEAD").strip()
    status = _command(
        runner, "git", "-C", str(checkout), "status", "--porcelain=v1",
        "--untracked-files=all",
    )
    if not _SHA.fullmatch(sha) or status:
        raise ObservationError("checkout is not an exact clean revision")

    compose = _compose_argv(request)
    raw_config = _command(runner, *compose, "config", "--format", "json")
    config = _json(raw_config, "effective Compose configuration")
    if (not isinstance(config, dict) or config.get("name") != request.project
            or not isinstance(config.get("services"), dict)
            or set(config["services"]) != _SERVICES):
        raise ObservationError("effective Compose service topology is incomplete or unexpected")
    for service, spec in config["services"].items():
        if not isinstance(spec, dict) or spec.get("ports"):
            raise ObservationError("effective Compose contains a port exposure or malformed service")

    rows = _container_rows(runner, request)
    service_rows: dict[str, dict] = {}
    ids = set()
    compose_labels = []
    for row in rows:
        labels = row.get("Config", {}).get("Labels")
        if not isinstance(labels, dict):
            raise ObservationError("container Compose labels are unavailable")
        service = labels.get("com.docker.compose.service")
        expected_files = ",".join(str(path.absolute()) for path in request.compose_files)
        if (labels.get("com.docker.compose.project") != request.project
                or service not in _SERVICES or service in service_rows):
            raise ObservationError("orphaned, unknown, or duplicate Compose container detected")
        if (labels.get("com.docker.compose.project.working_dir") != str(checkout)
                or labels.get("com.docker.compose.project.config_files") != expected_files):
            raise ObservationError("container Compose origin labels differ from this checkout")
        config_hash = labels.get("com.docker.compose.config-hash")
        oneoff = labels.get("com.docker.compose.oneoff")
        if (not isinstance(config_hash, str) or not _SHA256.fullmatch(config_hash)
                or oneoff not in {"True", "False"}):
            raise ObservationError("container Compose labels are incomplete or malformed")
        compose_labels.append(labels)
        identity = row.get("Id")
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise ObservationError("container identity is missing")
        if identity in ids:
            raise ObservationError("duplicate container identity detected")
        ids.add(identity)
        service_rows[service] = row
        service_config = config["services"][service]
        desired_image = service_config.get("image")
        if desired_image is not None and row.get("Config", {}).get("Image") != desired_image:
            raise ObservationError("runtime image reference differs from effective Compose")
        expected_env = _environment_map(service_config.get("environment", {}))
        actual_env = _environment_map(row.get("Config", {}).get("Env"))
        if any(actual_env.get(key) != value for key, value in expected_env.items()):
            raise ObservationError("runtime environment differs from effective Compose")
        desired_restart = service_config.get("restart", "no")
        actual_restart = (row.get("HostConfig") or {}).get("RestartPolicy")
        if not isinstance(desired_restart, str) or not _restart_matches(desired_restart, actual_restart):
            raise ObservationError("runtime restart policy differs from effective Compose")
        host_config = row.get("HostConfig") or {}
        if host_config.get("PortBindings"):
            raise ObservationError("container has a host-published port")
        ports = row.get("NetworkSettings", {}).get("Ports") or {}
        if any(bindings for bindings in ports.values() if bindings):
            raise ObservationError("container has an exposed host port")
    if not _REQUIRED.issubset(service_rows):
        raise ObservationError("required Compose containers are missing")

    # This fingerprint includes interpolated environment values, including
    # credentials, and the observed Compose provenance labels. Never log the
    # digest or accompany it with the resolved configuration.
    compose_sha = _compose_fingerprint(config, compose_labels)
    network_id = _network_identity(runner, rows, config, request.project)
    values = _compose_environment(config)
    database, database_oid, schema_sha, system_id, app_role = _pg_snapshot(
        runner, rows, values
    )
    images = _image_observations(runner, rows, sha)
    image_map = {image.service: image for image in images}
    if (image_map["backend"].image_id != image_map["worker"].image_id
            or image_map["backend"].reference != image_map["worker"].reference):
        raise ObservationError("backend and worker runtime images diverge")

    volume_id = None
    containers = []
    for service, row in service_rows.items():
        state = row.get("State") or {}
        running = state.get("Running")
        if type(running) is not bool:
            raise ObservationError("container runtime state is unavailable")
        restart = (row.get("HostConfig") or {}).get("RestartPolicy", {}).get("Name")
        if restart not in {"no", "always", "unless-stopped", "on-failure"}:
            raise ObservationError("container restart policy is unavailable")
        if service in _REQUIRED and running is not True:
            raise ObservationError("required Compose service is not running")
        if service in {"migrate", "seed"} and (running is not False or restart != "no"):
            raise ObservationError("one-shot Compose container is active or restartable")
        container_volume = None
        container_volume = _validate_mounts(
            runner, service, row, config, request.project, checkout
        )
        if service == "database":
            volume_id = container_volume
            if volume_id is None:
                raise ObservationError("PostgreSQL data volume is missing")
        containers.append(ContainerObservation(
            service, row["Id"], request.project, network_id, running, restart,
            row.get("Image") if service in {"backend", "worker", "frontend"} else None,
            container_volume,
        ))
    if volume_id is None:
        raise ObservationError("PostgreSQL volume identity is unavailable")

    caddy, nginx = service_rows["caddy"], service_rows["nginx"]
    edge = _runtime_routes(runner, caddy, nginx, service_rows)
    metadata = _read_metadata(checkout)
    if metadata.state is MetadataState.INCIDENT:
        raise ObservationError("G5 or legacy release metadata is unsafe or inconsistent")
    identity = TargetIdentity(
        request.project, compose_sha, network_id, volume_id, database, database_oid,
        schema_sha, sha, app_role, values["POSTGRES_USER"], caddy["Id"], system_id,
    )
    if (metadata.state is MetadataState.LEGACY_MANAGED
            and metadata.legacy_release_sha != sha):
        raise ObservationError("managed release metadata differs from the clean checkout")
    if metadata.state is MetadataState.G5_MANAGED:
        manifest = metadata.manifest
        if (manifest is None or manifest.identity.compose_project != request.project
                or manifest.identity.postgres_db != database
                or manifest.identity.candidate_sha != sha):
            raise ObservationError("G5 release receipt differs from the observed host identity")
    return HostInventory(
        CheckoutObservation(sha, True), identity, images, tuple(containers), metadata, edge
    )


def observe(
    request: ObserverRequest,
    *,
    runner: Runner = _run,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> HostObservations:
    """Collect two complete independent inventories, rejecting any drift."""
    if not isinstance(request, ObserverRequest):
        raise ObservationError("observer request is missing or malformed")
    try:
        start = clock()
        before = _collect_once(request, runner)
        after = _collect_once(request, runner)
        end = clock()
    except ObservationError:
        raise
    except Exception:
        raise ObservationError("host inventory is incomplete or malformed") from None
    if (not isinstance(start, datetime) or not isinstance(end, datetime)
            or start.tzinfo is None or end.tzinfo is None
            or start.utcoffset() is None or end.utcoffset() is None or end < start):
        raise ObservationError("observation timestamps are invalid")
    observations = HostObservations(before, after, start, end)
    if before != after:
        raise ObservationError("host inventory drifted during independent observation")
    return observations
