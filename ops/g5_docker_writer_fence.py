"""G5 runtime Docker writer shutdown, scoped to one inspected Compose project.

No CLI or deployment entrypoint. Caller must hold the G5 activation lease,
close edge admission and keep a durable database fence throughout. This cannot
exclude a Docker administrator or a writer outside the specified project.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import subprocess
from typing import Callable

from ops.g5_writer_drain_probe import WRITERS, SERVICES


class DockerFenceError(RuntimeError):
    """The project's runtime writer shutdown is not established."""


_ID = re.compile(r"[0-9a-f]{64}")
_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}")
_INSPECT = (
    '{"id":{{json .Id}},'
    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"status":{{json .State.Status}},'
    '"running":{{json .State.Running}},'
    '"paused":{{json .State.Paused}},'
    '"restarting":{{json .State.Restarting}},'
    '"policy":{{json .HostConfig.RestartPolicy.Name}}}'
)


def local_docker(args: list[str]) -> str:
    """Bound every command; never use a remote context or print diagnostics."""
    env = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH"):
        env.pop(key, None)
    try:
        result = subprocess.run(
            ["docker", "--host", "unix:///var/run/docker.sock", *args],
            env=env, capture_output=True, text=True, timeout=45, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        raise DockerFenceError("local Docker command failed or timed out") from None
    if result.returncode != 0:
        raise DockerFenceError("local Docker command returned nonzero")
    return result.stdout


@dataclass(frozen=True)
class Container:
    identity: str
    service: str
    status: str
    running: bool
    paused: bool
    restarting: bool
    policy: str

    @property
    def stopped(self) -> bool:
        return (self.status in {"exited", "created"} and not self.running
                and not self.paused and not self.restarting)


class DockerWriterFence:
    """Disable restart for *all* known writers before stopping any writer.

    Includes stopped instances, replicas and Compose one-offs. Uses full
    immutable IDs, never service-name stop/up (which can affect dependencies).
    A changed inventory, unknown service, failed command or ambiguous state
    blocks success. Never restores restart policies or starts containers.
    """

    def __init__(self, project: str, runner: Callable[[list[str]], str] = local_docker):
        if not isinstance(project, str) or not _PROJECT.fullmatch(project):
            raise DockerFenceError("invalid Compose project identity")
        self.project = project
        self._run = runner
        self._expected: dict[str, str] | None = None

    def _command(self, args: list[str]) -> str:
        try:
            result = self._run(args)
        except Exception:
            raise DockerFenceError("Docker writer fence command failed") from None
        if not isinstance(result, str):
            raise DockerFenceError("ambiguous Docker response")
        return result

    def _inventory(self) -> dict[str, Container]:
        output = self._command([
            "ps", "--all", "--no-trunc", "--filter",
            f"label=com.docker.compose.project={self.project}", "--format", "{{.ID}}",
        ])
        ids = output.splitlines()
        if (not ids or len(ids) != len(set(ids))
                or not all(_ID.fullmatch(identity) for identity in ids)):
            raise DockerFenceError("empty or malformed Docker project inventory")
        records = {}
        for identity in sorted(ids):
            raw = self._command([
                "inspect", "--type", "container", "--format", _INSPECT, identity
            ])
            try:
                row = json.loads(raw)
                if (not isinstance(row, dict)
                        or row.get("id") != identity or row.get("project") != self.project
                        or not isinstance(row.get("service"), str)
                        or row["service"] not in SERVICES
                        or not isinstance(row.get("status"), str)
                        or not isinstance(row.get("policy"), str)
                        or any(type(row.get(key)) is not bool
                               for key in ("running", "paused", "restarting"))):
                    raise DockerFenceError("unknown or ambiguous Docker container identity")
                records[identity] = Container(
                    identity, row["service"], row["status"], row["running"],
                    row["paused"], row["restarting"], row["policy"],
                )
            except (ValueError, TypeError):
                raise DockerFenceError("invalid Docker inspection response") from None
        # Refuse a wrong/partial project without its expected live DB and edge.
        for service in ("database", "nginx"):
            matches = [r for r in records.values() if r.service == service]
            if (len(matches) != 1 or matches[0].status != "running"
                    or not matches[0].running or matches[0].paused or matches[0].restarting):
                raise DockerFenceError("expected exactly one live database and nginx")
        return records

    def _same_inventory(self) -> dict[str, Container]:
        records = self._inventory()
        if {key: row.service for key, row in records.items()} != self._expected:
            raise DockerFenceError("Compose container inventory changed during writer shutdown")
        return records

    def engage(self) -> None:
        if self._expected is not None:
            raise DockerFenceError("writer shutdown already attempted; reconcile manually")
        records = self._inventory()
        writers = [row for row in records.values() if row.service in WRITERS]
        # Unknown or paused/dead/removing containers require reconciliation,
        # not unpausing or restarting them to try to obtain a clean result.
        for row in writers:
            if not (row.stopped or (
                row.status in {"running", "restarting"} and not row.paused
                and (row.running or row.restarting)
            )):
                raise DockerFenceError("writer container state cannot be safely stopped")
        self._expected = {key: row.service for key, row in records.items()}

        # A partially failed sequence never undoes restrictions already applied.
        for row in writers:
            self._command(["update", "--restart=no", row.identity])
        records = self._same_inventory()
        for row in records.values():
            if row.service in WRITERS and row.policy != "no":
                raise DockerFenceError("runtime writer restart policy was not disabled")
        for row in records.values():
            if row.service in WRITERS and not row.stopped:
                self._command(["stop", "--time", "10", row.identity])
        self.assert_closed()

    def assert_closed(self) -> None:
        if self._expected is None:
            raise DockerFenceError("writer shutdown was not engaged")
        for row in self._same_inventory().values():
            if row.service in WRITERS and (not row.stopped or row.policy != "no"):
                raise DockerFenceError("Docker writer remains active or restartable")
