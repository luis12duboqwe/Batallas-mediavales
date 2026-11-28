"""Offline checks for independent clone evidence; actual PG15 drill in CI."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops import ci_g5_logical_clone as clone
from ops.ci_g5_full_schema_restore import RehearsalError


def fixture_identity(prefix):
    return {k: prefix + k for k in ("container", "network", "volume", "system_identifier")}


@pytest.mark.parametrize("field", ["container", "network", "volume", "system_identifier"])
def test_clone_must_not_alias_source_or_witness(field):
    source, witness, target = (fixture_identity(p) for p in ("a", "b", "c"))
    clone.require_distinct(source, witness, target)
    target[field] = source[field]
    with pytest.raises(RehearsalError):
        clone.require_distinct(source, witness, target)
    target[field] = witness[field]
    with pytest.raises(RehearsalError):
        clone.require_distinct(source, witness, target)


def inventory():
    return {"rows": {"worlds": '[{"id":1}]'}, "sequences": {"worlds_id_seq": "1:t"},
            "database": "database-settings", "namespace": "public-acl",
            "catalog": ("catalog",)}


@pytest.mark.parametrize("field", ["rows", "sequences", "database", "namespace", "catalog"])
def test_clone_mismatch_rejected(field):
    source = inventory()
    witness = deepcopy(source)
    target = deepcopy(source)
    target[field] = "changed"
    with pytest.raises(RehearsalError):
        clone.compare_clone(source, witness, target)


def test_archive_witness_accounts_for_pg15_deparse_not_data_drift():
    source = inventory()
    witness = deepcopy(source)
    witness["catalog"] = ("restored canonical catalog",)
    result = clone.compare_clone(source, witness, deepcopy(witness))
    assert result["source_catalog_sha256"] != result["restored_catalog_sha256"]
    assert result["data_sha256"] == clone.digest(
        {"rows": source["rows"], "sequences": source["sequences"]})


def test_guard_refuses_non_hosted_runner(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "self-hosted")
    monkeypatch.setattr(clone, "docker", lambda *_: pytest.fail("must not access Docker"))
    assert clone.main() == 2
