"""CI-only Nginx admission and pre-existing WebSocket rehearsal."""
from __future__ import annotations

import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from ops.g5_edge_admission import EdgeAdmission, EdgeError


SERVER = r'''
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import hashlib

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path.startswith("/socket.io/") and self.headers.get("Upgrade") == "websocket":
            key = self.headers["Sec-WebSocket-Key"]
            accept = base64.b64encode(hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
            ).digest()).decode()
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.end_headers()
            self.wfile.flush()
            # Answer the client's empty, masked WebSocket ping with a pong.
            while self.rfile.read(6) == bytes.fromhex("898001020304"):
                self.wfile.write(bytes.fromhex("8a00"))
                self.wfile.flush()
            self.close_connection = True
        else:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
'''

CLIENT = r'''
import socket
import sys

with socket.create_connection(("nginx", 80), timeout=5) as conn:
    conn.settimeout(10)
    conn.sendall(
        b"GET /socket.io/?EIO=4&transport=websocket HTTP/1.1\r\n"
        b"Host: nginx\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n"
        b"Sec-WebSocket-Version: 13\r\n"
        b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
    )
    stream = conn.makefile("rb")
    assert stream.readline().split()[1] == b"101"
    while stream.readline() != b"\r\n":
        pass
    print("READY", flush=True)
    assert sys.stdin.readline().strip() == "ping"
    conn.sendall(bytes.fromhex("898001020304"))
    assert stream.read(2) == bytes.fromhex("8a00")
    print("PONG", flush=True)
    assert sys.stdin.readline().strip() == "closed"
    try:
        data = stream.read(1)
    except ConnectionResetError:
        data = b""
    assert data == b"", "old WebSocket did not disconnect"
    print("DISCONNECTED", flush=True)
'''


def docker_command(args: list[str]) -> list[str]:
    return ["docker", "--host", "unix:///var/run/docker.sock", *args]


def docker_env():
    env = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(key, None)
    return env


def probe(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(docker_command(args), env=docker_env(),
                            capture_output=True, text=True, timeout=45, check=False)
    return result.returncode, result.stdout, result.stderr


def run(args: list[str]) -> str:
    code, stdout, _ = probe(args)
    if code != 0:
        raise EdgeError("isolated Docker command failed")
    return stdout


def expect_line(proc, expected):
    ready, _, _ = select.select([proc.stdout], [], [], 20)
    if not ready or proc.stdout.readline().strip() != expected:
        raise RuntimeError("WebSocket fixture failed: expected " + expected)


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
        print("CI-only G5 Nginx rehearsal", file=sys.stderr)
        return 2
    project = "bm-g5-edge-" + uuid4().hex
    containers = []
    network = None
    client = None
    with tempfile.TemporaryDirectory(prefix="bm-g5-edge-") as temp:
        root = Path(temp).resolve()
        state = root / ".ops-state"
        state.mkdir(mode=0o700)
        edge = state / "edge-maintenance"
        edge.mkdir(mode=0o755)
        edge.chmod(0o755)
        (edge / "open").mkdir(mode=0o755)
        conf = root / "nginx.g5.conf"
        shutil.copyfile(Path(__file__).resolve().parents[1] / "nginx.g5.conf", conf)
        conf.chmod(0o644)

        def start(service, args):
            identity = run([
                "run", "-d", "--network", network, "--network-alias", service,
                "--label", "com.docker.compose.project=" + project,
                "--label", "com.docker.compose.service=" + service, *args,
            ]).strip()
            containers.append(identity)
            return identity

        try:
            network = run(["network", "create", "--internal", project]).strip()
            backend = start("backend", ["python:3.11-alpine", "python", "-u", "-c", SERVER])
            frontend = start("frontend", ["python:3.11-alpine", "python", "-m", "http.server", "80"])
            nginx = start("nginx", [
                "--mount", f"type=bind,source={conf},target=/etc/nginx/nginx.conf,readonly",
                "--mount", f"type=bind,source={edge},target=/etc/nginx/edge-maintenance,readonly",
                "nginx:1.28-alpine",
            ])
            for _ in range(30):
                code, _, _ = probe(["exec", nginx, "wget", "-q", "-O", "/dev/null",
                                    "-T", "2", "http://127.0.0.1/api/health"])
                if code == 0:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Nginx did not prove open HTTP admission")
            client = subprocess.Popen(
                docker_command(["exec", "-i", frontend, "python", "-u", "-c", CLIENT]),
                env=docker_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            expect_line(client, "READY")
            gate = EdgeAdmission(str(root), project, nginx, run, probe)
            gate.close()
            gate.assert_closed()
            # New handshakes are denied, but an old upgraded connection is
            # still live. This is why marker removal alone is not a drain.
            client.stdin.write("ping\n")
            client.stdin.flush()
            expect_line(client, "PONG")
            run(["stop", "--time", "2", backend])
            client.stdin.write("closed\n")
            client.stdin.flush()
            expect_line(client, "DISCONNECTED")
            if client.wait(timeout=10) != 0:
                raise RuntimeError("old WebSocket client failed")
            gate.assert_closed()
            # Maintenance remains closed on an already running proxy even
            # after the backend is stopped. No real game data is involved.
            print("G5 real Nginx HTTP/WS admission and old WebSocket drain rehearsal passed")
            return 0
        finally:
            if client is not None and client.poll() is None:
                client.kill()
                client.wait(timeout=10)
            if containers:
                run(["rm", "-f", *containers])
            if network:
                run(["network", "rm", network])


if __name__ == "__main__":
    raise SystemExit(main())
