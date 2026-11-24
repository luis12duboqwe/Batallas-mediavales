"""Regression tests for G5 runtime writer shutdown, no daemon access."""
from pathlib import Path
import sys
import json

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_docker_writer_fence import DockerFenceError, DockerWriterFence


class FakeDocker:
    def __init__(self):
        self.rows = {}
        self.mutations = []
        self.fail = None
        self.add_after_update = False
        for n, service in enumerate(("database", "nginx", "backend", "backend",
                                     "worker", "migrate", "seed"), 1):
            self.add(n, service)
        self.rows["7".zfill(64)].update(status="exited", running=False)

    def add(self, n, service, **overrides):
        identity = str(n).zfill(64)
        self.rows[identity] = dict(
            id=identity, project="game_ci", service=service, status="running",
            running=True, paused=False, restarting=False, policy="unless-stopped",
        )
        self.rows[identity].update(overrides)

    def run(self, args):
        if args[0] == "ps":
            return "\n".join(self.rows) + "\n"
        if args[0] == "inspect":
            return json.dumps(self.rows[args[-1]])
        self.mutations.append(tuple(args))
        if args[0] == self.fail:
            raise RuntimeError("synthetic Docker failure")
        if args[0] == "update":
            self.rows[args[-1]]["policy"] = "no"
            if self.add_after_update:
                self.add_after_update = False
                self.add(8, "worker")
        elif args[0] == "stop":
            self.rows[args[-1]].update(status="exited", running=False, restarting=False)
        else:
            raise AssertionError(args)
        return args[-1]


def test_all_replicas_and_one_shot_writers_disabled_before_stop():
    docker = FakeDocker()
    gate = DockerWriterFence("game_ci", docker.run)
    gate.engage()
    assert [cmd[0] for cmd in docker.mutations] == ["update"] * 5 + ["stop"] * 4
    assert {cmd[-1] for cmd in docker.mutations} == {str(n).zfill(64) for n in range(3, 8)}
    assert docker.rows["1".zfill(64)]["running"]
    assert docker.rows["2".zfill(64)]["running"]
    gate.assert_closed()
    with pytest.raises(DockerFenceError, match="already attempted"):
        gate.engage()


@pytest.mark.parametrize("change", ["unknown", "other-project", "missing-nginx",
                                     "paused", "invalid-id", "ambiguous"])
def test_untrustworthy_inventory_refused_before_mutation(change):
    docker = FakeDocker()
    if change == "unknown":
        docker.add(8, "unregistered_writer")
    elif change == "other-project":
        docker.rows["3".zfill(64)]["project"] = "foreign"
    elif change == "missing-nginx":
        del docker.rows["2".zfill(64)]
    elif change == "paused":
        docker.rows["3".zfill(64)].update(status="paused", paused=True)
    elif change == "invalid-id":
        docker.rows["bad-id"] = {}
    else:
        docker.rows["3".zfill(64)]["running"] = "true"
    with pytest.raises(DockerFenceError):
        DockerWriterFence("game_ci", docker.run).engage()
    assert not docker.mutations


@pytest.mark.parametrize("failure", ["update", "stop"])
def test_failed_commands_never_reenable_or_claim_closed(failure):
    docker = FakeDocker()
    docker.fail = failure
    gate = DockerWriterFence("game_ci", docker.run)
    with pytest.raises(DockerFenceError):
        gate.engage()
    with pytest.raises(DockerFenceError):
        gate.assert_closed()
    assert all(cmd[0] in {"update", "stop"} for cmd in docker.mutations)


def test_new_replica_between_update_and_stop_is_detected():
    docker = FakeDocker()
    docker.add_after_update = True
    with pytest.raises(DockerFenceError, match="inventory changed"):
        DockerWriterFence("game_ci", docker.run).engage()
    assert all(cmd[0] == "update" for cmd in docker.mutations)


@pytest.mark.parametrize("change", ["restarted", "policy", "new-replica", "deleted"])
def test_post_shutdown_drift_is_not_authorized(change):
    docker = FakeDocker()
    gate = DockerWriterFence("game_ci", docker.run)
    gate.engage()
    row = docker.rows["3".zfill(64)]
    if change == "restarted":
        row.update(status="running", running=True)
    elif change == "policy":
        row["policy"] = "always"
    elif change == "new-replica":
        docker.add(8, "worker")
    else:
        del docker.rows["3".zfill(64)]
    with pytest.raises(DockerFenceError):
        gate.assert_closed()


def test_empty_inventory_and_unsafe_project_fail_closed():
    docker = FakeDocker()
    docker.rows.clear()
    with pytest.raises(DockerFenceError):
        DockerWriterFence("game_ci", docker.run).engage()
    for name in ("", "../other", "-flag", "UPPER"):
        with pytest.raises(DockerFenceError):
            DockerWriterFence(name, docker.run)
