"""Adversarial guards for the isolated full-schema restore runner."""
from pathlib import Path
import os
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops import ci_g5_full_schema_restore as rehearsal


@pytest.fixture
def snapshot(tmp_path):
    return rehearsal.Snapshot.capture(tmp_path / "previous.dump", b"PGDMPfixture-data")


def test_archive_is_private_and_verified_from_existing_fd(snapshot):
    fd = snapshot.open_verified()
    try:
        snapshot.path.rename(snapshot.path.with_suffix(".moved"))
        snapshot.path.write_bytes(b"replacement-path")
        assert snapshot.read_verified(fd) == b"PGDMPfixture-data"
        assert os.fstat(fd).st_mode & 0o777 == 0o600
    finally:
        os.close(fd)


@pytest.mark.parametrize("attack", ["overwrite", "truncate", "replace", "permissions"])
def test_archive_alterations_are_refused(snapshot, attack):
    fd = snapshot.open_verified()
    try:
        if attack == "overwrite":
            with snapshot.path.open("r+b") as stream:
                stream.write(b"XXXXX")
        elif attack == "truncate":
            snapshot.path.write_bytes(b"PGDMP")
        elif attack == "replace":
            snapshot.path.unlink()
            snapshot.path.write_bytes(b"PGDMPfixture-data")
            os.close(fd)
            fd = os.open(snapshot.path, os.O_RDONLY)
        else:
            snapshot.path.chmod(0o644)
        with pytest.raises(rehearsal.RehearsalError, match="snapshot"):
            snapshot.read_verified(fd)
    finally:
        os.close(fd)


def test_archive_symlink_is_refused(snapshot, tmp_path):
    link = tmp_path / "link.dump"
    link.symlink_to(snapshot.path)
    altered = rehearsal.Snapshot(link, snapshot.sha256, snapshot.device,
                                 snapshot.inode, snapshot.size)
    with pytest.raises(OSError):
        altered.open_verified()


def test_capture_never_overwrites_and_requires_custom_format(snapshot, tmp_path):
    with pytest.raises(FileExistsError):
        rehearsal.Snapshot.capture(snapshot.path, b"PGDMPnew")
    with pytest.raises(rehearsal.RehearsalError, match="custom archive"):
        rehearsal.Snapshot.capture(tmp_path / "invalid.dump", b"plain SQL")


def test_catalog_normalizes_order_but_preserves_acl_owner_and_constraints():
    prefix = "-- PostgreSQL database dump\n\\restrict random-token\n"
    table = ("--\n-- Name: worlds; Type: TABLE; Schema: public; Owner: postgres\n--\n"
             "CREATE TABLE public.worlds (id integer NOT NULL);\n"
             "ALTER TABLE public.worlds OWNER TO postgres;\n")
    acl = ("--\n-- Name: TABLE worlds; Type: ACL; Schema: public; Owner: postgres\n--\n"
           "GRANT SELECT ON TABLE public.worlds TO game_app;\n")
    footer = "\n--\n-- PostgreSQL database dump complete\n--\n\\unrestrict random-token\n"
    first = (prefix + table + acl + footer).encode()
    reordered = (prefix.replace("random-token", "other") + acl + table).encode()
    assert rehearsal.canonical_schema(first) == rehearsal.canonical_schema(reordered)
    for old, new in [(b"NOT NULL", b""), (b"TO postgres", b"TO fixture_owner"),
                     (b"GRANT SELECT", b"GRANT UPDATE")]:
        assert rehearsal.canonical_schema(first) != rehearsal.canonical_schema(
            first.replace(old, new))


def test_catalog_preserves_multiline_literal_comments_and_blank_lines():
    header = "--\n-- Name: worlds; Type: COMMENT; Schema: public; Owner: postgres\n--\n"
    body = "COMMENT ON TABLE worlds IS 'first\n-- literal content\n\nlast';\n"
    before = (header + body).encode()
    assert rehearsal.canonical_schema(before) != rehearsal.canonical_schema(
        before.replace(b"literal content", b"changed content"))
    assert rehearsal.canonical_schema(before) != rehearsal.canonical_schema(
        before.replace(b"\n\n", b"\n"))


@pytest.mark.parametrize("delimiter", ["'", "$body$"])
def test_fake_toc_headers_inside_literals_cannot_mask_drift(delimiter):
    header = "--\n-- Name: actual; Type: COMMENT\n--\n"
    fake_a = "--\n-- Name: fake_a\n--\nA"
    fake_b = "--\n-- Name: fake_b\n--\nB"
    before = f"{header}SELECT {delimiter}\n{fake_a}\n{fake_b}\n{delimiter};".encode()
    after = f"{header}SELECT {delimiter}\n{fake_b}\n{fake_a}\n{delimiter};".encode()
    assert len(rehearsal.canonical_schema(before)) == 1
    assert rehearsal.canonical_schema(before) != rehearsal.canonical_schema(after)


@pytest.mark.parametrize("missing", ["CI", "GITHUB_ACTIONS"])
def test_cli_refuses_outside_ci_without_invoking_docker(monkeypatch, missing):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv(missing)
    monkeypatch.setattr(rehearsal, "docker", lambda *a, **k: pytest.fail("Docker invoked"))
    assert rehearsal.main([]) == 2


def test_docker_is_pinned_to_local_unix_socket(monkeypatch):
    calls = []
    monkeypatch.setenv("DOCKER_HOST", "ssh://external.invalid")
    monkeypatch.setattr(rehearsal, "command", lambda args, **kwargs: calls.append(args))
    rehearsal.docker(["version"])
    assert calls == [["docker", "--host", "unix:///var/run/docker.sock", "version"]]


@pytest.mark.parametrize("guard", ["barrier", "rejection", "executor", "checksum",
                                 "scope", "drift"])
def test_restore_preconditions_precede_every_destructive_command(monkeypatch, guard):
    fixture = rehearsal.Fixture("fixture-image")
    fixture.rejected = guard != "rejection"
    if guard == "executor":
        fixture.resources.append(("container", fixture.executor))

    def closed():
        if guard == "barrier":
            raise rehearsal.RehearsalError("barrier drift")

    def scope():
        if guard == "scope":
            raise rehearsal.RehearsalError("dependency outside fixture scope")

    class Receipt:
        def read_verified(self, fd):
            if guard == "checksum":
                raise rehearsal.RehearsalError("snapshot checksum changed")
            return b"PGDMPfixture"

    monkeypatch.setattr(fixture, "closed", closed)
    monkeypatch.setattr(fixture, "scope", scope)
    monkeypatch.setattr(fixture, "inventory", lambda: {"drift": guard == "drift"})
    monkeypatch.setattr(rehearsal, "docker",
                        lambda *a, **k: pytest.fail("destructive command reached"))
    with pytest.raises(rehearsal.RehearsalError):
        fixture.restore(Receipt(), 123, {"drift": False})


def test_cleanup_removes_anonymous_pg_volume_and_internal_network(monkeypatch):
    fixture = rehearsal.Fixture("fixture-image")
    fixture.resources = [("network", fixture.network), ("container", fixture.name),
                         ("container", fixture.executor)]
    calls = []

    def docker(args, **kwargs):
        calls.append(args)
        listing = "\n".join((fixture.executor, fixture.name, fixture.network)).encode()
        return type("Result", (), {"returncode": 0, "stdout": listing})()

    monkeypatch.setattr(rehearsal, "docker", docker)
    fixture.cleanup()
    removals = [args for args in calls if args[0] == "rm" or args[:2] == ["network", "rm"]]
    assert removals == [["rm", "--force", "--volumes", fixture.executor],
                     ["rm", "--force", "--volumes", fixture.name],
                     ["network", "rm", fixture.network]]
    assert fixture.resources == []


def test_cleanup_failure_is_not_reported_as_success(monkeypatch):
    fixture = rehearsal.Fixture("fixture-image")
    fixture.resources = [("container", fixture.name)]
    monkeypatch.setattr(rehearsal, "docker", lambda *a, **k:
                        type("Result", (), {"returncode": 1})())
    with pytest.raises(rehearsal.RehearsalError, match="cleanup failed"):
        fixture.cleanup()


def test_partial_container_start_is_owned_and_cleaned(monkeypatch):
    fixture = rehearsal.Fixture("fixture-image")
    removed = []

    def docker(args, **kwargs):
        if args[0] == "run":
            raise rehearsal.RehearsalError("startup failed after creation")
        if args[0] == "rm" or args[:2] == ["network", "rm"]:
            removed.append(args[-1])
        return type("Result", (), {
            "returncode": 0,
            "stdout": f"{fixture.name}\n{fixture.network}\n".encode(),
        })()

    monkeypatch.setattr(rehearsal, "docker", docker)
    with pytest.raises(rehearsal.RehearsalError, match="startup failed"):
        fixture.start()
    fixture.cleanup()
    assert removed == [fixture.name, fixture.network]


def test_cleanup_accepts_confirmed_absence_after_failed_creation(monkeypatch):
    fixture = rehearsal.Fixture("fixture-image")
    fixture.resources = [("container", fixture.name)]
    monkeypatch.setattr(rehearsal, "docker", lambda *a, **k:
                        type("Result", (), {"returncode": 0, "stdout": b""})())
    fixture.cleanup()
    assert fixture.resources == []


@pytest.mark.parametrize("fail", [False, True])
def test_restore_bootstraps_pg15_acl_and_fails_inside_one_transaction(monkeypatch, fail):
    fixture = rehearsal.Fixture("fixture-image")
    fixture.rejected = True
    candidate = {"catalog": "candidate"}
    calls = []
    transactions = []

    class Receipt:
        def read_verified(self, fd):
            calls.append("verified-fd")
            return b"PGDMPverified"

    class Process:
        returncode = None

        def __init__(self, args, stdin, **kwargs):
            transactions.append(stdin.read())

        def poll(self):
            return self.returncode

        def communicate(self, **kwargs):
            self.returncode = 3 if fail else 0
            return None, b"division by zero" if fail else b""

        def kill(self):
            pytest.fail("known completed restore was killed")

    def docker(args, **kwargs):
        assert calls == ["closed", "verified-fd", "scope", "closed"]
        assert args[-1] == "--file=-"
        assert kwargs["input"] == b"PGDMPverified"
        return type("Result", (), {"stdout": b"CREATE TABLE public.worlds(id integer);\n"})()

    monkeypatch.setattr(fixture, "closed", lambda: calls.append("closed"))
    monkeypatch.setattr(fixture, "scope", lambda: calls.append("scope"))
    monkeypatch.setattr(fixture, "inventory", lambda: candidate)
    monkeypatch.setattr(fixture.admin, "scalar",
                        lambda sql, database: "1" if "PgSleep" in sql else "0")
    monkeypatch.setattr(fixture, "app", lambda sql: type("Result", (), {
        "returncode": 2, "stderr": b"FATAL: role is not permitted to log in"})())
    monkeypatch.setattr(rehearsal, "docker", docker)
    monkeypatch.setattr(rehearsal.subprocess, "Popen", Process)
    fixture.restore(Receipt(), 123, candidate, fail=fail)
    sql = transactions[0]
    assert sql.startswith(b"BEGIN;\nDROP SCHEMA public CASCADE;\n")
    assert b"CREATE SCHEMA public AUTHORIZATION pg_database_owner;" in sql
    assert b"GRANT USAGE ON SCHEMA public TO PUBLIC;" in sql
    assert b"COMMENT ON SCHEMA public IS 'standard public schema';" in sql
    assert sql.index(b"DROP SCHEMA") < sql.index(b"CREATE TABLE")
    assert sql.endswith(b"COMMIT;\n")
    assert (b"SELECT 1/0;" in sql) is fail
    assert calls[-1] == "closed"


def test_snapshot_catalog_witness_uses_verified_bytes_and_distinct_database(monkeypatch):
    fixture = rehearsal.Fixture("fixture-image")
    calls = []

    class Receipt:
        def read_verified(self, fd):
            assert fd == 123
            return b"PGDMPverified-snapshot"

    def docker(args, **kwargs):
        calls.append(args)
        assert args[-1] == rehearsal.REFERENCE
        assert kwargs["input"] == b"PGDMPverified-snapshot"

    monkeypatch.setattr(fixture, "closed", lambda: calls.append("closed"))
    monkeypatch.setattr(fixture.admin, "sql",
                        lambda sql, database: calls.append((sql, database)))
    monkeypatch.setattr(rehearsal, "docker", docker)
    monkeypatch.setattr(fixture, "dump", lambda *options, database:
                        b"--\n-- Name: witness; Type: TABLE\n--\nCREATE TABLE worlds(id int);")
    assert fixture.snapshot_catalog(Receipt(), 123)
    assert calls[0] == calls[-1] == "closed"
    assert calls[1] == ("CREATE DATABASE g5_catalog_reference;", "postgres")
    assert rehearsal.REFERENCE != rehearsal.DB
