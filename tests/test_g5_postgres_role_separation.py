"""Adversarial G5 read-only PostgreSQL role-separation checks."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops import g5_writer_drain_probe as probe


@pytest.mark.parametrize("db_url,admin,expected", [
    ("postgresql+psycopg://game_app:secret@database:5432/game", "postgres_admin", "game_app"),
    ("postgresql://game_app:secret@database/game", "postgres_admin", "game_app"),
    ("postgresql+psycopg2://game_app:secret@database/game", "postgres_admin", "game_app"),
])
def test_distinct_postgres_app_role_parses_without_password(db_url, admin, expected):
    assert probe._application_role({"DB_URL": db_url, "POSTGRES_DB": "game"}, admin) == expected


@pytest.mark.parametrize("db_url", [
    "postgresql+psycopg://game_app:secret@elsewhere:5432/game",
    "postgresql+psycopg://game_app:secret@database:5433/game",
    "postgresql+psycopg://game_app:secret@database:noninteger/game",
    "postgresql+psycopg://game_app:secret@database:5432/otherdb",
    "postgresql+psycopg://game_app:secret@database:5432/game?host=elsewhere",
    "postgresql+psycopg://game_app:secret@database:5432/game?dbname=otherdb",
    "postgresql+psycopg://game_app:secret@database:5432/game#suffix",
    "postgresql+psycopg://game_app@database:5432/game",
])
def test_role_audit_rejects_database_endpoint_redirection(db_url):
    with pytest.raises(probe.ProbeError, match="endpoint|password"):
        probe._application_role(
            {"DB_URL": db_url, "POSTGRES_DB": "game"}, "postgres_admin"
        )


@pytest.mark.parametrize("db_url,admin", [
    ("postgresql+psycopg://postgres:secret@database/game", "postgres"),
    ("postgresql+psycopg://%70ostgres:secret@database/game", "postgres"),
    ("postgresql+psycopg://app%27--:secret@database/game", "postgres"),
    ("postgresql+psycopg://app-role:secret@database/game", "postgres"),
    ("postgresql+psycopg://:secret@database/game", "postgres"),
    ("postgresql+psycopg://database/game", "postgres"),
    ("sqlite:///game", "postgres"),
    ("", "postgres"),
    ("postgresql+psycopg://app:secret@database/game", "postgres-admin"),
    ("postgresql+psycopg://app:secret@database/game", ""),
    ("postgresql+psycopg://app:secret@database/game", "app"),
])
def test_shared_or_invalid_db_roles_fail_without_credential_leak(db_url, admin):
    with pytest.raises(probe.ProbeError) as failure:
        probe._application_role({"DB_URL": db_url}, admin)
    assert "secret" not in str(failure.value)


@pytest.mark.parametrize("role_status", ["0", "", "true", "1|0", "2", "ERROR", "1\n0"])
def test_elevated_or_untrustworthy_postgres_role_evidence_is_no_go(
    monkeypatch, role_status
):
    calls = []
    monkeypatch.setattr(probe, "_run", lambda argv: calls.append(argv) or role_status)
    with pytest.raises(probe.ProbeError, match="elevated|superuser"):
        probe._require_unprivileged_app_role(
            ["docker", "compose"], "postgres_admin", "game_writer"
        )
    assert len(calls) == 1
    sql = calls[0][-1]
    for column in ("rolsuper", "rolcreatedb", "rolcreaterole",
                   "rolreplication", "rolbypassrls", "rolcanlogin", "pg_has_role"):
        assert column in sql
    assert calls[0][-2] == "-Atqc"
    assert all(token not in calls[0] for token in ("UPDATE", "ALTER", "REVOKE", "GRANT"))


def test_nonprivileged_app_login_without_superuser_membership_passes(monkeypatch):
    calls = []
    monkeypatch.setattr(probe, "_run", lambda argv: calls.append(argv) or "1\n")
    probe._require_unprivileged_app_role(
        ["docker", "compose"], "postgres_admin", "game_writer"
    )
    assert len(calls) == 1
    assert "game_writer" in calls[0][-1]
    assert "secret" not in calls[0][-1]


def test_shared_postgres_admin_is_rejected_before_any_docker(
    tmp_path, monkeypatch
):
    env = tmp_path / "env"
    env.write_text(
        "POSTGRES_DB=medievol_db\nPOSTGRES_USER=postgres_admin\n"
        "DB_URL=postgresql+psycopg://postgres_admin:secret@database/medievol_db\n"
    )
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n")
    monkeypatch.setattr(probe, "_run", lambda _: pytest.fail("Docker must not run"))
    with pytest.raises(probe.ProbeError, match="identical"):
        probe.collect(env, [compose], tmp_path)


def test_elevated_postgres_app_role_blocks_before_edge_or_restart_checks(
    tmp_path, monkeypatch
):
    env = tmp_path / "env"
    env.write_text(
        "POSTGRES_DB=medievol_db\nPOSTGRES_USER=postgres_admin\n"
        "DB_URL=postgresql+psycopg://game_writer:secret@database/medievol_db\n"
    )
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n")
    calls = []

    def fake_run(argv):
        calls.append(argv)
        if argv[-3:] == ["config", "--format", "json"]:
            return json.dumps({"services": {}})
        if argv[-4:] == ["ps", "--all", "--format", "json"]:
            return json.dumps([])
        assert "FROM pg_roles" in argv[-1]
        return "0"

    monkeypatch.setattr(probe, "_run", fake_run)
    monkeypatch.setattr(
        probe, "_require_closed_edge",
        lambda *_: pytest.fail("Untrusted DB role must block edge observation"),
    )
    monkeypatch.setattr(
        probe, "verify_runtime_writer_restart_policies",
        lambda *_: pytest.fail("Untrusted DB role must block runtime claims"),
    )
    with pytest.raises(probe.ProbeError, match="elevated"):
        probe.collect(env, [compose], tmp_path)
    assert len(calls) == 3


def test_role_evidence_is_read_only_and_does_not_reveal_password(monkeypatch):
    calls = []
    monkeypatch.setattr(probe, "_run", lambda argv: calls.append(argv) or "1")
    probe._require_unprivileged_app_role(
        ["docker", "compose", "--env-file", "opaque.env"],
        "postgres_admin", "app_writer"
    )
    assert len(calls) == 1
    assert calls[0][-1].startswith("SELECT")
    assert not any(
        token in calls[0][-1].upper() for token in
        ("UPDATE ", "DELETE ", "INSERT ", "ALTER ", "GRANT ", "REVOKE ", "DROP ")
    )
    assert all("secret" not in item for item in calls[0])


@pytest.mark.parametrize("role", ["app';DROP TABLE users;--", "app-role", "", "a" * 64])
def test_sql_role_identifiers_must_be_safe_before_psql(monkeypatch, role):
    monkeypatch.setattr(
        probe, "_run", lambda _: pytest.fail("Unsafe role SQL reached Docker")
    )
    with pytest.raises(probe.ProbeError, match="identity"):
        probe._require_unprivileged_app_role(["docker"], "postgres_admin", role)
