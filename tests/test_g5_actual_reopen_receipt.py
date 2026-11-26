"""Durable, secret-free original parameters for the CI reopen rehearsal."""

import hashlib
import json
import os
import stat
from dataclasses import asdict, replace

import pytest

from ops.ci_g5_actual_reopen import (
    OriginalContainer,
    OriginalDatabase,
    require_original_receipt,
    write_original_receipt,
)
from ops.g5_cutover_state import StateError


SECRET = "fixture-secret-never-persist-71c3"


def original_database():
    return OriginalDatabase(
        database="game_ci", database_oid=100, app_role="game_app", app_role_oid=101,
        maintenance_role="postgres", maintenance_role_oid=102, connection_limit=12,
        login=True, server_version_num=150009,
    )


def inspection(service="worker", identity="a"):
    return {
        "Id": identity * 64,
        "Image": "sha256:" + "b" * 64,
        "Config": {
            "Labels": {
                "com.docker.compose.project": "ci_project",
                "com.docker.compose.service": service,
            },
            "Env": ["VALUE:" + SECRET],
            "Cmd": ["python", "-m", "worker"],
        },
        "HostConfig": {
            "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 4},
            "NetworkMode": "ci_project",
            "ExtraHosts": ["secret:" + SECRET],
        },
    }


def captured(row):
    return OriginalContainer.capture(
        row, "ci_project", row["Config"]["Labels"]["com.docker.compose.service"]
    )


@pytest.fixture
def originals():
    return original_database(), [captured(inspection())]


def test_receipt_persists_original_parameters_without_raw_docker_configuration(tmp_path, originals):
    path = tmp_path / "original.json"
    database, containers = originals

    write_original_receipt(path, database, containers)
    raw = path.read_text()
    payload = json.loads(raw)
    assert stat.S_ISREG(path.stat().st_mode)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert SECRET not in raw
    assert "ExtraHosts" not in raw and "python" not in raw
    assert '"Env"' not in raw
    original = payload["original"]
    assert original["database"] == asdict(database)
    assert original["containers"] == [{
        "identity": containers[0].identity,
        "image": containers[0].image,
        "service": "worker",
        "policy_name": "on-failure",
        "policy_maximum_retry_count": 4,
        "config_sha256": hashlib.sha256(containers[0].config.encode()).hexdigest(),
        "host_config_sha256": hashlib.sha256(containers[0].host_config.encode()).hexdigest(),
    }]
    canonical = json.dumps(original, sort_keys=True, separators=(",", ":")).encode()
    assert payload["sha256"] == hashlib.sha256(canonical).hexdigest()

    # Recreate the inputs independently, as after a fresh inspection.
    require_original_receipt(path, original_database(), [captured(inspection())])


def test_receipt_flushes_file_and_parent_directory(tmp_path, originals, monkeypatch):
    path = tmp_path / "original.json"
    synced = []
    real_fsync = os.fsync

    def recording_fsync(fd):
        synced.append(os.fstat(fd))
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", recording_fsync)
    write_original_receipt(path, *originals)
    assert any(stat.S_ISREG(info.st_mode) for info in synced)
    parent = tmp_path.stat()
    assert any(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino)
               == (parent.st_dev, parent.st_ino) for info in synced)


@pytest.mark.parametrize("changes", [
    {"database": "other_ci"}, {"database_oid": 200},
    {"app_role": "other_app"}, {"app_role_oid": 201},
    {"maintenance_role": "other_admin"}, {"maintenance_role_oid": 202},
    {"connection_limit": -1}, {"server_version_num": 150010},
])
def test_receipt_rejects_database_identity_or_parameter_drift(tmp_path, originals, changes):
    path = tmp_path / "original.json"
    database, containers = originals
    write_original_receipt(path, database, containers)
    with pytest.raises(StateError):
        require_original_receipt(path, replace(database, **changes), containers)


@pytest.mark.parametrize("path_parts,value", [
    (("Id",), "c" * 64),
    (("Image",), "sha256:" + "c" * 64),
    (("Config", "Cmd"), ["other"]),
    (("Config", "Env"), ["VALUE:changed"]),
    (("HostConfig", "NetworkMode"), "different"),
    (("HostConfig", "RestartPolicy", "Name"), "always"),
    (("HostConfig", "RestartPolicy", "MaximumRetryCount"), 3),
])
def test_receipt_rejects_container_identity_config_or_policy_drift(
    tmp_path, originals, path_parts, value
):
    path = tmp_path / "original.json"
    database, containers = originals
    write_original_receipt(path, database, containers)
    row = inspection()
    if path_parts == ("HostConfig", "RestartPolicy", "Name"):
        row["HostConfig"]["RestartPolicy"]["MaximumRetryCount"] = 0
    target = row
    for key in path_parts[:-1]:
        target = target[key]
    target[path_parts[-1]] = value
    with pytest.raises(StateError) as error:
        require_original_receipt(path, database, [captured(row)])
    assert SECRET not in str(error.value)


def test_receipt_rejects_missing_or_added_container(tmp_path, originals):
    path = tmp_path / "original.json"
    database, containers = originals
    write_original_receipt(path, database, containers)
    extra = captured(inspection("backend", "c"))
    for candidate in ([], containers + [extra]):
        with pytest.raises(StateError):
            require_original_receipt(path, database, candidate)


def test_receipt_inventory_is_order_independent(tmp_path, originals):
    path = tmp_path / "original.json"
    database, containers = originals
    inventory = containers + [captured(inspection("backend", "c"))]
    write_original_receipt(path, database, inventory)
    require_original_receipt(path, database, list(reversed(inventory)))


@pytest.mark.parametrize("duplicate", ["identity", "service"])
def test_receipt_rejects_duplicate_container_identity_or_service(tmp_path, originals, duplicate):
    database, containers = originals
    row = inspection("backend", "a" if duplicate == "identity" else "c")
    if duplicate == "service":
        row = inspection("worker", "c")
    with pytest.raises(StateError):
        write_original_receipt(tmp_path / "original.json", database, containers + [captured(row)])


def test_receipt_cannot_be_overwritten(tmp_path, originals):
    path = tmp_path / "original.json"
    write_original_receipt(path, *originals)
    before = path.read_bytes()
    with pytest.raises(StateError):
        write_original_receipt(path, *originals)
    assert path.read_bytes() == before


@pytest.mark.parametrize("tamper", ["truncated", "checksum", "malformed"])
def test_receipt_rejects_corruption_without_leaking_content(tmp_path, originals, tamper):
    path = tmp_path / "original.json"
    write_original_receipt(path, *originals)
    if tamper == "truncated":
        raw = path.read_bytes()
        path.write_bytes(raw[:len(raw) // 2])
    elif tamper == "checksum":
        raw = path.read_text()
        path.write_text(raw.replace("game_ci", "other_ci"))
    else:
        path.write_text('{"bad":"' + SECRET)
    with pytest.raises(StateError) as error:
        require_original_receipt(path, *originals)
    assert SECRET not in str(error.value)


def test_receipt_rejects_unsafe_mode_and_symlink(tmp_path, originals):
    path = tmp_path / "original.json"
    write_original_receipt(path, *originals)
    path.chmod(0o644)
    with pytest.raises(StateError):
        require_original_receipt(path, *originals)
    path.chmod(0o600)
    actual = tmp_path / "actual.json"
    path.rename(actual)
    path.symlink_to(actual)
    with pytest.raises(StateError):
        require_original_receipt(path, *originals)


def test_receipt_rejects_hard_link_and_unsafe_parent(tmp_path, originals):
    path = tmp_path / "original.json"
    write_original_receipt(path, *originals)
    link = tmp_path / "hardlink"
    os.link(path, link)
    with pytest.raises(StateError):
        require_original_receipt(path, *originals)
    link.unlink()
    tmp_path.chmod(0o777)
    try:
        with pytest.raises(StateError):
            require_original_receipt(path, *originals)
    finally:
        tmp_path.chmod(0o700)


def test_receipt_rejects_fsync_failure(tmp_path, originals, monkeypatch):
    def failed_fsync(fd):
        raise OSError("simulated flush failure")

    monkeypatch.setattr(os, "fsync", failed_fsync)
    with pytest.raises(StateError):
        write_original_receipt(tmp_path / "original.json", *originals)
