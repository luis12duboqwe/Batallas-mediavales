"""Disposable CI rehearsal of the controlled Caddy → Nginx → app edge."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from ops.g5_edge_provenance import (
    ContainerContract,
    ProvenanceError,
    fixed_config,
    read_config,
    sha256,
    verify_container,
    verify_network,
)


_CADDY = "caddy:2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d"
_NGINX = "nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236"
_FIXTURE = re.compile(r"bm-g5-edge-provenance-[0-9a-f]{32}")
_ID = re.compile(r"[0-9a-f]{64}")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_FRONTEND_CONF = b"""worker_processes 1;
error_log /dev/stderr notice;
pid /tmp/nginx.pid;
events { worker_connections 128; }
http {
    access_log /dev/stdout;
    server {
        listen 8081;
        server_name _;
        root /usr/share/nginx/html;
        index index.html;
        location = /health { default_type text/plain; return 200 "ok\\n"; }
        location / { try_files $uri $uri/ /index.html; }
    }
}
"""
_APP_PROBE = r'''
import json
import urllib.request

def get(path):
    with urllib.request.urlopen("http://caddy:8080" + path, timeout=5) as response:
        return response.status, response.read()

status, body = get("/health")
assert status == 200 and body == b"ok\n", (status, body)
status, body = get("/api/health")
assert status == 200 and json.loads(body) == {"status": "ok"}, (status, body)
status, body = get("/")
assert status == 200 and b"<html" in body.lower(), (status, body[:100])
print("HTTP, API, and frontend route checks passed")
'''
_SOCKET_IO_PROBE = r'''
import base64
import hashlib
import json
import os
import socket
import struct

def recv_exact(conn, count):
    data = b""
    while len(data) < count:
        chunk = conn.recv(count - len(data))
        if not chunk:
            raise RuntimeError("truncated WebSocket frame")
        data += chunk
    return data

def recv_frame(conn):
    first, second = recv_exact(conn, 2)
    length = second & 127
    if length == 126:
        length = struct.unpack("!H", recv_exact(conn, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", recv_exact(conn, 8))[0]
    payload = recv_exact(conn, length)
    if second & 128:
        mask = recv_exact(conn, 4)
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return first & 15, payload

def send_text(conn, value):
    payload = value.encode()
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    prefix = bytes([0x81])
    if len(payload) < 126:
        prefix += bytes([0x80 | len(payload)])
    elif len(payload) < 65536:
        prefix += bytes([0x80 | 126]) + struct.pack("!H", len(payload))
    else:
        raise RuntimeError("unexpectedly large Socket.IO message")
    conn.sendall(prefix + mask + masked)

with socket.create_connection(("caddy", 8080), timeout=5) as conn:
    conn.settimeout(10)
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    conn.sendall(
        b"GET /socket.io/?EIO=4&transport=websocket HTTP/1.1\r\n"
        b"Host: caddy:8080\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n"
        b"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: " + key.encode() + b"\r\n\r\n"
    )
    response = bytearray()
    while b"\r\n\r\n" not in response:
        response.extend(conn.recv(1))
        if len(response) > 16384:
            raise RuntimeError("oversized WebSocket handshake")
    headers = bytes(response).split(b"\r\n\r\n", 1)[0]
    assert headers.startswith(b"HTTP/1.1 101 "), headers
    expected = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
    )
    assert b"Sec-WebSocket-Accept: " + expected.lower() in headers.lower(), headers
    opcode, packet = recv_frame(conn)
    assert opcode == 1 and packet.startswith(b"0{"), packet
    send_text(conn, '40{"token":"invalid-ci-token"}')
    opcode, packet = recv_frame(conn)
    assert opcode == 1 and packet.startswith(b"44"), packet
    assert json.loads(packet[2:]).get("message") == "authentication failed", packet
print("real Socket.IO Engine.IO/WebSocket handshake and app auth rejection passed")
'''


class FixtureError(RuntimeError):
    """The isolated CI fixture failed its provenance rehearsal."""


def docker_command(args: list[str]) -> list[str]:
    return ["docker", "--host", "unix:///var/run/docker.sock", *args]


def docker_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(key, None)
    return env


def invoke(args: list[str], *, timeout: int = 45, check: bool = True,
           binary: bool = False):
    try:
        result = subprocess.run(
            docker_command(args), env=docker_env(), capture_output=True,
            text=not binary, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FixtureError("isolated Docker operation failed") from exc
    if check and result.returncode:
        raise FixtureError("isolated Docker operation failed")
    return result


def run(args: list[str], *, timeout: int = 45) -> str:
    return invoke(args, timeout=timeout).stdout


def source_tree_sha256(repo: Path, relative: str) -> str:
    paths = subprocess.check_output(
        ["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others",
         "--exclude-standard", "--", relative],
    ).split(b"\0")
    digest = hashlib.sha256()
    selected = sorted(path.decode("utf-8") for path in paths if path)
    if not selected:
        raise FixtureError("application build context is empty")
    for name in selected:
        path = repo / name
        if not path.is_file():
            raise FixtureError("application source inventory changed")
        payload = path.read_bytes()
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def image_inspect(image: str) -> dict:
    rows = json.loads(run(["image", "inspect", image]))
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise FixtureError("image inspection unavailable")
    return rows[0]


def build_app_image(repo: Path, service: str, fixture: str, tag: str,
                    iidfile: Path, revision: str) -> tuple[str, str]:
    context = repo / f"batalla_medieval_{service}"
    tree_hash = source_tree_sha256(repo, context.relative_to(repo).as_posix())
    args = [
        "build", "--pull", "--iidfile", str(iidfile), "--tag", tag,
        "--label", "medievol.g5.edge-fixture=" + fixture,
        "--label", "medievol.g5.source-sha256=" + tree_hash,
        "--label", "org.opencontainers.image.revision=" + revision,
    ]
    if service == "frontend":
        args.extend(["--build-arg", "VITE_API_URL=/api"])
    args.append(str(context))
    invoke(args, timeout=1800)
    image_id = iidfile.read_text().strip()
    row = image_inspect(image_id)
    labels = row.get("Config", {}).get("Labels", {})
    if (not _IMAGE_ID.fullmatch(image_id) or row.get("Id") != image_id
            or labels.get("medievol.g5.edge-fixture") != fixture
            or labels.get("medievol.g5.source-sha256") != tree_hash
            or labels.get("org.opencontainers.image.revision") != revision):
        raise FixtureError("built app image content identity mismatch")
    return image_id, tree_hash


def config_bundle(repo: Path, directory: Path) -> dict[str, tuple[Path, str]]:
    source_caddy = (repo / "Caddyfile").read_text()
    caddy_text = source_caddy.replace("{$TLS_EMAIL}", "ci@example.invalid")
    caddy_text = caddy_text.replace("{$PUBLIC_HOST}", ":8080")
    if caddy_text.count("reverse_proxy nginx:80") != 1:
        raise FixtureError("unexpected Caddy route source")
    caddy_text = caddy_text.replace("reverse_proxy nginx:80", "reverse_proxy nginx:8080")

    nginx_text = (repo / "nginx.conf").read_text()
    if nginx_text.count("listen 80;") != 1:
        raise FixtureError("unexpected Nginx route source")
    nginx_text = "pid /tmp/nginx.pid;\n" + nginx_text.replace("listen 80;", "listen 8080;")

    values = {
        "Caddyfile": caddy_text.encode(),
        "nginx.conf": nginx_text.encode(),
        "frontend.conf": _FRONTEND_CONF,
    }
    bundle = {}
    for name, content in values.items():
        if re.search(rb"(?im)^\s*(?:include|import)\b", content):
            raise FixtureError("edge config unexpectedly contains an include or import")
        path = directory / name
        path.write_bytes(content)
        path.chmod(0o444)
        bundle[name] = (path, sha256(content))
    return bundle


def write_status(fixture: str, service: str, image_id: str, network: str,
                 *, bind_mounts: tuple[tuple[str, str], ...] = ()):
    temp_mounts = {
        "caddy": ("/data", "/config", "/tmp"),
        "nginx": ("/tmp", "/var/cache/nginx"),
        "frontend": ("/tmp", "/var/cache/nginx"),
        "backend": ("/tmp",),
    }[service]
    commands = {
        "backend": ("python", "-m", "uvicorn", "app.main:socket_app",
                    "--host", "0.0.0.0", "--port", "8000"),
        "frontend": ("nginx", "-g", "daemon off; pid /tmp/nginx.pid;"),
        "nginx": ("nginx", "-g", "daemon off; pid /tmp/nginx.pid;"),
        "caddy": ("caddy", "run", "--config", "/etc/caddy/Caddyfile",
                  "--adapter", "caddyfile"),
    }
    uids = {"backend": 10001, "frontend": 101, "nginx": 101, "caddy": 10001}
    tmpfs_options = tuple(
        (path, f"rw,noexec,nosuid,size=32m,uid={uids[service]},gid={uids[service]},mode=700")
        for path in temp_mounts
    )
    args = [
        "run", "--detach", "--pull=never", "--name", fixture + "-" + service,
        "--network", network, "--network-alias", service,
        "--label", "medievol.g5.edge-fixture=" + fixture,
        "--label", "com.docker.compose.project=" + fixture,
        "--label", "com.docker.compose.service=" + service,
        "--restart=no", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true", "--pids-limit=64",
        "--memory=512m", "--cpus=1", "--user", f"{uids[service]}:{uids[service]}",
    ]
    for path, options in tmpfs_options:
        args.extend(["--tmpfs", f"{path}:{options}"])
    if service == "backend":
        args.extend([
            "--env", "APP_ENV=test",
            "--env", "DATABASE_URL=sqlite:////tmp/g5-edge-provenance-unused.db",
            "--env", "CORS_ORIGINS=http://localhost",
        ])
    for source, target in bind_mounts:
        args.extend(["--mount", f"type=bind,source={source},target={target},readonly"])
    args.extend(["--entrypoint", commands[service][0], image_id, *commands[service][1:]])
    container_id = run(args).strip()
    if not _ID.fullmatch(container_id):
        raise FixtureError("Docker returned an invalid container identity")
    contract = ContainerContract(
        service=service, container_id=container_id, image_id=image_id,
        network_name=network, network_id="0" * 64, alias=service,
        command=commands[service], uid=uids[service], bind_mounts=bind_mounts,
        tmpfs_options=tmpfs_options,
    )
    return container_id, contract


def inspect_contract(contract: ContainerContract, network_id: str,
                     *, check_network_name: str | None = None) -> None:
    if contract.network_id != network_id:
        contract = ContainerContract(
            **{**contract.__dict__, "network_id": network_id},
        )
    row = json.loads(run(["inspect", "--type", "container", contract.container_id]))[0]
    command_line = invoke(["exec", contract.container_id, "cat", "/proc/1/cmdline"],
                          binary=True).stdout
    status = invoke(["exec", contract.container_id, "cat", "/proc/1/status"],
                    binary=True).stdout.decode("ascii", errors="replace")
    verify_container(row, contract, command_line, status)
    if check_network_name:
        network = json.loads(run(["network", "inspect", check_network_name]))[0]
        verify_network(network, network_id, check_network_name)


def assert_rejected_config(path: Path, expected_digest: str) -> None:
    original = path.read_bytes()
    if path.name == "nginx.conf":
        altered = original.replace(b"proxy_pass http://backend/;",
                                   b"proxy_pass http://frontend/;", 1)
        if altered == original:
            raise FixtureError("could not construct a route-deviation fixture")
    else:
        altered = original + b"\n"
    path.chmod(0o644)
    try:
        path.write_bytes(altered)
        try:
            read_config(path, expected_digest)
        except ProvenanceError:
            return
        raise FixtureError("altered edge configuration was accepted")
    finally:
        path.write_bytes(original)
        path.chmod(0o444)
    read_config(path, expected_digest)


def probe_app(backend_id: str) -> None:
    run(["exec", backend_id, "python", "-c", _APP_PROBE], timeout=30)
    run(["exec", backend_id, "python", "-c", _SOCKET_IO_PROBE], timeout=30)


def wait_for_edge(backend_id: str) -> None:
    for _ in range(60):
        result = invoke(["exec", backend_id, "python", "-c",
                         "import urllib.request; urllib.request.urlopen('http://caddy:8080/api/health', timeout=2)"],
                        check=False)
        if result.returncode == 0:
            return
        time.sleep(1)
    raise FixtureError("controlled Caddy → Nginx → backend route did not become ready")


def cleanup(fixture: str) -> None:
    if not _FIXTURE.fullmatch(fixture):
        raise FixtureError("invalid isolated edge fixture identity")
    label = "label=medievol.g5.edge-fixture=" + fixture
    containers = run(["ps", "--all", "--quiet", "--no-trunc", "--filter", label]).splitlines()
    if len(set(containers)) != len(containers) or any(not _ID.fullmatch(i) for i in containers):
        raise FixtureError("invalid isolated container inventory")
    if containers:
        run(["stop", "--time", "10", *containers], timeout=60)
        run(["rm", "--force", "--volumes", *containers], timeout=60)
    if run(["ps", "--all", "--quiet", "--no-trunc", "--filter", label]).strip():
        raise FixtureError("isolated edge containers survived cleanup")
    networks = run(["network", "ls", "--quiet", "--no-trunc", "--filter", label]).splitlines()
    if len(set(networks)) > 1 or any(not _ID.fullmatch(i) for i in networks):
        raise FixtureError("invalid isolated network inventory")
    if networks:
        run(["network", "rm", *networks], timeout=60)
    if run(["network", "ls", "--quiet", "--no-trunc", "--filter", label]).strip():
        raise FixtureError("isolated edge network survived cleanup")
    images = run(["image", "ls", "--quiet", "--no-trunc", "--filter", label]).splitlines()
    if len(set(images)) != len(images) or any(not _IMAGE_ID.fullmatch(i) for i in images):
        raise FixtureError("invalid isolated image inventory")
    if images:
        run(["image", "rm", *images], timeout=60)


def _require_ci() -> None:
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("CI") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != "luis12duboqwe/Batallas-mediavales"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.environ.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}):
        raise FixtureError("only the repository's hosted push/dispatch CI may run this fixture")


def main() -> int:
    fixture = None
    cleanup_done = False
    try:
        _require_ci()
        repo = Path(__file__).resolve().parents[1]
        revision = run(["version", "--format", "{{.Server.Version}}"]).strip()
        if not revision:
            raise FixtureError("Docker daemon version unavailable")
        source_revision = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True,
        ).strip()
        if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
            raise FixtureError("source revision is not immutable")

        fixture = "bm-g5-edge-provenance-" + uuid4().hex
        with tempfile.TemporaryDirectory(prefix="bm-g5-edge-provenance-") as temp:
            root = Path(temp).resolve()
            configs = config_bundle(repo, root)
            for name, (path, digest) in configs.items():
                fixed_config(name, path.read_bytes(), digest)
            assert_rejected_config(configs["nginx.conf"][0], configs["nginx.conf"][1])

            run(["pull", _CADDY], timeout=300)
            run(["pull", _NGINX], timeout=300)
            caddy_image = image_inspect(_CADDY)["Id"]
            nginx_image = image_inspect(_NGINX)["Id"]
            if not _IMAGE_ID.fullmatch(caddy_image) or not _IMAGE_ID.fullmatch(nginx_image):
                raise FixtureError("proxy images are not content identified")
            backend_image, backend_tree = build_app_image(
                repo, "backend", fixture, fixture + ":backend", root / "backend.iid", source_revision,
            )
            frontend_image, frontend_tree = build_app_image(
                repo, "frontend", fixture, fixture + ":frontend", root / "frontend.iid", source_revision,
            )

            run(["network", "create", "--driver", "bridge", "--internal",
                 "--label", "medievol.g5.edge-fixture=" + fixture, fixture])
            network = json.loads(run(["network", "inspect", fixture]))[0]
            network_id = network.get("Id")
            if not isinstance(network_id, str) or not _ID.fullmatch(network_id):
                raise FixtureError("network inspection returned invalid network identity")
            verify_network(network, network_id, fixture)
            contracts = {}
            ids = {}
            for service, image, mounts in (
                ("backend", backend_image, ()),
                ("frontend", frontend_image, ((str(configs["frontend.conf"][0]),
                                                "/etc/nginx/nginx.conf"),)),
                ("nginx", nginx_image, ((str(configs["nginx.conf"][0]),
                                         "/etc/nginx/nginx.conf"),)),
                ("caddy", caddy_image, ((str(configs["Caddyfile"][0]),
                                         "/etc/caddy/Caddyfile"),)),
            ):
                ids[service], contracts[service] = write_status(
                    fixture, service, image, fixture, bind_mounts=mounts,
                )
                contracts[service] = ContainerContract(
                    **{**contracts[service].__dict__, "network_id": network_id},
                )

            for service, contract in contracts.items():
                inspect_contract(contract, network_id, check_network_name=fixture)
            network = json.loads(run(["network", "inspect", fixture]))[0]
            verify_network(network, network_id, fixture, set(ids.values()))
            for name, (path, digest) in configs.items():
                read_config(path, digest)
            assert_rejected_config(configs["nginx.conf"][0], configs["nginx.conf"][1])
            assert_rejected_config(configs["Caddyfile"][0], configs["Caddyfile"][1])
            assert_rejected_config(configs["frontend.conf"][0], configs["frontend.conf"][1])
            wait_for_edge(ids["backend"])
            probe_app(ids["backend"])

            original_caddy = contracts["caddy"]
            run(["rm", "--force", ids["caddy"]])
            replacement_id, replacement_contract = write_status(
                fixture, "caddy", caddy_image, fixture,
                bind_mounts=((str(configs["Caddyfile"][0]), "/etc/caddy/Caddyfile"),),
            )
            replacement_contract = ContainerContract(
                **{**replacement_contract.__dict__, "network_id": network_id},
            )
            replacement_row = json.loads(run(["inspect", "--type", "container",
                                              replacement_id]))[0]
            replacement_command = invoke(
                ["exec", replacement_id, "cat", "/proc/1/cmdline"], binary=True,
            ).stdout
            replacement_status = invoke(
                ["exec", replacement_id, "cat", "/proc/1/status"], binary=True,
            ).stdout.decode("ascii", errors="replace")
            replacement_rejected = False
            try:
                verify_container(replacement_row, original_caddy,
                                 replacement_command, replacement_status)
            except ProvenanceError:
                replacement_rejected = True
            else:
                raise FixtureError("replacement Caddy container was accepted")

            evidence = {
                "status": "NO-GO",
                "scope": "controlled-startup-only",
                "source_revision": source_revision,
                "docker_server_version": revision,
                "network_id": network_id,
                "images": {
                    "caddy": {"reference": _CADDY, "image_id": caddy_image},
                    "nginx": {"reference": _NGINX, "image_id": nginx_image},
                    "backend": {"image_id": backend_image, "source_tree_sha256": backend_tree},
                    "frontend": {"image_id": frontend_image, "source_tree_sha256": frontend_tree},
                },
                "config_sha256": {name: digest for name, (_, digest) in configs.items()},
                "container_ids": ids,
                "checks": [
                    "exact PID-1 argv and UID",
                    "content-addressed images and config mounts",
                    "read-only roots, no added capabilities, no published ports",
                    "isolated internal bridge network",
                    "Caddy to Nginx to actual backend HTTP/API and frontend",
                    "actual Socket.IO Engine.IO/WebSocket handshake and auth rejection",
                    "route-deviation and config-content drift rejected",
                    "replacement container rejected",
                ],
                "replacement_rejected": replacement_rejected,
                "replacement_container_id": replacement_id,
                "limitations": [
                    "Docker daemon access is root-equivalent on the disposable hosted runner.",
                    "The evidence proves only this controlled startup and these probes.",
                    "Probes do not prove the absence of alternate network paths or bypasses.",
                    "Legacy host observation cannot prove which configuration was loaded.",
                ],
            }
        cleanup(fixture)
        cleanup_done = True
        evidence["fixture_closed"] = True
        print(json.dumps(evidence, sort_keys=True, indent=2))
        print("G5 edge provenance rehearsal passed; outcome remains NO-GO.")
        return 0
    except Exception as exc:
        print(str(exc) or "G5 edge provenance rehearsal failed", file=sys.stderr)
        return 1
    finally:
        if fixture is not None and not cleanup_done:
            try:
                cleanup(fixture)
            except Exception as exc:
                print("isolated edge cleanup failed: " + str(exc), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
