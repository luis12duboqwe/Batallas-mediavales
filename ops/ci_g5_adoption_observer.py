"""Disposable GitHub-hosted Docker rehearsal for the G5 partial observer."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4

from ops import g5_adoption_observer as observer


_OWNER_LABEL = "medievol.g5.adoption-fixture"
_ID = re.compile(r"[0-9a-f]{64}\Z")
_MAX_OUTPUT = 4 * 1024 * 1024


def _docker(
    args: list[str], *, timeout: int = 120, capture: bool = True,
    input_data: bytes | None = None,
) -> str:
    if not args:
        raise RuntimeError("empty fixture command")
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith(("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_CERT_PATH")):
            environment.pop(key, None)
    try:
        command = [
            "docker", "--host", "unix:///var/run/docker.sock", *args,
        ]
        run_options = {
            "stdout": subprocess.PIPE if capture else subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "text": False,
            "shell": False,
            "close_fds": True,
            "timeout": timeout,
            "check": False,
            "env": environment,
        }
        if input_data is None:
            run_options["stdin"] = subprocess.DEVNULL
        else:
            run_options["input"] = input_data
        result = subprocess.run(
            command,
            **run_options,
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("owned G5 fixture Docker command failed or timed out") from None
    if result.returncode:
        raise RuntimeError("owned G5 fixture Docker command returned nonzero")
    if not capture:
        return ""
    if len(result.stdout) > _MAX_OUTPUT:
        raise RuntimeError("owned G5 fixture Docker output exceeded its bound")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise RuntimeError("owned G5 fixture Docker output was not UTF-8") from None


def _ids(kind: str, project: str) -> list[str]:
    if kind == "container":
        args = ["ps", "--all", "--no-trunc", "--filter", f"label={_OWNER_LABEL}={project}",
                "--format", "{{.ID}}"]
    elif kind == "network":
        args = ["network", "ls", "--no-trunc", "--filter", f"label={_OWNER_LABEL}={project}",
                "--format", "{{.ID}}"]
    elif kind == "volume":
        args = ["volume", "ls", "--filter", f"label={_OWNER_LABEL}={project}",
                "--format", "{{.Name}}"]
    elif kind == "image":
        args = ["image", "ls", "--no-trunc", "--filter", f"label={_OWNER_LABEL}={project}",
                "--format", "{{.ID}}"]
    else:
        raise RuntimeError("unsupported owned fixture resource type")
    values = _docker(args).splitlines()
    if len(set(values)) != len(values) or any(not item for item in values):
        raise RuntimeError("owned G5 fixture resource inventory is malformed")
    valid_id = _ID.fullmatch if kind != "image" else lambda item: re.fullmatch(
        r"sha256:[0-9a-f]{64}", item
    )
    if kind != "volume" and any(not valid_id(item) for item in values):
        raise RuntimeError("owned G5 fixture resource identity is malformed")
    return values


def _cleanup(project: str) -> None:
    """Remove only resources discovered with this fixture's unique owner label."""
    containers = _ids("container", project)
    for identity in containers:
        rows = json.loads(_docker(["inspect", "--type", "container", identity]))
        if (not isinstance(rows, list) or len(rows) != 1
                or rows[0].get("Id") != identity
                or (rows[0].get("Config", {}).get("Labels") or {}).get(_OWNER_LABEL) != project):
            raise RuntimeError("refusing to clean an unowned fixture container")
    if containers:
        _docker(["rm", "--force", *containers], capture=False)
    if _ids("container", project):
        raise RuntimeError("owned G5 fixture containers survived cleanup")

    networks = _ids("network", project)
    for identity in networks:
        rows = json.loads(_docker(["network", "inspect", identity]))
        if (not isinstance(rows, list) or len(rows) != 1
                or rows[0].get("Id") != identity
                or (rows[0].get("Labels") or {}).get(_OWNER_LABEL) != project):
            raise RuntimeError("refusing to clean an unowned fixture network")
    if networks:
        _docker(["network", "rm", *networks], capture=False)
    if _ids("network", project):
        raise RuntimeError("owned G5 fixture networks survived cleanup")

    volumes = _ids("volume", project)
    for name in volumes:
        rows = json.loads(_docker(["volume", "inspect", name]))
        if (not isinstance(rows, list) or len(rows) != 1
                or rows[0].get("Name") != name
                or (rows[0].get("Labels") or {}).get(_OWNER_LABEL) != project):
            raise RuntimeError("refusing to clean an unowned fixture volume")
    if volumes:
        _docker(["volume", "rm", *volumes], capture=False)
    if _ids("volume", project):
        raise RuntimeError("owned G5 fixture volumes survived cleanup")

    images = _ids("image", project)
    for identity in images:
        rows = json.loads(_docker(["image", "inspect", identity]))
        if (not isinstance(rows, list) or len(rows) != 1
                or rows[0].get("Id") != identity
                or (rows[0].get("Config", {}).get("Labels") or {}).get(_OWNER_LABEL) != project):
            raise RuntimeError("refusing to clean an unowned fixture image")
    if images:
        _docker(["image", "rm", *images], capture=False)
    if _ids("image", project):
        raise RuntimeError("owned G5 fixture images survived cleanup")


def _compose_file(root: Path, project: str, sha: str) -> tuple[Path, Path]:
    dockerfile = root / "Dockerfile"
    dockerfile.write_text(
        "FROM python:3.11-slim\n"
        "ARG SOURCE_SHA\n"
        "RUN pip install --no-cache-dir 'SQLAlchemy==2.0.35' 'psycopg[binary]==3.2.3'\n"
        "LABEL org.opencontainers.image.revision=${SOURCE_SHA}\n"
        f"LABEL {_OWNER_LABEL}={project}\n",
        encoding="ascii",
    )
    app_sleep = ["python", "-c", "import time; time.sleep(3600)"]
    no_op = ["python", "-c", "pass"]
    compose = {
        "services": {
            "database": {
                "image": "postgres:15-alpine",
                "restart": "unless-stopped",
                "environment": {
                    "POSTGRES_USER": "${POSTGRES_USER:?required}",
                    "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD:?required}",
                    "POSTGRES_DB": "${POSTGRES_DB:?required}",
                },
                "volumes": [
                    {"type": "volume", "source": "postgres-data",
                     "target": "/var/lib/postgresql/data"},
                ],
                "healthcheck": {
                    "test": ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"],
                    "interval": "2s", "timeout": "2s", "retries": 30,
                },
                "networks": ["web"],
                "labels": {_OWNER_LABEL: project},
            },
            "migrate": {
                "build": {"context": str(root), "args": {"SOURCE_SHA": sha}},
                "image": f"{project}-backend:fixture",
                "command": no_op,
                "restart": "no",
                "environment": {
                    "DATABASE_URL": "${G5_MIGRATION_DB_URL:?required}",
                },
                "networks": ["web"],
                "labels": {_OWNER_LABEL: project},
            },
            "seed": {
                "build": {"context": str(root), "args": {"SOURCE_SHA": sha}},
                "image": f"{project}-backend:fixture",
                "command": no_op,
                "restart": "no",
                "environment": {
                    "DATABASE_URL": "${G5_MIGRATION_DB_URL:?required}",
                },
                "networks": ["web"],
                "labels": {_OWNER_LABEL: project},
            },
            "backend": {
                "build": {"context": str(root), "args": {"SOURCE_SHA": sha}},
                "image": f"{project}-backend:fixture",
                "command": app_sleep,
                "restart": "unless-stopped",
                "environment": {
                    "DATABASE_URL": "${DB_URL:?required}",
                },
                "networks": ["web"],
                "labels": {_OWNER_LABEL: project},
            },
            "worker": {
                "build": {"context": str(root), "args": {"SOURCE_SHA": sha}},
                "image": f"{project}-backend:fixture",
                "command": app_sleep,
                "restart": "unless-stopped",
                "environment": {
                    "DATABASE_URL": "${DB_URL:?required}",
                },
                "networks": ["web"],
                "labels": {_OWNER_LABEL: project},
            },
            "frontend": {
                "image": "nginx:1.28-alpine",
                "restart": "unless-stopped",
                "networks": ["web"],
                "labels": {_OWNER_LABEL: project},
            },
            "nginx": {
                "image": "nginx:1.28-alpine",
                "restart": "unless-stopped",
                "volumes": [
                    {"type": "bind", "source": str(root / "nginx.conf"),
                     "target": "/etc/nginx/nginx.conf", "read_only": True},
                ],
                "networks": ["web"],
                "labels": {_OWNER_LABEL: project},
            },
            "caddy": {
                "image": "caddy:2.10.2-alpine",
                "restart": "unless-stopped",
                "volumes": [
                    {"type": "bind", "source": str(root / "Caddyfile"),
                     "target": "/etc/caddy/Caddyfile", "read_only": True},
                    {"type": "volume", "source": "caddy-data", "target": "/data"},
                    {"type": "volume", "source": "caddy-config", "target": "/config"},
                ],
                "networks": ["web"],
                "labels": {_OWNER_LABEL: project},
            },
        },
        "volumes": {
            "postgres-data": {"labels": {_OWNER_LABEL: project}},
            "caddy-data": {"labels": {_OWNER_LABEL: project}},
            "caddy-config": {"labels": {_OWNER_LABEL: project}},
        },
        "networks": {"web": {"driver": "bridge", "labels": {_OWNER_LABEL: project}}},
    }
    compose_path = root / "compose.yml"
    compose_path.write_text(json.dumps(compose, sort_keys=True), encoding="utf-8")
    env_file = root / "fixture.env"
    env_file.touch(mode=0o600)
    env_file.chmod(0o600)
    return compose_path, env_file



_EXPECTED_PARTIAL_BLOCKERS = frozenset({
    "immutable image digest or provenance observation is incomplete",
    "Nginx loaded configuration cannot be authenticated with a read-only runtime interface",
})


def _assert_partial_observations(observed, sha: str) -> None:
    """Do not treat a repeatable observation failure as a successful rehearsal."""
    if (observed.before != observed.after
            or observed.before.checkout.commit_sha != sha
            or observed.before.caddy_routes != ("/",)
            or observed.after.caddy_routes != ("/",)
            or set(observed.before.blockers) != _EXPECTED_PARTIAL_BLOCKERS
            or set(observed.after.blockers) != _EXPECTED_PARTIAL_BLOCKERS
            or set(observed.blockers) != _EXPECTED_PARTIAL_BLOCKERS):
        raise RuntimeError("live disposable inventory failed required partial evidence assertions")



def _clone_fixture_checkout(source: Path, target: Path, sha: str) -> None:
    """A fresh local checkout cannot inherit another drill's ignored incident state."""
    if target.exists() or target.is_symlink() or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("invalid isolated fixture checkout")
    try:
        for args in (
            ["git", "clone", "--local", "--shared", "--no-checkout", "--", str(source), str(target)],
            ["git", "-C", str(target), "checkout", "--detach", sha],
        ):
            subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, shell=False, timeout=60, check=True)
        actual = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--verify", "HEAD"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, shell=False, timeout=10, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("isolated fixture checkout failed") from None
    if actual != sha or observer._read_metadata(target).state is not observer.MetadataState.ABSENT:
        raise RuntimeError("isolated fixture checkout identity or release metadata invalid")


def run() -> None:
    """Create, observe, adversarially mutate, and clean up only a CI fixture."""
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or not workspace or Path(workspace).resolve() != Path(__file__).resolve().parents[1]
            or not Path("/var/run/docker.sock").is_socket()):
        raise RuntimeError("live G5 observer rehearsal requires GitHub CI's local Docker socket")
    project = "bm-g5-adoption-" + uuid4().hex
    if _ids("container", project) or _ids("network", project) or _ids("volume", project):
        raise RuntimeError("unique G5 fixture project unexpectedly already exists")
    root = Path(tempfile.mkdtemp(prefix=project + "-", dir=workspace)).resolve()
    app_password = secrets.token_hex(24)
    fixture_env = {
        "POSTGRES_USER": "game_admin",
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "POSTGRES_DB": "game_db",
    }
    fixture_env["DB_URL"] = (
        f"postgresql+psycopg://game_app:{app_password}@database:5432/game_db"
    )
    fixture_env["G5_MIGRATION_DB_URL"] = (
        "postgresql+psycopg://game_admin:" + fixture_env["POSTGRES_PASSWORD"]
        + "@database:5432/game_db"
    )
    saved_environment = {key: os.environ.get(key) for key in fixture_env}
    try:
        os.environ.update(fixture_env)
        root.chmod(0o700)
        sha = subprocess.run(
            ["git", "-C", workspace, "rev-parse", "--verify", "HEAD"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, shell=False, timeout=10, check=True,
        ).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise RuntimeError("GitHub checkout revision is invalid")
        checkout = root / "checkout"
        _clone_fixture_checkout(Path(workspace), checkout, sha)
        # Keep the Docker build context independent of the clone and .git.
        config_root = root / "fixture"
        config_root.mkdir(mode=0o700)
        (config_root / "nginx.conf").write_text(
            "events {}\nhttp { server { listen 80; location / { return 200 'fixture'; } } }\n",
            encoding="ascii",
        )
        (config_root / "Caddyfile").write_text(
            "{\n    admin 0.0.0.0:2019\n    auto_https off\n}\n"
            ":80 {\n    reverse_proxy nginx:80\n}\n",
            encoding="ascii",
        )
        compose_path, env_file = _compose_file(config_root, project, sha)
        prefix = [
            "compose", "--project-name", project, "--project-directory", str(checkout),
            "--env-file", str(env_file), "-f", str(compose_path),
        ]
        _docker([*prefix, "build", "backend", "worker", "migrate", "seed"],
                timeout=300, capture=False)
        _docker([*prefix, "up", "--detach", "--no-build"], timeout=300, capture=False)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                identity = _docker([
                    *prefix, "exec", "--no-TTY", "database", "psql", "-X", "-q",
                    "-U", "game_admin", "-d", "game_db", "-Atqc",
                    "SELECT current_user || '|' || current_database()",
                ]).strip()
                if identity == "game_admin|game_db":
                    break
                time.sleep(1)
            except RuntimeError:
                time.sleep(1)
        else:
            raise RuntimeError("disposable PostgreSQL container did not start")
        _docker([
            *prefix, "exec", "--no-TTY", "database", "psql", "-X",
            "-v", "ON_ERROR_STOP=1", "-U", "game_admin", "-d", "game_db", "-f", "-",
        ], capture=False, input_data=(
            f"CREATE ROLE game_app LOGIN PASSWORD '{app_password}';\n".encode("ascii")
        ))
        for service, command in (
            ("nginx", ["wget", "-qO-", "http://127.0.0.1/"]),
            ("caddy", ["wget", "-qO-", "http://127.0.0.1:2019/config/"]),
        ):
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    if _docker([
                        *prefix, "exec", "--no-TTY", service, *command,
                    ]).strip():
                        break
                except RuntimeError:
                    time.sleep(1)
            else:
                raise RuntimeError(f"disposable {service} fixture service did not become ready")

        request = observer.ObserverRequest(
            checkout, env_file, (compose_path,), project
        )
        observed = observer.observe_partial(request, runner=observer._run)
        _assert_partial_observations(observed, sha)

        worker = next(
            row for row in observer._container_rows(observer._run, request)
            if (row.get("Config", {}).get("Labels") or {}).get(
                "com.docker.compose.service"
            ) == "worker"
        )
        network = observed.before.identity.network_id
        _docker(["network", "disconnect", network, worker["Id"]], capture=False)
        try:
            observer.observe_partial(request, runner=observer._run)
        except observer.ObservationError:
            pass
        else:
            raise RuntimeError("live network mutation was not rejected by the observer")
        print("G5 partial adoption: two independent Compose/PG15 observations and network drift rejection verified; full edge/provenance remains NO-GO", flush=True)
    finally:
        try:
            _cleanup(project)
        finally:
            for key, value in saved_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    run()
