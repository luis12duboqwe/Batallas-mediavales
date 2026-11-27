"""CI-only logical snapshot restore into independent, fenced PG15 clusters.

Reuses the full-schema laboratory; no host adapter or production execution.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from ops.ci_g5_full_schema_restore import (
    DB, PREVIOUS, ROOT, Fixture, RehearsalError, Snapshot,
    command, docker, require,
)


_HEX = re.compile(r"[0-9a-f]{64}")
_SYSTEM_ID = re.compile(r"[1-9][0-9]{0,19}")


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _single(raw):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise RehearsalError("ambiguous Docker evidence") from None
    require(isinstance(value, list) and len(value) == 1
            and isinstance(value[0], dict), "ambiguous Docker evidence")
    return value[0]


def identity(fixture):
    """Observe database, container, network and mounted volume independently."""
    row = _single(docker(["inspect", "--type", "container", fixture.name]).stdout)
    net = _single(docker(["network", "inspect", fixture.network]).stdout)
    cid, nid = row.get("Id"), net.get("Id")
    require(isinstance(cid, str) and _HEX.fullmatch(cid)
            and isinstance(nid, str) and _HEX.fullmatch(nid),
            "invalid fixture container/network identity")
    label = fixture.label.split("=", 1)
    require(row.get("Config", {}).get("Labels", {}).get(label[0]) == label[1]
            and net.get("Labels", {}).get(label[0]) == label[1]
            and net.get("Internal") is True
            and row.get("HostConfig", {}).get("PortBindings") in (None, {})
            and row.get("State", {}).get("Running") is True,
            "fixture is not isolated")
    networks = row.get("NetworkSettings", {}).get("Networks")
    require(isinstance(networks, dict) and set(networks) == {fixture.network}
            and networks[fixture.network].get("NetworkID") == nid
            and set(net.get("Containers") or {}) == {cid},
            "unexpected network member or attachment")
    mounts = row.get("Mounts", [])
    require(isinstance(mounts, list) and len(mounts) == 1
            and mounts[0].get("Type") == "volume"
            and mounts[0].get("Destination") == "/var/lib/postgresql/data",
            "unexpected database mount")
    volume = mounts[0].get("Name")
    require(isinstance(volume, str) and _HEX.fullmatch(volume),
            "database volume identity missing")
    info = _single(docker(["volume", "inspect", volume]).stdout)
    require(info.get("Name") == volume and info.get("Driver") == "local"
            and info.get("Mountpoint") == mounts[0].get("Source"),
            "database volume identity changed")
    system_id = fixture.admin.scalar(
        "SELECT system_identifier::text FROM pg_control_system();", "postgres")
    require(isinstance(system_id, str) and _SYSTEM_ID.fullmatch(system_id)
            and int(system_id) < 2**64, "invalid PostgreSQL system identifier")
    db = fixture.database_identity()
    require(isinstance(db, str) and re.fullmatch(r"[1-9][0-9]*:" + DB + r":[1-9][0-9]*", db),
            "invalid database identity")
    return {"container": cid, "network": nid, "volume": volume,
            "system_identifier": system_id, "database": db}


def require_distinct(*identities):
    require(len(identities) >= 2, "independent cluster identities required")
    for field in ("container", "network", "volume", "system_identifier"):
        require(all(isinstance(item, dict) and isinstance(item.get(field), str)
                    and item[field] for item in identities),
                "incomplete independent cluster identity")
        require(len({item[field] for item in identities}) == len(identities),
                "logical restore target aliases another cluster")


def assert_same_data(source, restored):
    # A logical restore can assign new database OIDs. Rows, sequences,
    # database settings and namespace ACL/owner must still be identical.
    for field in ("rows", "sequences", "database", "namespace"):
        require(field in source and field in restored and source[field] == restored[field],
                "logical clone data or metadata mismatch: " + field)


def compare_clone(source, witness, clone):
    assert_same_data(source, witness)
    assert_same_data(source, clone)
    require(bool(witness.get("catalog")) and witness["catalog"] == clone.get("catalog"),
            "logical clone catalog differs from independent archive witness")
    return {
        "source_catalog_sha256": digest(source["catalog"]),
        "restored_catalog_sha256": digest(clone["catalog"]),
        "data_sha256": digest({"rows": source["rows"], "sequences": source["sequences"]}),
    }


def restore_empty(fixture, expected_identity, receipt, fd):
    fixture.closed()
    require(identity(fixture) == expected_identity, "clone identity drift")
    require(fixture.admin.scalar(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f','S');"
    ) == "0", "logical restore target is not empty")
    # Never use --clean, --create, database replacement or a live target.
    payload = receipt.read_verified(fd)
    docker(["exec", "-i", fixture.name, "pg_restore", "--single-transaction",
            "--exit-on-error", "-U", "postgres", "-d", DB], input=payload)
    fixture.closed()
    require(identity(fixture) == expected_identity, "clone identity changed during restore")
    return fixture.inventory()


def rehearse(image, workspace):
    source, witness, clone = [Fixture(image) for _ in range(3)]
    fixtures = (source, witness, clone)
    success = False
    fd = None
    try:
        source.start()
        source.migrate(PREVIOUS)
        source.seed()  # actual committed app update and active app session
        source.fence().engage()
        source.closed()
        source.scope()
        before = identity(source)
        baseline = source.inventory()
        require(baseline["rows"] and baseline["sequences"]
                and source.admin.scalar("SELECT name FROM worlds;") == "app-confirmed",
                "committed source data absent")
        receipt = Snapshot.capture(workspace / "source.dump", source.dump("--format=custom"))
        fd = receipt.open_verified()
        source.closed()
        require(identity(source) == before and source.inventory() == baseline,
                "source changed during snapshot")
        # Two separately initialized clusters provide the archive's canonical
        # deparse witness and the independently verified logical clone.
        for target in (witness, clone):
            target.start()
            target.fence().engage()
            target.closed()
        observed = [before, identity(witness), identity(clone)]
        require_distinct(*observed)
        docker(["exec", "-i", source.name, "pg_restore", "--list"],
               input=receipt.read_verified(fd))
        restored_witness = restore_empty(witness, observed[1], receipt, fd)
        source.closed()
        require(identity(source) == before and source.inventory() == baseline,
                "source changed during witness restore")
        restored_clone = restore_empty(clone, observed[2], receipt, fd)
        evidence = compare_clone(baseline, restored_witness, restored_clone)
        source.closed()
        require(identity(source) == before and source.inventory() == baseline,
                "source changed during clone restore")
        for target, expected in zip((witness, clone), observed[1:]):
            target.closed()
            require(identity(target) == expected, "restored target identity drift")
        require_distinct(*(identity(item) for item in fixtures))
        receipt.read_verified(fd)
        success = True
        return evidence | {
            "snapshot_sha256": receipt.sha256,
            "source": before, "clone": observed[2],
            "independent_witness": observed[1],
            "table_count": len(baseline["rows"]),
            "sequence_count": len(baseline["sequences"]),
            "logical_clone_verified": True,
            "external_backup_verified": False,
            "production_authorized": False,
        }
    finally:
        if fd is not None:
            os.close(fd)
        if success:
            for fixture in reversed(fixtures):
                fixture.cleanup()
        else:
            # Preserve the owned disposable resources and archive for
            # diagnosis. Never reopen roles after an uncertain result.
            for fixture in fixtures:
                if fixture.identity is not None:
                    try:
                        fixture.fence().engage()
                    except BaseException:
                        pass
            print("logical clone failed; fixture evidence retained for CI diagnosis",
                  file=sys.stderr)


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        return 2
    workspace = Path(tempfile.mkdtemp(prefix="bm-g5-logical-clone-"))
    try:
        sha = command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.decode().strip()
        require(re.fullmatch(r"[0-9a-f]{40}", sha), "checkout identity unavailable")
        tag = "bm-g5-full-schema-head:" + sha
        row = _single(docker(["image", "inspect", tag]).stdout)
        image = row.get("Id")
        require(isinstance(image, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", image)
                and tag in (row.get("RepoTags") or []), "exact CI-built backend image missing")
        result = rehearse(image, workspace)
        (workspace / "source.dump").unlink()
        workspace.rmdir()
        print(json.dumps(result | {"head": sha, "image_id": image}, sort_keys=True))
        return 0
    except (RehearsalError, OSError, ValueError):
        print("logical clone rehearsal failed; no release authorization", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
