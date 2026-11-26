import copy
import hashlib

import pytest

from ops.ci_g5_actual_reopen import (
    OriginalContainer,
    OriginalDatabase,
    require_committed_receipt_locked,
)
from ops.g5_cutover_state import CutoverStore, Identity, Phase, StateError


def docker_row():
    return {
        "Id": "a" * 64,
        "Image": "sha256:" + "b" * 64,
        "Config": {"Labels": {"com.docker.compose.project": "ci_project",
                              "com.docker.compose.service": "worker"},
                   "Env": ["FIXTURE=value"], "Cmd": ["python", "-m", "app.worker"]},
        "HostConfig": {"RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 4},
                       "NetworkMode": "ci_project", "Privileged": False},
        "State": {"Status": "running", "Running": True, "Paused": False, "Restarting": False},
    }


def test_fenced_container_must_preserve_exact_configuration_and_full_policy():
    row = docker_row()
    original = OriginalContainer.capture(row, "ci_project", "worker")
    assert (original.policy_name, original.policy_maximum_retry_count) == ("on-failure", 4)
    fenced = copy.deepcopy(row)
    fenced["HostConfig"]["RestartPolicy"] = {"Name": "no", "MaximumRetryCount": 0}
    fenced["State"] = {"Status": "exited", "Running": False, "Paused": False, "Restarting": False}
    original.assert_fenced_identity(fenced, "ci_project")

    for path, value in [
        (("Id",), "c" * 64),
        (("Image",), "sha256:" + "c" * 64),
        (("Config", "Cmd"), ["other"]),
        (("Config", "Labels", "com.docker.compose.project"), "other"),
        (("HostConfig", "NetworkMode"), "other"),
        (("HostConfig", "RestartPolicy", "MaximumRetryCount"), 4),
        (("HostConfig", "RestartPolicy", "Name"), "always"),
    ]:
        changed = copy.deepcopy(fenced)
        target = changed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(StateError):
            original.assert_fenced_identity(changed, "ci_project")


@pytest.mark.parametrize("status", ["created", "exited"])
def test_fenced_container_accepts_only_observed_stopped_states(status):
    row = docker_row()
    original = OriginalContainer.capture(row, "ci_project", "worker")
    row["HostConfig"]["RestartPolicy"] = {"Name": "no", "MaximumRetryCount": 0}
    row["State"] = {"Status": status, "Running": False, "Paused": False, "Restarting": False}
    original.assert_fenced_identity(row, "ci_project")


@pytest.mark.parametrize("state", [
    None, {},
    {"Status": "running", "Running": True, "Paused": False, "Restarting": False},
    {"Status": "paused", "Running": False, "Paused": True, "Restarting": False},
    {"Status": "restarting", "Running": False, "Paused": False, "Restarting": True},
    {"Status": "dead", "Running": False, "Paused": False, "Restarting": False},
    {"Status": "exited", "Running": True, "Paused": False, "Restarting": False},
    {"Status": "exited", "Running": False, "Paused": True, "Restarting": False},
    {"Status": "exited", "Running": False, "Paused": False, "Restarting": True},
    {"Status": "exited", "Running": False, "Paused": False},
    {"Status": "exited", "Running": 0, "Paused": False, "Restarting": False},
    {"Status": [], "Running": False, "Paused": False, "Restarting": False},
])
def test_fenced_container_rejects_live_or_ambiguous_states(state):
    row = docker_row()
    original = OriginalContainer.capture(row, "ci_project", "worker")
    row["HostConfig"]["RestartPolicy"] = {"Name": "no", "MaximumRetryCount": 0}
    row["State"] = state
    with pytest.raises(StateError, match="state"):
        original.assert_fenced_identity(row, "ci_project")


@pytest.mark.parametrize("policy", [
    {"Name": "on-failure"},
    {"Name": "always", "MaximumRetryCount": 5},
    {"Name": "on-failure", "MaximumRetryCount": True},
    {"Name": "on-failure", "MaximumRetryCount": -1},
    {"Name": "other", "MaximumRetryCount": 0},
])
def test_capture_rejects_ambiguous_restart_policies(policy):
    row = docker_row()
    row["HostConfig"]["RestartPolicy"] = policy
    with pytest.raises(StateError):
        OriginalContainer.capture(row, "ci_project", "worker")


def test_original_database_requires_pg15_exact_identities_and_login():
    fields = dict(database="game_ci", database_oid=100, app_role="game_app",
                  app_role_oid=101, maintenance_role="postgres", maintenance_role_oid=102,
                  connection_limit=12, login=True, server_version_num=150009)
    assert OriginalDatabase(**fields).connection_limit == 12
    for changes in ({"connection_limit": 0}, {"login": False},
                    {"server_version_num": 160000}, {"app_role_oid": 102},
                    {"database": "unsafe;DROP"}, {"connection_limit": True}):
        with pytest.raises(StateError):
            OriginalDatabase(**(fields | changes))


def test_only_exact_valid_committed_receipt_is_accepted_under_lock(tmp_path):
    host = tmp_path / "host"
    host.mkdir(mode=0o700)
    (host / ".ops-state").mkdir(mode=0o700)
    backups = tmp_path / "backups"
    backups.mkdir(mode=0o700)
    archive = backups / "snapshot"
    archive.write_bytes(b"fixture")
    archive.chmod(0o600)
    identity = Identity("ci-reopen", "a" * 40, "b" * 40,
                        hashlib.sha256(b"fixture").hexdigest(), str(archive),
                        "ci_project", "game_ci")
    store = CutoverStore(str(host))
    store.prepare(identity, str(backups))
    with store.hold_phase(identity, Phase.PREPARED):
        with pytest.raises(StateError, match="committed"):
            require_committed_receipt_locked(store, identity)
    store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
    store.advance(identity, Phase.MIGRATING, Phase.VERIFIED_READONLY)
    store.advance(identity, Phase.VERIFIED_READONLY, Phase.COMMITTED_WRITERS_ALLOWED)
    with store.hold_phase(identity, Phase.COMMITTED_WRITERS_ALLOWED):
        require_committed_receipt_locked(store, identity)
        other = Identity("ci-other", identity.previous_sha, identity.candidate_sha,
                         identity.backup_sha256, identity.backup_path,
                         identity.compose_project, identity.postgres_db)
        with pytest.raises(StateError, match="identity"):
            require_committed_receipt_locked(store, other)

    receipt = host / ".ops-state" / "g5-cutover.json"
    receipt.write_text(receipt.read_text().replace("COMMITTED_WRITERS_ALLOWED", "PREPARED"))
    with pytest.raises(StateError, match="invalid cutover manifest"):
        require_committed_receipt_locked(store, identity)
