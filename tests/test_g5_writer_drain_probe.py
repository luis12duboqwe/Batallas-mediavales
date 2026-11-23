"""BM-0093: read-only G5 writer drain probe regression contracts."""
import json
import subprocess
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops import g5_writer_drain_probe as probe


@pytest.fixture
def sample(tmp_path):
    edge = tmp_path / ".ops-state" / "edge-maintenance"
    edge.mkdir(parents=True)
    config = {"services": {
        name: {"restart": "no"} for name in probe.SERVICES
    }}
    config["services"]["nginx"]["volumes"] = [
        {"source": str(tmp_path / "nginx.g5.conf"),
         "target": "/etc/nginx/nginx.conf", "read_only": True},
        {"source": str(edge),
         "target": "/etc/nginx/edge-maintenance", "read_only": True},
    ]
    containers = [
        {"Service": "database", "State": "running"},
        {"Service": "nginx", "State": "running"},
        {"Service": "frontend", "State": "running"},
        {"Service": "caddy", "State": "running"},
        {"Service": "backend", "State": "exited"},
        {"Service": "worker", "State": "exited"},
        {"Service": "migrate", "State": "exited"},
        {"Service": "seed", "State": "exited"},
    ]
    return config, containers, edge


def check(sample, pg="0|0"):
    config, containers, edge = sample
    return probe.inspect(config, containers, pg, edge)


def test_only_quiescent_known_compose_passes_observation(sample):
    assert check(sample) == []


@pytest.mark.parametrize("format_text", [
    '[{"Service":"database","State":"running"}]',
    '{"Service":"database","State":"running"}',
    '{"Service":"database","State":"running"}\n{"Service":"nginx","State":"running"}',
])
def test_compose_inventory_decodes_supported_formats(format_text):
    assert probe.decode_ps(format_text)


@pytest.mark.parametrize("invalid", ["", "{", "123", "true", '"string"', '[null]'])
def test_invalid_compose_inventory_fails_closed(invalid):
    with pytest.raises(probe.ProbeError):
        probe.decode_ps(invalid)


@pytest.mark.parametrize("service", ["backend", "worker", "migrate", "seed"])
@pytest.mark.parametrize("state", ["running", "restarting", "paused", "created"])
def test_all_writer_classes_and_unsafe_states_block(sample, service, state):
    config, containers, edge = sample
    next(row for row in containers if row["Service"] == service)["State"] = state
    assert any(service in reason for reason in check(sample))


@pytest.mark.parametrize("service", ["backend", "worker", "migrate", "seed"])
def test_restart_can_reopen_writer_after_reboot(sample, service):
    config, _, _ = sample
    config["services"][service]["restart"] = "unless-stopped"
    assert any(service in reason and "restart" in reason for reason in check(sample))


def test_compose_unknown_service_is_blocker_even_if_exited(sample):
    config, containers, edge = sample
    containers.append({"Service": "unscheduled_writer", "State": "exited"})
    assert any("Unknown" in issue for issue in check(sample))
    config["services"]["new_writer"] = {"restart": "no"}
    assert any("topology" in issue for issue in check(sample))


def test_missing_expected_service_is_blocker(sample):
    sample[0]["services"].pop("seed")
    assert any("missing" in issue for issue in check(sample))


@pytest.mark.parametrize("invalid", [None, [], "bad", {"services": []}])
def test_malformed_compose_config_is_blocked(sample, invalid):
    _, containers, edge = sample
    assert probe.inspect(invalid, containers, "0|0", edge)


def test_missing_nginx_spec_is_blocked_without_exception(sample):
    sample[0]["services"]["nginx"] = None
    assert any("Nginx" in reason for reason in check(sample))


@pytest.mark.parametrize("pg", ["1|0", "0|1", "2|3"])
def test_postgres_sessions_and_prepared_transactions_block(sample, pg):
    assert any("PostgreSQL" in reason for reason in check(sample, pg))


@pytest.mark.parametrize("pg", ["", "0", "0|x", "-1|0", "0|0|0", "0\n0"])
def test_malformed_postgres_counts_block(sample, pg):
    assert any("two numeric counts" in reason for reason in check(sample, pg))


@pytest.mark.parametrize("service", ["database", "nginx"])
def test_essential_service_must_run_exactly_once(sample, service):
    config, containers, edge = sample
    for row in containers:
        if row["Service"] == service:
            row["State"] = "exited"
    assert any(service in reason for reason in check(sample))
    containers.append({"Service": service, "State": "running"})
    containers.append({"Service": service, "State": "running"})
    assert any(service in reason for reason in check(sample))


@pytest.mark.parametrize("target", ["/etc/nginx/nginx.conf", "/etc/nginx/edge-maintenance"])
def test_missing_or_writable_g5_mount_is_blocked(sample, target):
    config, _, _ = sample
    mount = next(m for m in config["services"]["nginx"]["volumes"]
                 if m["target"] == target)
    mount["read_only"] = False
    assert any("mount" in reason for reason in check(sample))
    mount["read_only"] = True
    config["services"]["nginx"]["volumes"].remove(mount)
    assert any("mount" in reason for reason in check(sample))


def test_mount_with_same_basename_in_another_directory_is_blocked(sample, tmp_path):
    config, _, edge = sample
    mount = next(m for m in config["services"]["nginx"]["volumes"]
                 if m["target"] == "/etc/nginx/nginx.conf")
    other = tmp_path / "other"
    other.mkdir()
    mount["source"] = str(other / "nginx.g5.conf")
    assert any("misplaced" in reason for reason in check(sample))


def test_open_gate_even_as_dangling_symlink_is_blocked(sample, tmp_path):
    _, _, edge = sample
    marker = edge / "open"
    marker.mkdir()
    assert any("admission" in reason for reason in check(sample))
    marker.rmdir()
    marker.symlink_to(tmp_path / "missing")
    assert any("admission" in reason for reason in check(sample))


def test_symlinked_gate_directory_is_blocked(sample, tmp_path):
    _, _, edge = sample
    original = edge.with_name("real-gate")
    edge.rename(original)
    edge.symlink_to(original)
    assert any("unsafe" in reason for reason in check(sample))


def test_read_only_collection_uses_passed_env_and_no_mutating_docker_commands(
    sample, tmp_path, monkeypatch
):
    config, containers, edge = sample
    env = tmp_path / ".release.env"
    env.write_text("POSTGRES_DB=medievol_db\nPOSTGRES_USER=medievol\n")
    compose = tmp_path / "docker-compose.deploy.yml"
    compose.write_text("services: {}\n")
    calls = []

    def fake_run(argv):
        calls.append(argv)
        if argv[-3:] == ["config", "--format", "json"]:
            return json.dumps(config)
        if argv[-4:] == ["ps", "--all", "--format", "json"]:
            return json.dumps(containers)
        assert "exec" in argv and "-Atqc" in argv
        return "0|0\n"

    edge_checks = []
    runtime_checks = []
    monkeypatch.setattr(probe, "_run", fake_run)
    monkeypatch.setattr(probe, "_require_closed_edge",
                        lambda argv, url: edge_checks.append((argv, url)))
    monkeypatch.setattr(probe, "verify_runtime_writer_restart_policies",
                        lambda rows: runtime_checks.append(rows))
    assert probe.collect(env, [compose], edge) == []
    assert len(runtime_checks) == 1
    assert len(edge_checks) == 2
    assert all(argv[:2] == ["docker", "compose"] for argv, _ in edge_checks)
    assert "/api/health" in edge_checks[0][1]
    assert "/socket.io/" in edge_checks[1][1]
    assert len(calls) == 3
    assert all(argv[:2] == ["docker", "compose"] for argv in calls)
    assert all(not any(part in {"stop", "up", "start", "restore", "rm"} for part in argv)
               for argv in calls)
    assert "medievol_db" in calls[-1][-1]


@pytest.mark.parametrize("status", [
    "  HTTP/1.1 503 Service Unavailable",
    "HTTP/1.0 503",
    " HTTP/2 503",
])
def test_actual_nginx_503_is_required_even_with_wget_nonzero(monkeypatch, status):
    monkeypatch.setattr(
        probe.subprocess, "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 8, "", status + chr(10))
    )
    probe._require_closed_edge(["docker", "compose"], "http://127.0.0.1/api/health")


@pytest.mark.parametrize("status", [
    "", "Connection refused", "HTTP/1.1 200 OK",
    "HTTP/1.1 500 Internal Error", "response body 503", "HTTP/1.1 5030",
])
def test_http_failures_and_false_statuses_never_count_as_closed(monkeypatch, status):
    monkeypatch.setattr(
        probe.subprocess, "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 1, "", status + chr(10))
    )
    with pytest.raises(probe.ProbeError, match="maintenance HTTP 503"):
        probe._require_closed_edge(["docker", "compose"], "http://127.0.0.1/api/health")


@pytest.mark.parametrize("dbname", ["x';DROP TABLE users;--", "", "a-b"])
def test_invalid_database_name_never_reaches_psql(sample, tmp_path, monkeypatch, dbname):
    _, _, edge = sample
    env = tmp_path / ".release.env"
    env.write_text(f"POSTGRES_DB={dbname}\nPOSTGRES_USER=medievol\n")
    compose = tmp_path / "docker-compose.deploy.yml"
    compose.write_text("services: {}\n")
    monkeypatch.setattr(probe, "_run",
                        lambda argv: pytest.fail("Must not reach Docker with untrusted dbname"))
    with pytest.raises(probe.ProbeError):
        probe.collect(env, [compose], edge)


@pytest.mark.parametrize("service", ["backend", "worker", "migrate", "seed"])
def test_runtime_restart_policy_is_checked_for_each_writer_even_if_exited(
    sample, monkeypatch, service
):
    _, containers, _ = sample
    expected = {}
    for index, row in enumerate(containers):
        if row["Service"] in probe.WRITERS:
            row["ID"] = format(index + 1, "012x")
            expected[row["ID"]] = row["Service"]
    calls = []

    def fake_run(argv):
        calls.append(argv)
        assert argv[:4] == ["docker", "inspect", "--type", "container"]
        assert argv[-2] == "{{.HostConfig.RestartPolicy.Name}}"
        assert argv[-1] in expected
        return "no\\n"

    monkeypatch.setattr(probe, "_run", fake_run)
    probe.verify_runtime_writer_restart_policies(containers)
    assert len(calls) == len(probe.WRITERS)
    assert {c[-1] for c in calls} == set(expected)


@pytest.mark.parametrize("unsafe_policy", ["always", "unless-stopped", "on-failure", "", "no\\nno"])
def test_desired_restart_no_cannot_mask_unsafe_runtime_restart(
    sample, monkeypatch, unsafe_policy
):
    _, containers, _ = sample
    worker = next(row for row in containers if row["Service"] == "worker")
    worker["ID"] = "a" * 12
    monkeypatch.setattr(probe, "_run", lambda argv: unsafe_policy)
    with pytest.raises(probe.ProbeError, match="runtime Docker restart policy"):
        probe.verify_runtime_writer_restart_policies([worker])


@pytest.mark.parametrize("identity", [None, "", "worker-01", "abc", "A" * 12, "a" * 11, "a" * 65, "a" * 12 + " --force"])
def test_missing_malformed_or_untrusted_docker_ids_are_refused(
    sample, monkeypatch, identity
):
    _, containers, _ = sample
    worker = next(row for row in containers if row["Service"] == "worker")
    worker["ID"] = identity
    monkeypatch.setattr(
        probe, "_run", lambda argv: pytest.fail("Unsafe ID must never reach Docker"),
    )
    with pytest.raises(probe.ProbeError, match="identity"):
        probe.verify_runtime_writer_restart_policies([worker])


def test_runtime_policy_probe_does_not_mutate_container_or_docker(
    sample, monkeypatch
):
    _, containers, _ = sample
    backend = next(row for row in containers if row["Service"] == "backend")
    backend["ID"] = "b" * 12
    args = []
    monkeypatch.setattr(probe, "_run", lambda command: args.append(command) or "no")
    probe.verify_runtime_writer_restart_policies([backend])
    assert len(args) == 1
    assert args[0][0:2] == ["docker", "inspect"]
    assert not {"update", "start", "restart", "stop", "rm"} & set(args[0])


def test_runtime_inspect_failure_is_a_hard_no_go(sample, monkeypatch):
    _, containers, _ = sample
    worker = next(row for row in containers if row["Service"] == "worker")
    worker["ID"] = "c" * 12
    monkeypatch.setattr(
        probe, "_run", lambda argv: (_ for _ in ()).throw(
            probe.ProbeError("Docker inspect returned nonzero")
        )
    )
    with pytest.raises(probe.ProbeError, match="inspect"):
        probe.verify_runtime_writer_restart_policies([worker])


def test_successful_cli_observation_never_claims_cutover_authorization(
    sample, monkeypatch, capsys
):
    monkeypatch.setattr(probe, "collect", lambda *args: [])
    monkeypatch.setattr(sys, "argv", ["probe", "--env-file", "sample", "-f", "compose"])
    assert probe.main() == 0
    output = capsys.readouterr().out
    assert "OBSERVATION" in output and "NOT backup/restore authorization" in output
