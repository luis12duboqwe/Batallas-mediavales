from __future__ import annotations

import base64
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

import pytest


ROOT = Path(__file__).resolve().parents[1]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _mock_backend(records: list[tuple[str, str]]) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _respond(self):
            records.append((self.command, self.path))
            if self.headers.get("Upgrade", "").lower() == "websocket":
                self.send_response(101)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.end_headers()
                self.wfile.flush()
                return

            if self.path == "/forbidden":
                self.send_error(403)
                return

            body = f"{self.command}:{self.path}".encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        do_GET = _respond
        do_POST = _respond

        def log_message(self, _format, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


@pytest.fixture(scope="module")
def edge():
    nginx = shutil.which("nginx")
    if not nginx:
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail("Nginx is required in CI: skipping the edge maintenance gate is unsafe")
        pytest.skip("nginx is required for isolated edge integration tests")

    records: list[tuple[str, str]] = []
    backend = _mock_backend(records)
    frontend = _mock_backend([])
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (backend, frontend)
    ]
    for thread in threads:
        thread.start()

    temp_root = Path(tempfile.mkdtemp(prefix="g5-edge-maintenance-"))
    temp_root.chmod(0o755)
    process = None
    try:
        control = temp_root / "control"
        control.mkdir(mode=0o755)
        control.chmod(0o755)  # mktemp/runner may have restrictive umask 077
        config_path = temp_root / "nginx.conf"
        port = _free_port()
        config = (ROOT / "nginx.g5.conf").read_text(encoding="utf-8")
        config = config.replace("server backend:8000;", f"server 127.0.0.1:{backend.server_port};")
        config = config.replace("server frontend:80;", f"server 127.0.0.1:{frontend.server_port};")
        config = config.replace("listen 80;", f"listen 127.0.0.1:{port};")
        config = config.replace("/etc/nginx/edge-maintenance", str(control))
        config = config.replace(
            "http {\n", f"http {{\n    access_log {temp_root / 'access.log'};\n"
        )
        config = f"pid {temp_root / 'nginx.pid'};\nerror_log {temp_root / 'error.log'} notice;\n" + config
        config_path.write_text(config, encoding="utf-8")

        checked = subprocess.run(
            [nginx, "-t", "-c", str(config_path), "-p", str(temp_root) + "/"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert checked.returncode == 0, checked.stderr
        process = subprocess.Popen(
            [nginx, "-c", str(config_path), "-p", str(temp_root) + "/", "-g", "daemon off;"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base_url = f"http://127.0.0.1:{port}"

        for _ in range(100):
            if process.poll() is not None:
                pytest.fail((temp_root / "error.log").read_text(encoding="utf-8"))
            try:
                with urlopen(base_url + "/health", timeout=0.2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("isolated Nginx did not become ready")

        yield {"base_url": base_url, "control": control, "records": records}
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        backend.shutdown()
        frontend.shutdown()
        for thread in threads:
            thread.join(timeout=2)
        backend.server_close()
        frontend.server_close()
        shutil.rmtree(temp_root, ignore_errors=True)


def _request(edge, path: str, method="GET", headers=None, body=None, redirects=True):
    request = Request(edge["base_url"] + path, data=body, headers=headers or {}, method=method)
    opener = build_opener() if redirects else build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=3) as response:
            return response.status, response.headers, response.read()
    except HTTPError as response:
        return response.code, response.headers, response.read()


@pytest.fixture()
def closed_edge(edge):
    marker = edge["control"] / "open"
    if marker.is_symlink() or marker.is_file():
        marker.unlink()
    elif marker.is_dir():
        shutil.rmtree(marker)
    return edge


def _assert_maintenance_response(response):
    status, headers, _ = response
    assert status == 503
    assert headers["Retry-After"] == "60"
    assert headers["Cache-Control"] == "no-store"


def _websocket_response(edge):
    key = base64.b64encode(b"g5-edge-test-key").decode()
    request = (
        "GET /socket.io/?EIO=4&transport=websocket HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{edge['base_url'].rsplit(':', 1)[1]}\r\n"
        "Connection: Upgrade\r\n"
        "Upgrade: websocket\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Sec-WebSocket-Key: {key}\r\n\r\n"
    ).encode()
    with socket.create_connection(("127.0.0.1", int(edge["base_url"].rsplit(":", 1)[1]))) as sock:
        sock.settimeout(3)
        sock.sendall(request)
        response = bytearray()
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
    return bytes(response).split(b"\r\n\r\n", 1)


def _assert_websocket_maintenance_response(edge):
    headers = _websocket_response(edge)
    assert headers[0].startswith(b"HTTP/1.1 503")
    assert b"Retry-After: 60" in headers[0]
    assert b"Cache-Control: no-store" in headers[0]


def test_closed_by_default_blocks_api_writes_and_socket_io(closed_edge):
    edge = closed_edge
    _assert_maintenance_response(_request(edge, "/api/write?operation=get"))
    _assert_maintenance_response(_request(
        edge, "/api/write", method="POST", body=b"write"
    ))
    _assert_maintenance_response(_request(edge, "/socket.io/?transport=polling"))
    _assert_maintenance_response(_request(edge, "/api", redirects=False))
    _assert_maintenance_response(_request(edge, "/socket.io", redirects=False))
    _assert_websocket_maintenance_response(edge)
    assert edge["records"] == []
    status, _, body = _request(edge, "/health")
    assert status == 200
    assert body == b"ok\n"


def test_local_regular_file_opens_routes_without_reload_and_health_stays_live(closed_edge):
    edge = closed_edge
    (edge["control"] / "open").write_text("local marker\n", encoding="utf-8")
    (edge["control"] / "open").chmod(0o644)

    status, _, body = _request(edge, "/api/write?operation=get")
    assert status == 200
    assert body == b"GET:/write?operation=get"
    status, _, body = _request(edge, "/api/write", method="POST", body=b"write")
    assert status == 200
    assert body == b"POST:/write"
    assert _request(edge, "/socket.io/?transport=polling")[0] == 200
    assert _websocket_response(edge)[0].startswith(b"HTTP/1.1 101")

    assert _request(edge, "/api/forbidden")[0] == 403

    status, headers, _ = _request(edge, "/api", redirects=False)
    assert status == 308
    assert headers["Location"].endswith("/api/")
    status, headers, _ = _request(edge, "/socket.io", redirects=False)
    assert status == 308
    assert headers["Location"].endswith("/socket.io/")

    status, _, body = _request(edge, "/health")
    assert status == 200
    assert body == b"ok\n"


def test_missing_directory_and_symlink_signals_fail_closed(closed_edge):
    edge = closed_edge
    marker = edge["control"] / "open"

    _assert_maintenance_response(_request(edge, "/api/write"))
    marker.mkdir()
    _assert_maintenance_response(_request(edge, "/api/write"))

    marker.rmdir()
    target = edge["control"] / "target"
    target.write_text("local marker\n", encoding="utf-8")
    marker.symlink_to(target)
    _assert_maintenance_response(_request(edge, "/api/write"))

    marker.unlink()
    marker.write_text("local marker\n", encoding="utf-8")
    marker.chmod(0)
    _assert_maintenance_response(_request(edge, "/api/write"))


def test_client_supplied_headers_cannot_open_the_edge(closed_edge):
    edge = closed_edge
    for headers in (
        {"X-Edge-Maintenance": "open"},
        {"X-Maintenance": "false", "Cookie": "maintenance=open"},
        {"X-Forwarded-For": "127.0.0.1"},
    ):
        _assert_maintenance_response(_request(edge, "/api/write", headers=headers))
    _assert_websocket_maintenance_response(edge)
    assert _request(edge, "/_edge_maintenance_check")[0] == 404


def test_deploy_compose_mounts_control_read_only_and_design_documents_limits():
    compose = (ROOT / "docker-compose.deploy.yml").read_text(encoding="utf-8")
    nginx_service = compose.split("  nginx:\n", 1)[1].split("  caddy:\n", 1)[0]
    assert "./.ops-state/edge-maintenance:/etc/nginx/edge-maintenance:ro" in nginx_service
    assert "./${G5_NGINX_CONFIG_FILE:-nginx.conf}:/etc/nginx/nginx.conf:ro" in nginx_service
    assert (ROOT / "nginx.conf").is_file()
    assert (ROOT / "nginx.g5.conf").is_file()

    design = (ROOT / "docs/G5_EDGE_MAINTENANCE_DESIGN.md").read_text(encoding="utf-8")
    assert "WebSocket" in design
    assert "backend" in design
    assert "worker" in design
    assert "transaccional" in design


def test_restrictive_umask_directory_is_normalized_before_open(closed_edge):
    """Absent marker stays closed; normalization opens across worker UID setups."""
    edge = closed_edge
    control = edge["control"]
    marker = control / "open"
    control.chmod(0o700)
    try:
        assert control.stat().st_mode & 0o777 == 0o700
        _assert_maintenance_response(_request(edge, "/api/write"))
        marker.write_text("open\n", encoding="utf-8")
        marker.chmod(0o600)
        # A worker sharing the owner's UID can still read a 0600 file.
        # Do not rely on chmod for closing: only removing the marker closes.
        assert marker.stat().st_mode & 0o777 == 0o600
    finally:
        control.chmod(0o755)

    marker.chmod(0o644)
    assert _request(edge, "/api/write")[0] == 200
    assert _request(edge, "/socket.io/?transport=polling")[0] == 200

    marker.unlink()
    _assert_maintenance_response(_request(edge, "/api/write"))
    _assert_maintenance_response(_request(edge, "/socket.io/?transport=polling"))


def test_burst_closed_edge_never_returns_rate_limit_instead_of_maintenance(closed_edge):
    """Admission close has priority over API rate limiting for every request."""
    responses = [
        _request(
            closed_edge, "/api/write?check=maintenance",
            headers={"X-Forwarded-For": "198.51.100.220"},
        )
        for _ in range(45)
    ]
    for response in responses:
        _assert_maintenance_response(response)


def test_burst_open_edge_still_enforces_api_rate_limit(closed_edge):
    """The normal 429 anti-abuse budget is retained after explicit opening."""
    marker = closed_edge["control"] / "open"
    marker.write_text("open\n", encoding="utf-8")
    marker.chmod(0o644)
    statuses = [
        _request(
            closed_edge, "/api/write?check=rate",
            headers={"X-Forwarded-For": "198.51.100.221"},
        )[0]
        for _ in range(45)
    ]
    assert 200 in statuses
    assert 429 in statuses


def test_default_compose_remains_ungated_until_recovery_is_integrated():
    """Do not break normal local play or activate an unsafe G5 gate on merge."""
    base = (ROOT / "nginx.conf").read_text(encoding="utf-8")
    gated = (ROOT / "nginx.g5.conf").read_text(encoding="utf-8")
    local = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    protected = (ROOT / "docker-compose.deploy.yml").read_text(encoding="utf-8")
    assert "auth_request /_edge_maintenance_check" not in base
    assert "auth_request /_edge_maintenance_check" in gated
    assert "./nginx.conf:/etc/nginx/nginx.conf:ro" in local
    assert "G5_NGINX_CONFIG_FILE:-nginx.conf" in protected


def test_rate_limit_during_closed_gate_never_forwards_to_backend(closed_edge):
    """Rate limiting may emit 429 in a flood, but no request reaches a writer."""
    edge = closed_edge
    before = len(edge["records"])
    statuses = []
    for _ in range(40):
        status, headers, _ = _request(edge, "/api/write")
        statuses.append(status)
        if status == 503:
            assert headers["Retry-After"] == "60"
            assert headers["Cache-Control"] == "no-store"
    assert set(statuses) <= {429, 503}, statuses
    assert 503 in statuses
    assert len(edge["records"]) == before
