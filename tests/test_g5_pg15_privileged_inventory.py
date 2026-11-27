"""Read-only inventory validation and ambiguous-response regressions."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_pg15_writer_fence import Pg15FenceTarget
from ops.g5_pg15_privileged_inventory import (
    CLUSTER_CHECKS, DATABASE_CHECKS, InventoryError, inspect_privileged_inventory,
)


TARGET = Pg15FenceTarget("game_ci", "game_app", "postgres")


def flags(names, *blockers):
    return "|".join("0" if name in blockers else "1" for name in names)


class Reader:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def query(self, database, statement):
        self.calls.append((database, statement))
        assert statement.startswith("SELECT CASE WHEN")
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.mark.parametrize("fenced", [False, True])
def test_positive_observation_is_not_authority(fenced):
    reader = Reader(flags(CLUSTER_CHECKS), flags(DATABASE_CHECKS), flags(DATABASE_CHECKS), flags(CLUSTER_CHECKS))
    observation = inspect_privileged_inventory(TARGET, reader, fenced=fenced)
    assert observation.blockers == ()
    assert [db for db, _ in reader.calls] == ["postgres", "postgres", "game_ci", "postgres"]
    assert all("transaction_read_only" in sql for _, sql in reader.calls)
    assert ("NOT rolcanlogin" if fenced else "AND rolcanlogin") in reader.calls[0][1]


@pytest.mark.parametrize("blocker", CLUSTER_CHECKS)
def test_cluster_blocker_prevents_target_connection(blocker):
    reader = Reader(flags(CLUSTER_CHECKS, blocker))
    assert inspect_privileged_inventory(TARGET, reader, fenced=False).blockers == (blocker,)
    assert len(reader.calls) == 1


@pytest.mark.parametrize("blocker", DATABASE_CHECKS)
def test_target_blockers_rechecked_after_connection_closes(blocker):
    reader = Reader(flags(CLUSTER_CHECKS), flags(DATABASE_CHECKS), flags(DATABASE_CHECKS, blocker),
                    flags(CLUSTER_CHECKS, "client_sessions"))
    assert inspect_privileged_inventory(TARGET, reader, fenced=True).blockers == (
        blocker, "client_sessions"
    )
    assert len(reader.calls) == 4


@pytest.mark.parametrize("invalid", [None, True, "", "1", "1|0|bogus", "2|" * 12,
                                      ValueError("driver secret=do-not-log")])
def test_ambiguous_evidence_fails_without_credentials(invalid):
    reader = Reader(invalid)
    with pytest.raises(InventoryError) as error:
        inspect_privileged_inventory(TARGET, reader, fenced=True)
    assert "do-not-log" not in str(error.value)


def test_invalid_fence_flag_rejected():
    with pytest.raises(InventoryError):
        inspect_privileged_inventory(TARGET, Reader(), fenced=1)


@pytest.mark.parametrize("name", ["template0", "template1"])
def test_template_database_rejected(name):
    with pytest.raises(InventoryError):
        inspect_privileged_inventory(Pg15FenceTarget(name, "game_app", "postgres"),
                                     Reader(), fenced=False)


@pytest.mark.parametrize("blocker", DATABASE_CHECKS)
def test_maintenance_catalog_not_ignored(blocker):
    reader = Reader(flags(CLUSTER_CHECKS), flags(DATABASE_CHECKS, blocker),
                    flags(DATABASE_CHECKS), flags(CLUSTER_CHECKS))
    assert inspect_privileged_inventory(TARGET, reader, fenced=False).blockers == (blocker,)
    assert [db for db, _ in reader.calls] == ["postgres", "postgres", "game_ci", "postgres"]


def test_inventory_checks_parameter_acl_not_only_current_settings():
    reader = Reader(flags(CLUSTER_CHECKS, "no_parameter_grants"))
    assert inspect_privileged_inventory(TARGET, reader, fenced=False).blockers == ("no_parameter_grants",)
    assert "pg_parameter_acl" in reader.calls[0][1]
    assert "ALTER SYSTEM" in reader.calls[0][1]


def test_stock_pg_settings_exception_is_narrow():
    reader = Reader(flags(CLUSTER_CHECKS), flags(DATABASE_CHECKS),
                    flags(DATABASE_CHECKS), flags(CLUSTER_CHECKS))
    assert inspect_privileged_inventory(TARGET, reader, fenced=False).blockers == ()
    statement = reader.calls[1][1]
    assert "c.relname<>'pg_settings' OR c.relkind<>'v' OR c.oid>=16384" in statement
    assert "INSERT,DELETE,TRUNCATE,TRIGGER" in statement
    assert "aclexplode(c.relacl)" in statement


def test_server_file_acl_is_independent_of_initdb_acl():
    reader = Reader(flags(CLUSTER_CHECKS), flags(DATABASE_CHECKS),
                    flags(DATABASE_CHECKS), flags(CLUSTER_CHECKS))
    assert inspect_privileged_inventory(TARGET, reader, fenced=False).blockers == ()
    sql = reader.calls[1][1]
    assert "p.proname IN ('lo_import','lo_export')" in sql
    assert "p.proowner=(SELECT oid FROM pg_roles" in sql
    assert "has_function_privilege" in sql
