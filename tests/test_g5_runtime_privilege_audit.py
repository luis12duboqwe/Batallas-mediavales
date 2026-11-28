"""Scoped privilege assertions fail closed on ambiguous catalog evidence."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_pg15_writer_fence import Pg15FenceTarget
from ops.g5_runtime_privilege_audit import AuditError, RelationRule, inspect_runtime_privileges


TARGET = Pg15FenceTarget("game_ci", "game_app", "postgres")
RULES = (
    RelationRule("hero_items", "table", frozenset({"SELECT", "UPDATE"}), frozenset({"DELETE"})),
    RelationRule("hero_items_id_seq", "sequence", frozenset({"USAGE"}), frozenset({"UPDATE"})),
)


class Reader:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def query(self, database, sql):
        self.calls.append((database, sql))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_observation_checks_scoped_effective_privileges_in_one_read_only_snapshot():
    reader = Reader("|".join(["1"] * 22))
    assert inspect_runtime_privileges(TARGET, reader, RULES).blockers == ()
    assert len(reader.calls) == 1
    database, sql = reader.calls[0]
    assert database == "game_ci"
    assert sql.startswith("SELECT CASE WHEN")
    assert "transaction_read_only" in sql and "server_version_num" in sql
    assert "has_table_privilege" in sql and "has_sequence_privilege" in sql
    assert "has_any_column_privilege" not in sql  # DELETE has no column privilege
    assert "c.relowner" in sql


def test_missing_relation_and_missing_and_unexpected_privileges_are_distinct():
    values = ["1"] * 22
    values[11] = values[14] = values[16] = "0"
    result = inspect_runtime_privileges(TARGET, Reader("|".join(values)), RULES)
    assert result.blockers == ("hero_items:exists", "hero_items:missing:SELECT",
                               "hero_items:unexpected:DELETE")


def test_forbidden_column_acl_is_checked():
    rule = RelationRule("item_templates", "table", frozenset({"SELECT"}), frozenset({"UPDATE"}))
    reader = Reader("|".join(["1"] * 16))
    inspect_runtime_privileges(TARGET, reader, (rule,))
    assert "has_any_column_privilege('game_app'" in reader.calls[0][1]


@pytest.mark.parametrize("response", [None, "", "1|0", "1|" * 15, "2|" * 14 + "1",
                                      "1\n0", RuntimeError("credential-value")])
def test_bad_or_unavailable_evidence_fails_without_exposing_errors(response):
    with pytest.raises(AuditError) as error:
        inspect_runtime_privileges(TARGET, Reader(response), RULES)
    assert "credential-value" not in str(error.value)


@pytest.mark.parametrize("args", [
    ("x'; DROP TABLE users;--", "table", frozenset({"SELECT"}), frozenset()),
    ("users", "view", frozenset({"SELECT"}), frozenset()),
    ("users", "table", frozenset({"SELECT"}), frozenset({"SELECT"})),
    ("users", "table", frozenset({"USAGE"}), frozenset()),
    ("users", "table", {"SELECT"}, frozenset()),
    ("users", "sequence", frozenset(), frozenset()),
])
def test_invalid_rules_are_rejected(args):
    with pytest.raises(AuditError):
        RelationRule(*args)


@pytest.mark.parametrize("rules", [(), [], (RULES[0], RULES[0]), ("not a rule",)])
def test_invalid_manifest_is_rejected_before_query(rules):
    reader = Reader("")
    with pytest.raises(AuditError):
        inspect_runtime_privileges(TARGET, reader, rules)
    assert reader.calls == []
