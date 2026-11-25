"""Durable G5 admission closure for the opt-in Nginx gate.

No CLI, no reopening, no activation of the G5 overlay. Caller must own the
activation lease, control Docker administration and fence SQL before draining
existing connections. Closing the marker does not terminate active requests.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
import re
import stat
from typing import Callable

from ops.g5_cutover_state import CutoverStore, DIRECTORY, _directory_identity, StateError


class EdgeError(StateError):
    """The edge admission closure cannot be established."""


_ID = re.compile(r"[0-9a-f]{64}")
_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}")
_MOUNT = "/etc/nginx/edge-maintenance"
_CONF = "/etc/nginx/nginx.conf"
_STATUS = re.compile(r"^\s*HTTP/1\.[01]\s+(\d{3})(?:\s|$)", re.MULTILINE)
_INSPECT = (
    '{"id":{{json .Id}},'
    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"running":{{json .State.Running}},'
    '"paused":{{json .State.Paused}},'
    '"mounts":{{json .Mounts}}}'
)


class EdgeAdmission:
    """Close an exact, already-running opt-in Nginx container.

    Runner executes Docker locally using argument vectors; probe runner returns
    (exit code, stdout, stderr) for wget (HTTP 503 is normally nonzero).
    The caller must supply trusted executors on the same Docker host.
    """

    def __init__(self, host_root: str, project: str, nginx_id: str,
                 run: Callable[[list[str]], str],
                 probe: Callable[[list[str]], tuple[int, str, str]]):
        self.store = CutoverStore(host_root)
        if (not isinstance(project, str) or not _PROJECT.fullmatch(project)
                or not isinstance(nginx_id, str) or not _ID.fullmatch(nginx_id)):
            raise EdgeError("unsafe Nginx container or project identity")
        self.project = project
        self.nginx_id = nginx_id
        self.run = run
        self.probe = probe
        self.edge_path = os.path.join(self.store.host_root, ".ops-state", "edge-maintenance")
        self.conf_path = os.path.join(self.store.host_root, "nginx.g5.conf")
        self._expected = None

    @contextmanager
    def _edge(self):
        with self.store._state_directory() as directory:
            original = _directory_identity(os.fstat(directory))
            fd = os.open("edge-maintenance", DIRECTORY | os.O_CLOEXEC, dir_fd=directory)
            try:
                info = os.fstat(fd)
                if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o755:
                    raise EdgeError("edge directory must be caller-owned mode 0755")
                identity = _directory_identity(info)
                if self._expected is not None and identity != self._expected:
                    raise EdgeError("edge directory identity changed")
                yield fd, identity
                self.store._check_directory(directory, original)
                if identity != _directory_identity(os.stat(
                    "edge-maintenance", dir_fd=directory, follow_symlinks=False
                )):
                    raise EdgeError("edge directory replaced during closure")
            finally:
                os.close(fd)

    def _runtime(self, fd: int) -> None:
        raw = self.run(["inspect", "--type", "container", "--format", _INSPECT, self.nginx_id])
        row = json.loads(raw)
        if (not isinstance(row, dict) or row.get("id") != self.nginx_id
                or row.get("project") != self.project or row.get("service") != "nginx"
                or row.get("running") is not True or row.get("paused") is not False
                or not isinstance(row.get("mounts"), list)):
            raise EdgeError("Nginx runtime identity is not established")
        for destination, source in ((_MOUNT, self.edge_path), (_CONF, self.conf_path)):
            mounts = [m for m in row["mounts"] if isinstance(m, dict)
                      and m.get("Destination") == destination]
            if (len(mounts) != 1 or mounts[0].get("Type") != "bind"
                    or mounts[0].get("Source") != source or mounts[0].get("RW") is not False):
                raise EdgeError("Nginx G5 bind mount does not match trusted host path")
        # Reject nested mounts that can shadow marker/config entries.
        for mount in row["mounts"]:
            if not isinstance(mount, dict) or not isinstance(mount.get("Destination"), str):
                raise EdgeError("malformed Nginx mount inventory")
            target = mount["Destination"]
            if target.startswith(_MOUNT + "/") or target.startswith(_CONF + "/"):
                raise EdgeError("unexpected nested Nginx G5 mount")
        config = os.stat(self.conf_path, follow_symlinks=False)
        if (not stat.S_ISREG(config.st_mode) or config.st_uid != os.geteuid()
                or config.st_mode & 0o022):
            raise EdgeError("unsafe G5 Nginx config file")
        # Docker's Source string alone does not distinguish a replaced inode
        # from the old directory/config still mounted by the running container.
        for path, info in ((_MOUNT, os.fstat(fd)), (_CONF, config)):
            actual = self.run(["exec", self.nginx_id, "stat", "-c", "%d:%i", path]).strip()
            if actual != f"{info.st_dev}:{info.st_ino}":
                raise EdgeError("Nginx G5 mount inode differs from host inode")

    def _probes(self) -> None:
        for path, headers in (
            ("/api", []), ("/api/health", []),
            ("/socket.io", []), ("/socket.io/?EIO=4&transport=polling", []),
            ("/socket.io/?EIO=4&transport=websocket",
             ["--header", "Connection: Upgrade", "--header", "Upgrade: websocket",
              "--header", "Sec-WebSocket-Version: 13",
              "--header", "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ=="]),
        ):
            code, stdout, stderr = self.probe([
                "exec", self.nginx_id, "wget", "-S", "-O", "/dev/null", "-T", "3",
                *headers, "http://127.0.0.1" + path,
            ])
            # A transport failure or redirect ending in 503 is not proof.
            if type(code) is not int or code == 0 or _STATUS.findall(stderr) != ["503"]:
                raise EdgeError("Nginx failed to prove direct maintenance HTTP 503")

    def close(self) -> None:
        """Remove only the empty admission directory, durably; never reopen."""
        try:
            with self._edge() as (fd, identity):
                self._runtime(fd)
                entries = os.listdir(fd)
                if entries == ["open"]:
                    marker = os.stat("open", dir_fd=fd, follow_symlinks=False)
                    if (not stat.S_ISDIR(marker.st_mode) or marker.st_uid != os.geteuid()
                            or marker.st_mode & 0o022):
                        raise EdgeError("unsafe Nginx admission marker")
                    os.rmdir("open", dir_fd=fd)
                elif entries:
                    raise EdgeError("unexpected files in Nginx maintenance directory")
                os.fsync(fd)
                if os.listdir(fd):
                    raise EdgeError("Nginx admission changed during closure")
                self._expected = identity
                self._runtime(fd)
                self._probes()
                if os.listdir(fd):
                    raise EdgeError("Nginx admission reopened during closure")
        except Exception as exc:
            if isinstance(exc, EdgeError):
                raise
            raise EdgeError("G5 edge closure failed") from None

    def assert_closed(self) -> None:
        if self._expected is None:
            raise EdgeError("G5 edge closure was not engaged")
        try:
            with self._edge() as (fd, _):
                if os.listdir(fd):
                    raise EdgeError("Nginx admission is no longer closed")
                self._runtime(fd)
                self._probes()
                if os.listdir(fd):
                    raise EdgeError("Nginx admission changed during verification")
        except Exception as exc:
            if isinstance(exc, EdgeError):
                raise
            raise EdgeError("G5 edge verification failed") from None
