"""Unit tests for the disposable role lab's catalog and entry guards.

The catalog responses are synthetic; these tests do not exercise PostgreSQL.
"""
import copy
import json

import pytest

from ops import ci_g5_role_provisioning as policy
from ops.g5_pg15_writer_fence import Pg15FenceTarget


TARGET = Pg15FenceTarget("game_migration_ci", "game_app", "postgres")


def catalog(revision, granted_revision=None):
    grants = policy.table_privileges(granted_revision) if granted_revision else {}
    owner_table_privileges = (
        "SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER",
    )
    objects = [
        {
            "name": name,
            "kind": "r",
            "owner": "postgres",
            "column_acl": False,
            "attached": [],
            "acl": ([["postgres", privilege, False, "postgres"]
                     for privilege in owner_table_privileges]
                    + [["game_app", privilege, False, "postgres"]
                       for privilege in sorted(grants.get(name, ()))]),
        }
        for name in sorted(policy.expected_tables(revision))
    ]
    sequences = [("worlds_id_seq", "worlds")]
    if revision == policy.CANDIDATE:
        sequences.append(("wonder_funding_id_seq", "wonder_funding"))
    for name, table in sequences:
        objects.append({
            "name": name,
            "kind": "S",
            "owner": "postgres",
            "column_acl": False,
            "attached": [table],
            "acl": ([["postgres", privilege, False, "postgres"]
                     for privilege in ("USAGE", "SELECT", "UPDATE")]
                    + ([["game_app", "SELECT", False, "postgres"],
                        ["game_app", "USAGE", False, "postgres"]]
                       if table in grants else [])),
        })
    return {
        "schemas": ["public"],
        "defaults": 0,
        "routines": 0,
        "foreign_sequence_defaults": 0,
        "required_sequences": [name for name, _ in sequences],
        "schema_app_acl": ["USAGE"] if granted_revision else [],
        "schema_ok": True,
        "objects": objects,
    }


class CatalogSession:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def query(self, database, sql):
        self.calls.append((database, sql))
        if "json_build_object" in sql:
            return json.dumps(self.value)
        return "\n".join(
            obj["name"] + "|" + obj["kind"]
            for obj in self.value["objects"] if obj["kind"] in {"r", "p", "v", "m", "f"}
        )


def obj(value, name):
    return next(item for item in value["objects"] if item["name"] == name)


@pytest.mark.parametrize(("revision", "granted"), [
    (policy.PREVIOUS, None),
    (policy.PREVIOUS, policy.PREVIOUS),
    (policy.CANDIDATE, policy.PREVIOUS),
    (policy.CANDIDATE, policy.CANDIDATE),
])
def test_known_catalog_states_accepted(revision, granted):
    session = CatalogSession(catalog(revision, granted))
    result = policy.inspect_objects(TARGET, session, revision, granted_revision=granted)
    assert result == sorted(session.value["required_sequences"])
    assert all(database == TARGET.database for database, _ in session.calls)
    assert all(sql.lstrip().startswith("SELECT ") for _, sql in session.calls)


def test_catalog_query_uses_sequence_default_acl_and_does_not_hide_pgextra():
    session = CatalogSession(catalog(policy.PREVIOUS))
    policy.inspect_objects(TARGET, session, policy.PREVIOUS)
    sql = session.calls[-1][1]
    assert "THEN 's'::\"char\"" in sql
    assert "nspname NOT LIKE 'pg_%'" not in sql
    assert "left(nspname, 3) <> 'pg_'" in sql


@pytest.mark.parametrize("revision", [policy.PREVIOUS, policy.CANDIDATE])
def test_wiki_articles_policy_supports_runtime_writes(revision):
    assert {"SELECT", "INSERT", "UPDATE"} <= policy.table_privileges(revision)["wiki_articles"]


def test_missing_wiki_update_grant_is_drift():
    evidence = catalog(policy.PREVIOUS, policy.PREVIOUS)
    obj(evidence, "wiki_articles")["acl"].remove(["game_app", "UPDATE", False, "postgres"])
    with pytest.raises(policy.ObjectPolicyError):
        policy.inspect_objects(TARGET, CatalogSession(evidence), policy.PREVIOUS,
                               granted_revision=policy.PREVIOUS)


@pytest.mark.parametrize("target", [
    Pg15FenceTarget("other_db", "game_app", "postgres"),
    Pg15FenceTarget("game_migration_ci", "other_app", "postgres"),
    Pg15FenceTarget("game_migration_ci", "game_app", "other_admin"),
    None,
])
def test_wrong_target_rejected_before_inventory(target):
    session = CatalogSession(catalog(policy.PREVIOUS))
    with pytest.raises(policy.ObjectPolicyError):
        policy.inspect_objects(target, session, policy.PREVIOUS)
    assert not session.calls


@pytest.mark.parametrize(("revision", "granted"), [
    ("head", None),
    (policy.PREVIOUS, "head"),
    (policy.PREVIOUS, policy.CANDIDATE),
])
def test_invalid_revision_or_transition_rejected(revision, granted):
    with pytest.raises(policy.ObjectPolicyError):
        policy.inspect_objects(TARGET, CatalogSession(catalog(policy.PREVIOUS)),
                               revision, granted_revision=granted)


def test_unexpected_and_missing_tables_rejected():
    base = catalog(policy.PREVIOUS)
    extra = copy.deepcopy(base)
    extra["objects"].append({**obj(extra, "worlds"), "name": "unknown_table"})
    missing = copy.deepcopy(base)
    missing["objects"].remove(obj(missing, "worlds"))
    duplicate = copy.deepcopy(base)
    duplicate["objects"].append(copy.deepcopy(obj(duplicate, "worlds")))
    for value in (extra, missing, duplicate):
        with pytest.raises(policy.ObjectPolicyError):
            policy.inspect_objects(TARGET, CatalogSession(value), policy.PREVIOUS)


@pytest.mark.parametrize(("field", "value"), [
    ("schemas", ["public", "unreviewed"]),
    ("schemas", ["pgextra", "public"]),
    ("defaults", 1),
    ("routines", 1),
    ("foreign_sequence_defaults", 1),
    ("schema_ok", False),
    ("schema_app_acl", ["USAGE", "CREATE"]),
    ("schema_app_acl", []),
])
def test_schema_and_default_privilege_drift_rejected(field, value):
    evidence = catalog(policy.PREVIOUS, policy.PREVIOUS)
    evidence[field] = value
    with pytest.raises(policy.ObjectPolicyError):
        policy.inspect_objects(TARGET, CatalogSession(evidence), policy.PREVIOUS,
                               granted_revision=policy.PREVIOUS)


@pytest.mark.parametrize("mutation", [
    lambda x: obj(x, "worlds").update(owner="game_app"),
    lambda x: obj(x, "worlds").update(column_acl=True),
    lambda x: obj(x, "worlds").update(kind="v"),
    lambda x: obj(x, "worlds")["acl"].append(["PUBLIC", "SELECT", False, "postgres"]),
    lambda x: obj(x, "worlds")["acl"].append(["other_role", "SELECT", False, "postgres"]),
    lambda x: obj(x, "worlds")["acl"].append(["game_app", "TRUNCATE", False, "postgres"]),
    lambda x: obj(x, "worlds")["acl"].append(["game_app", "SELECT", True, "postgres"]),
    lambda x: obj(x, "worlds")["acl"].remove(["game_app", "UPDATE", False, "postgres"]),
    lambda x: obj(x, "achievements")["acl"].append(["game_app", "UPDATE", False, "postgres"]),
    lambda x: obj(x, "alembic_version")["acl"].append(["game_app", "SELECT", False, "postgres"]),
    lambda x: obj(x, "worlds")["acl"].append(["game_app", "SELECT", False, "postgres"]),
    lambda x: obj(x, "worlds")["acl"].remove(["postgres", "DELETE", False, "postgres"]),
    lambda x: obj(x, "worlds")["acl"].append(["game_app", "TRUNCATE", False, "other_role"]),
])
def test_table_ownership_and_per_table_acl_drift_rejected(mutation):
    evidence = catalog(policy.PREVIOUS, policy.PREVIOUS)
    mutation(evidence)
    with pytest.raises(policy.ObjectPolicyError):
        policy.inspect_objects(TARGET, CatalogSession(evidence), policy.PREVIOUS,
                               granted_revision=policy.PREVIOUS)


@pytest.mark.parametrize("mutation", [
    lambda x: obj(x, "worlds_id_seq").update(attached=[]),
    lambda x: obj(x, "worlds_id_seq").update(attached=["alembic_version"]),
    lambda x: obj(x, "worlds_id_seq").update(attached=["worlds", "cities"]),
    lambda x: obj(x, "worlds_id_seq")["acl"].append(["game_app", "UPDATE", False, "postgres"]),
    lambda x: obj(x, "worlds_id_seq")["acl"].remove(["game_app", "USAGE", False, "postgres"]),
    lambda x: x["required_sequences"].clear(),
    lambda x: x["required_sequences"].append("missing_seq"),
    lambda x: x["objects"].append({
        "name": "rogue_seq", "kind": "S", "owner": "postgres",
        "column_acl": False, "attached": [], "acl": [],
    }),
])
def test_sequence_attachment_and_grant_drift_rejected(mutation):
    evidence = catalog(policy.PREVIOUS, policy.PREVIOUS)
    mutation(evidence)
    with pytest.raises(policy.ObjectPolicyError):
        policy.inspect_objects(TARGET, CatalogSession(evidence), policy.PREVIOUS,
                               granted_revision=policy.PREVIOUS)


def test_ungranted_sequence_still_requires_full_owner_acl():
    evidence = catalog(policy.PREVIOUS)
    obj(evidence, "worlds_id_seq")["acl"].remove(["postgres", "UPDATE", False, "postgres"])
    with pytest.raises(policy.ObjectPolicyError):
        policy.inspect_objects(TARGET, CatalogSession(evidence), policy.PREVIOUS)


def test_candidate_must_not_have_grants_before_provisioning():
    evidence = catalog(policy.CANDIDATE, policy.PREVIOUS)
    obj(evidence, "wonder_funding")["acl"].append(["game_app", "SELECT", False, "postgres"])
    with pytest.raises(policy.ObjectPolicyError):
        policy.inspect_objects(TARGET, CatalogSession(evidence), policy.CANDIDATE,
                               granted_revision=policy.PREVIOUS)


def test_query_failure_is_sanitized():
    class BrokenSession:
        def query(self, *_):
            raise RuntimeError("sensitive connection information")

    with pytest.raises(policy.ObjectPolicyError) as error:
        policy.inspect_objects(TARGET, BrokenSession(), policy.PREVIOUS)
    assert "sensitive" not in str(error.value)


@pytest.mark.parametrize(("missing", "value"), [
    ("CI", None), ("CI", "false"), ("GITHUB_ACTIONS", None),
    ("GITHUB_ACTIONS", "false"), ("RUNNER_ENVIRONMENT", None),
    ("RUNNER_ENVIRONMENT", "self-hosted"),
])
def test_main_requires_github_hosted_ci(monkeypatch, missing, value):
    for key, setting in {"CI": "true", "GITHUB_ACTIONS": "true",
                         "RUNNER_ENVIRONMENT": "github-hosted"}.items():
        monkeypatch.setenv(key, setting)
    if value is None:
        monkeypatch.delenv(missing)
    else:
        monkeypatch.setenv(missing, value)
    monkeypatch.setattr(policy, "_drill", lambda: pytest.fail("drill must not run"))
    assert policy.main([]) == 2


def test_main_rejects_arguments_and_sanitizes_failure(monkeypatch, capsys):
    for key, value in {"CI": "true", "GITHUB_ACTIONS": "true",
                       "RUNNER_ENVIRONMENT": "github-hosted"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(policy, "_drill", lambda: (_ for _ in ()).throw(
        RuntimeError("secret connection data")))
    assert policy.main(["unexpected"]) == 2
    assert policy.main([]) == 1
    assert "secret" not in capsys.readouterr().err


def test_provision_rejects_non_fixture_executor(monkeypatch):
    for key, value in {"CI": "true", "GITHUB_ACTIONS": "true",
                       "RUNNER_ENVIRONMENT": "github-hosted"}.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(policy.ObjectPolicyError):
        policy.provision(TARGET, object(), object(), policy.PREVIOUS)


@pytest.mark.parametrize(("revision", "granted"), [
    (policy.PREVIOUS, None),
    (policy.CANDIDATE, policy.PREVIOUS),
])
def test_provision_issues_only_named_policy_grants(monkeypatch, revision, granted):
    from ops.ci_g5_actual_migration import Admin
    from ops.ci_g5_privileged_inventory import IsolatedAdmin
    from ops import ci_g5_release_transition as release

    for key, value in {"CI": "true", "GITHUB_ACTIONS": "true",
                       "RUNNER_ENVIRONMENT": "github-hosted"}.items():
        monkeypatch.setenv(key, value)
    project = "bm-g5-edge-" + "a" * 32
    monkeypatch.setattr(release, "_container", lambda _: {
        "Config": {"Labels": {"medievol.g5.edge-fixture": project}},
        "NetworkSettings": {"Networks": {project: {}}},
        "Image": "sha256:fixture",
        "HostConfig": {"PortBindings": {}},
    })
    monkeypatch.setattr(release, "_image", lambda _: {"Id": "sha256:fixture"})
    monkeypatch.setattr(release, "_docker_json", lambda *args: {
        "Internal": True, "Labels": {"medievol.g5.edge-fixture": project},
    })
    statements = []
    inspections = []
    monkeypatch.setattr(Admin, "sql", lambda self, statement, database:
                        statements.append((statement, database)))
    monkeypatch.setattr(policy, "_inventory", lambda *args: None)

    def inspect(target, session, checked_revision, *, granted_revision):
        inspections.append(granted_revision)
        return ["worlds_id_seq"]

    monkeypatch.setattr(policy, "inspect_objects", inspect)
    policy.provision(TARGET, Admin("fixture"), IsolatedAdmin("fixture"), revision,
                     granted_revision=granted)
    prior = policy.table_privileges(granted) if granted else {}
    expected = []
    if granted is None:
        expected.append('GRANT USAGE ON SCHEMA public TO "game_app";')
    expected.extend(
        f'GRANT {", ".join(sorted(privileges))} ON TABLE "{name}" TO "game_app";'
        for name, privileges in sorted(policy.table_privileges(revision).items())
        if name not in prior
    )
    expected.append('GRANT USAGE, SELECT ON SEQUENCE "worlds_id_seq" TO "game_app";')
    assert statements == [("BEGIN; " + " ".join(expected) + " COMMIT;", TARGET.database)]
    assert inspections == [granted, revision]


@pytest.mark.parametrize("revision", [policy.PREVIOUS, policy.CANDIDATE])
def test_hero_catalog_lock_requires_update_but_not_insert_or_delete(revision):
    assert policy.table_privileges(revision)["item_templates"] == {"SELECT", "UPDATE"}
    evidence = catalog(revision, revision)
    obj(evidence, "item_templates")["acl"].remove(["game_app", "UPDATE", False, "postgres"])
    with pytest.raises(policy.ObjectPolicyError):
        policy.inspect_objects(TARGET, CatalogSession(evidence), revision,
                               granted_revision=revision)
