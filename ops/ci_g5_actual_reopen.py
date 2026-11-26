"""Incomplete CI-only G5 reopen rehearsal: identity/receipt checks only.

This module deliberately has no entrypoint and cannot reopen anything. A
future rehearsal must call these checks while owning the lifecycle lease and
the manifest phase lock; they are not a production authorization mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
import sys

from ops.g5_cutover_state import CutoverStore, Identity, Phase, StateError


_CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")


@dataclass(frozen=True)
class OriginalDatabase:
    database: str
    database_oid: int
    app_role: str
    app_role_oid: int
    maintenance_role: str
    maintenance_role_oid: int
    connection_limit: int
    login: bool
    server_version_num: int

    def __post_init__(self):
        names = (self.database, self.app_role, self.maintenance_role)
        oids = (self.database_oid, self.app_role_oid, self.maintenance_role_oid)
        if (any(not isinstance(n, str) or not _NAME.fullmatch(n) for n in names)
                or self.app_role == self.maintenance_role
                or any(type(oid) is not int or oid <= 0 for oid in oids)
                or self.app_role_oid == self.maintenance_role_oid
                or type(self.connection_limit) is not int
                or self.connection_limit < -1 or self.connection_limit == 0
                or self.login is not True
                or type(self.server_version_num) is not int
                or not 150000 <= self.server_version_num < 160000):
            raise StateError("invalid original PostgreSQL fixture identity or parameters")


def _encoded(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise StateError("invalid Docker inspection response") from None


@dataclass(frozen=True)
class OriginalContainer:
    identity: str
    image: str
    service: str
    policy_name: str
    policy_maximum_retry_count: int
    config: str = field(repr=False)
    host_config: str = field(repr=False)

    @classmethod
    def capture(cls, row, project, service):
        if not isinstance(row, dict):
            raise StateError("invalid Docker container inspection")
        identity, image = row.get("Id"), row.get("Image")
        config, host = row.get("Config"), row.get("HostConfig")
        if (not isinstance(identity, str) or not _CONTAINER_ID.fullmatch(identity)
                or not isinstance(image, str) or not _IMAGE_ID.fullmatch(image)
                or not isinstance(config, dict) or not isinstance(host, dict)):
            raise StateError("missing Docker identity or configuration")
        labels = config.get("Labels")
        if (not isinstance(labels, dict)
                or labels.get("com.docker.compose.project") != project
                or labels.get("com.docker.compose.service") != service
                or service not in {"backend", "worker", "migrate", "seed"}):
            raise StateError("Docker project or service mismatch")
        policy = host.get("RestartPolicy")
        if not isinstance(policy, dict) or set(policy) != {"Name", "MaximumRetryCount"}:
            raise StateError("invalid full restart policy")
        name, retries = policy["Name"], policy["MaximumRetryCount"]
        if (name not in {"no", "always", "unless-stopped", "on-failure"}
                or type(retries) is not int or retries < 0
                or (name != "on-failure" and retries != 0)):
            raise StateError("invalid restart policy or retry count")
        host_without_policy = {key: value for key, value in host.items() if key != "RestartPolicy"}
        return cls(identity, image, service, name, retries,
                   _encoded(config), _encoded(host_without_policy))

    def assert_fenced_identity(self, row, project):
        actual = self.capture(row, project, self.service)
        state = row.get("State")
        if (actual.identity != self.identity or actual.image != self.image
                or actual.config != self.config or actual.host_config != self.host_config
                or actual.policy_name != "no" or actual.policy_maximum_retry_count != 0
                or not isinstance(state, dict)
                or state.get("Status") not in ("created", "exited")
                or any(state.get(key) is not False for key in ("Running", "Paused", "Restarting"))):
            raise StateError("fenced container identity, configuration, policy or state drifted")


def require_committed_receipt_locked(store: CutoverStore, identity: Identity):
    """Recheck the exact on-disk receipt; caller must hold hold_phase's lock.

    Do not call show() here: lifecycle callbacks already own the nonrecursive
    lock. The lifecycle also verifies the held entry on leaving the callback.
    This check does not itself permit any SQL, Docker, or edge change.
    """
    if not isinstance(store, CutoverStore) or not isinstance(identity, Identity):
        raise StateError("invalid receipt check target")
    store._check_process()
    with store._state_directory() as directory:
        manifest, stamp = store._matching(directory, identity)
        if manifest.phase is not Phase.COMMITTED_WRITERS_ALLOWED:
            raise StateError("exact committed receipt required")
        os.fsync(directory)
        store._check_entry(directory, stamp)


if __name__ == "__main__":
    print("G5 actual reopen rehearsal is not implemented; no action taken", file=sys.stderr)
    raise SystemExit(2)
