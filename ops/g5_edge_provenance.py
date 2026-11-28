"""Content-pinned evidence for a deliberately started, isolated edge stack."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat


class ProvenanceError(RuntimeError):
    """The controlled edge runtime no longer matches its launch contract."""


_ID = re.compile(r"[0-9a-f]{64}")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_IMPORT = re.compile(r"^\s*(?:include|import)\b", re.IGNORECASE | re.MULTILINE)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixed_config(name: str, content: bytes, expected_sha256: str) -> str:
    """Validate exact config bytes and reject independently resolved includes."""
    if name not in {"Caddyfile", "nginx.conf", "frontend.conf"}:
        raise ProvenanceError("unknown edge configuration")
    if not isinstance(content, bytes) or sha256(content) != expected_sha256:
        raise ProvenanceError("edge configuration content changed")
    if _IMPORT.search(content.decode("utf-8", errors="replace")):
        raise ProvenanceError("edge configuration contains an include or import")
    return expected_sha256


@dataclass(frozen=True)
class ContainerContract:
    service: str
    container_id: str
    image_id: str
    network_name: str
    network_id: str
    alias: str
    command: tuple[str, ...]
    uid: int
    bind_mounts: tuple[tuple[str, str], ...] = ()
    tmpfs_options: tuple[tuple[str, str], ...] = ()


def verify_process_identity(command_line: bytes, status: str,
                            contract: ContainerContract) -> None:
    if not isinstance(command_line, bytes):
        raise ProvenanceError("process command line unavailable")
    command = tuple(part.decode("utf-8", errors="strict")
                    for part in command_line.rstrip(b"\0").split(b"\0"))
    match = re.search(r"^Uid:\s+(\d+)\b", status, re.MULTILINE)
    if command != contract.command or match is None or int(match.group(1)) != contract.uid:
        raise ProvenanceError("PID 1 does not match the controlled process contract")


def verify_container(row: dict, contract: ContainerContract,
                     command_line: bytes, process_status: str) -> None:
    if (not isinstance(contract.container_id, str) or not _ID.fullmatch(contract.container_id)
            or not isinstance(contract.image_id, str) or not _IMAGE_ID.fullmatch(contract.image_id)
            or not isinstance(contract.network_id, str) or not _ID.fullmatch(contract.network_id)):
        raise ProvenanceError("invalid pinned runtime identity")
    if not isinstance(row, dict):
        raise ProvenanceError("container inspection unavailable")
    config = row.get("Config")
    host = row.get("HostConfig")
    state = row.get("State")
    labels = config.get("Labels") if isinstance(config, dict) else None
    expected_user = f"{contract.uid}:{contract.uid}"
    network_settings = row.get("NetworkSettings")
    networks = network_settings.get("Networks") if isinstance(network_settings, dict) else None
    restart_policy = host.get("RestartPolicy") if isinstance(host, dict) else None
    mounts = row.get("Mounts")
    if (row.get("Id") != contract.container_id
            or row.get("Image") != contract.image_id
            or row.get("Path") != contract.command[0]
            or not isinstance(row.get("Args"), (list, tuple))
            or tuple(row["Args"]) != contract.command[1:]
            or not isinstance(state, dict) or state.get("Running") is not True
            or state.get("Paused") is not False
            or not isinstance(labels, dict)
            or labels.get("medievol.g5.edge-fixture") != contract.network_name
            or labels.get("com.docker.compose.project") != contract.network_name
            or labels.get("com.docker.compose.service") != contract.service
            or config.get("User") != expected_user
            or not isinstance(host, dict)
            or host.get("Privileged") is not False
            or host.get("ReadonlyRootfs") is not True
            or host.get("CapAdd") not in (None, [])
            or host.get("CapDrop") != ["ALL"]
            or host.get("SecurityOpt") != ["no-new-privileges:true"]
            or not isinstance(restart_policy, dict) or restart_policy.get("Name") != "no"
            or host.get("PortBindings") not in (None, {})
            or host.get("PublishAllPorts") is not False
            or host.get("NetworkMode") != contract.network_name
            or host.get("Memory") != 512 * 1024 * 1024
            or host.get("NanoCpus") != 1_000_000_000
            or host.get("PidsLimit") != 64
            or not isinstance(networks, dict) or len(networks) != 1
            or contract.network_name not in networks
            or not isinstance(networks.get(contract.network_name), dict)
            or networks[contract.network_name].get("NetworkID") != contract.network_id
            or contract.alias not in networks[contract.network_name].get("Aliases", [])
            or not isinstance(mounts, list)):
        raise ProvenanceError("container identity, isolation, or launch settings drifted")

    expected_mounts = {target: source for source, target in contract.bind_mounts}
    observed_mounts = {}
    observed_tmpfs = set()
    for mount in mounts:
        if not isinstance(mount, dict):
            raise ProvenanceError("malformed container mount")
        if mount.get("Type") == "tmpfs":
            destination = mount.get("Destination")
            if not isinstance(destination, str) or destination in observed_tmpfs:
                raise ProvenanceError("unsafe or duplicate container tmpfs")
            observed_tmpfs.add(destination)
            continue
        if mount.get("Type") != "bind":
            raise ProvenanceError("unexpected container mount")
        destination = mount.get("Destination")
        if (not isinstance(destination, str) or mount.get("RW") is not False
                or destination in observed_mounts):
            raise ProvenanceError("unsafe or duplicate container mount")
        observed_mounts[destination] = mount.get("Source")
    host_tmpfs = host.get("Tmpfs") or {}
    expected_tmpfs = dict(contract.tmpfs_options)
    if (not isinstance(host_tmpfs, dict)
            or observed_mounts != expected_mounts
            or observed_tmpfs != set(expected_tmpfs)
            or host_tmpfs != expected_tmpfs):
        raise ProvenanceError("container bind mounts differ from the launch contract")
    verify_process_identity(command_line, process_status, contract)


def verify_network(row: dict, network_id: str, fixture: str,
                   container_ids: set[str] | None = None) -> None:
    labels = row.get("Labels") if isinstance(row, dict) else None
    containers = row.get("Containers") if isinstance(row, dict) else None
    options = row.get("Options") if isinstance(row, dict) else None
    if (not isinstance(row, dict) or not isinstance(network_id, str)
            or not _ID.fullmatch(network_id) or row.get("Id") != network_id
            or row.get("Name") != fixture or row.get("Driver") != "bridge"
            or row.get("Internal") is not True
            or row.get("EnableIPv6") is not False
            or not isinstance(labels, dict)
            or labels.get("medievol.g5.edge-fixture") != fixture
            or (options is not None and not isinstance(options, dict))
            or (isinstance(options, dict)
                and options.get("com.docker.network.bridge.host_binding_ipv4") not in (None, ""))
            or (container_ids is not None
                and (not isinstance(containers, dict) or set(containers) != container_ids))):
        raise ProvenanceError("isolated Docker network identity drifted")


def read_config(path: str | os.PathLike[str], expected_sha256: str) -> str:
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022):
            raise ProvenanceError("edge configuration is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            content = stream.read()
    except ProvenanceError:
        raise
    except OSError:
        raise ProvenanceError("edge configuration unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)
    digest = fixed_config(Path(path).name, content, expected_sha256)
    return digest


def legacy_host_observation(*, container_id: str | None = None,
                            image_ref: str | None = None,
                            probe_results: tuple[int, ...] = ()) -> dict:
    """Label retrospective facts without implying which config a process loaded."""
    return {
        "kind": "legacy-host-observation",
        "container_id": container_id,
        "image_ref": image_ref,
        "probe_results": list(probe_results),
        "proves_loaded_configuration": False,
        "proves_absence_of_bypass": False,
        "status": "inconclusive",
    }
