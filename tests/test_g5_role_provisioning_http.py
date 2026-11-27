import json
import sys
import types

import pytest

from ops import ci_g5_role_provisioning as role


class Response:
    def __init__(self, status, data):
        self.status_code = status
        self.data = data

    def json(self):
        return self.data


class Client:
    failure = None
    requests = []

    def __init__(self, **kwargs):
        assert kwargs["base_url"] == "http://127.0.0.1:8000"
        assert kwargs["trust_env"] is False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))
        token = kwargs.get("headers", {}).get("Authorization", "")
        other = token.endswith("g5_role_other")
        if path == self.failure:
            return Response(200, [])
        if path == "/auth/token":
            return Response(200, {"access_token": kwargs["data"]["username"]})
        if path == "/worlds/7/join":
            return Response(200, {"starting_city_id": 11})
        if path == "/building/available":
            return Response(404, {}) if other else Response(200, [
                {"name": "warehouse", "can_upgrade": True}])
        if path == "/building/upgrade":
            return Response(404, {}) if other else Response(200, {"id": 12})
        if path == "/support/cases":
            return Response(200, {"id": 13})
        if path == "/auth/me/privacy-requests":
            return Response(200, [] if other else {"id": 14})
        if path.startswith("/support/cases/"):
            return (Response(404, {}) if other else
                    Response(200, {"id": int(path.rsplit("/", 1)[-1])}))
        if path == "/support/admin/cases":
            return (Response(200, [{"id": 13}, {"id": 14}])
                    if token.endswith("g5_role_admin") else Response(403, {}))
        raise AssertionError(path)


def execute_client(monkeypatch, failure=None):
    Client.failure = failure
    Client.requests = []
    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(Client=Client))
    monkeypatch.setattr(sys, "argv", ["-", "7"])
    exec(role._HTTP_CLIENT, {})


def test_http_client_covers_gameplay_support_privacy_and_authorization(monkeypatch, capsys):
    execute_client(monkeypatch)
    assert json.loads(capsys.readouterr().out) == {
        "city": 11, "queue": 12, "case": 13, "privacy": 14}
    assert len(Client.requests) == 17
    assert {params["headers"]["Authorization"].split()[-1]
            for _, path, params in Client.requests if path == "/support/admin/cases"} == {
                "g5_role_player", "g5_role_admin"}


@pytest.mark.parametrize("path", ["/building/available", "/support/cases/13",
                                  "/support/cases/14", "/support/admin/cases"])
def test_http_client_fails_closed_on_wrong_status(monkeypatch, path):
    with pytest.raises(RuntimeError):
        execute_client(monkeypatch, path)


def test_backend_is_stopped_and_removed_on_probe_failure(monkeypatch):
    from ops import ci_g5_edge_admission
    from ops import ci_g5_integrated_runtime, ci_g5_release_transition

    calls = []
    row = {"Image": "sha256:image",
           "HostConfig": {"PortBindings": {}, "PublishAllPorts": False},
           "Config": {"Labels": {"medievol.g5.edge-fixture": "fixture"}},
           "State": {"Running": False}}
    monkeypatch.setattr(ci_g5_release_transition, "_create_container", lambda *a, **k: "id")
    monkeypatch.setattr(ci_g5_release_transition, "_container", lambda _: row)
    monkeypatch.setattr(ci_g5_edge_admission, "run", lambda args: calls.append(args))
    monkeypatch.setattr(ci_g5_edge_admission, "probe", lambda args: (0, "", ""))
    monkeypatch.setattr(ci_g5_integrated_runtime, "wait_until", lambda f, _: f())
    monkeypatch.setattr(ci_g5_integrated_runtime, "binary",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("failure")))
    with pytest.raises(RuntimeError, match="failure"):
        role._http_probes("fixture", "sha256:image", "fixture-url", 7, object())
    assert calls == [["start", "id"], ["stop", "-t", "10", "id"], ["rm", "id"]]


def test_backend_rejects_published_ports_before_start(monkeypatch):
    from ops import ci_g5_edge_admission, ci_g5_release_transition

    calls = []
    row = {"Image": "sha256:image",
           "HostConfig": {"PortBindings": {"8000/tcp": [{}]}, "PublishAllPorts": False},
           "Config": {"Labels": {"medievol.g5.edge-fixture": "fixture"}},
           "State": {"Running": False}}
    monkeypatch.setattr(ci_g5_release_transition, "_create_container", lambda *a, **k: "id")
    monkeypatch.setattr(ci_g5_release_transition, "_container", lambda _: row)
    monkeypatch.setattr(ci_g5_edge_admission, "run", lambda args: calls.append(args))
    with pytest.raises(role.ObjectPolicyError, match="isolation"):
        role._http_probes("fixture", "sha256:image", "fixture-url", 7, object())
    assert calls == [["stop", "-t", "10", "id"], ["rm", "id"]]


def test_sql_denial_probes_use_fixed_statements_and_other_database(monkeypatch):
    from ops import ci_g5_actual_migration, ci_g5_edge_admission

    checks = []
    commands = []
    monkeypatch.setattr(ci_g5_actual_migration, "expect_refused",
                        lambda *args: checks.append(args))
    monkeypatch.setattr(ci_g5_edge_admission, "probe",
                        lambda command: (commands.append(command) or
                                         (2, "", 'permission denied for database "postgres"')))
    role._sql_denial_probes("fixture")
    assert checks == [
        ("fixture", "CREATE ROLE forbidden_ci NOLOGIN;", "permission denied to create role"),
        ("fixture", "ALTER SYSTEM SET log_statement = 'none';",
         'permission denied to set parameter "log_statement"'),
        ("fixture", "SELECT pg_catalog.pg_read_file('postgresql.conf');",
         "permission denied for function pg_read_file"),
        ("fixture", "SELECT rolpassword FROM pg_catalog.pg_authid;",
         "permission denied for table pg_authid"),
    ]
    assert len(commands) == 1
    assert commands[0][commands[0].index("-d") + 1] == "postgres"
    assert commands[0][-1] == "SELECT 1;"


@pytest.mark.parametrize("result", [(0, "", ""), (2, "", "connection refused")])
def test_cross_database_probe_requires_explicit_denial(monkeypatch, result):
    from ops import ci_g5_actual_migration, ci_g5_edge_admission

    monkeypatch.setattr(ci_g5_actual_migration, "expect_refused", lambda *args: None)
    monkeypatch.setattr(ci_g5_edge_admission, "probe", lambda command: result)
    with pytest.raises(role.ObjectPolicyError, match="cross-database denial"):
        role._sql_denial_probes("fixture")


def test_candidate_http_client_uses_distinct_fixture_accounts(monkeypatch, capsys):
    Client.failure = None
    Client.requests = []
    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(Client=Client))
    monkeypatch.setattr(sys, "argv", ["-", "7", "_candidate"])
    # The historical mock recognizes unsuffixed identities; normalize only
    # for authorization responses, while retaining the actual login inputs.
    original = Client.request
    names = []
    def request(self, method, path, **kwargs):
        if path == "/auth/token":
            names.append(kwargs["data"]["username"])
            kwargs = {**kwargs, "data": {**kwargs["data"],
                      "username": kwargs["data"]["username"].removesuffix("_candidate")}}
        return original(self, method, path, **kwargs)
    monkeypatch.setattr(Client, "request", request)
    exec(role._HTTP_CLIENT, {})
    assert names == ["g5_role_player_candidate", "g5_role_other_candidate",
                     "g5_role_admin_candidate"]
    assert json.loads(capsys.readouterr().out)["queue"] == 12
