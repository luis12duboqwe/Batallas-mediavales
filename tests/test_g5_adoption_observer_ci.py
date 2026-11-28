import json
import os
from pathlib import Path

import pytest


def test_fixture_compose_does_not_persist_generated_credentials(tmp_path):
    from ops.ci_g5_adoption_observer import _compose_file

    project = "bm-g5-adoption-" + "a" * 32
    compose_path, env_file = _compose_file(tmp_path, project, "b" * 40)
    config = json.loads(compose_path.read_text(encoding="utf-8"))
    assert env_file.read_text(encoding="ascii") == ""
    assert env_file.stat().st_mode & 0o777 == 0o600
    assert config["services"]["database"]["environment"]["POSTGRES_PASSWORD"] == (
        "${POSTGRES_PASSWORD:?required}"
    )
    assert config["services"]["backend"]["environment"]["DATABASE_URL"] == (
        "${DB_URL:?required}"
    )


_LIVE_CI = (
    os.environ.get("GITHUB_ACTIONS") == "true"
    and os.environ.get("CI") == "true"
    and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    and os.environ.get("G5_OBSERVER_LIVE_TEST") == "1"
    and Path("/var/run/docker.sock").is_socket()
)


@pytest.mark.skipif(not _LIVE_CI, reason="requires GitHub-hosted CI local Docker")
def test_owned_live_compose_pg15_observation_and_runtime_mutation():
    from ops.ci_g5_adoption_observer import run

    run()


def test_rehearsal_rejects_self_hosted_before_docker(monkeypatch):
    from ops import ci_g5_adoption_observer as lab
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "self-hosted")
    monkeypatch.setattr(lab, "_docker", lambda *_a, **_k: pytest.fail("must not access Docker"))
    with pytest.raises(RuntimeError, match="GitHub CI"):
        lab.run()


def test_live_partial_observation_accepts_only_documented_limits():
    from types import SimpleNamespace
    from ops import ci_g5_adoption_observer as lab

    sha = "a" * 40
    blockers = tuple(sorted(lab._EXPECTED_PARTIAL_BLOCKERS))
    row = SimpleNamespace(checkout=SimpleNamespace(commit_sha=sha),
                          caddy_routes=("/",), blockers=blockers)
    observations = SimpleNamespace(before=row, after=row, blockers=blockers)
    lab._assert_partial_observations(observations, sha)
    # Identical degraded snapshots must not pass.
    for unexpected in (
        "runtime Compose service hash differs from effective configuration",
        "Caddy loaded runtime route could not be verified",
        "partial host inventory drifted during independent observation",
    ):
        bad = SimpleNamespace(checkout=row.checkout, caddy_routes=row.caddy_routes,
                              blockers=blockers + (unexpected,))
        with pytest.raises(RuntimeError, match="required partial evidence"):
            lab._assert_partial_observations(
                SimpleNamespace(before=bad, after=bad, blockers=bad.blockers), sha)
    no_route = SimpleNamespace(checkout=row.checkout, caddy_routes=(), blockers=blockers)
    with pytest.raises(RuntimeError, match="required partial evidence"):
        lab._assert_partial_observations(
            SimpleNamespace(before=no_route, after=no_route, blockers=blockers), sha)
    with pytest.raises(RuntimeError, match="required partial evidence"):
        lab._assert_partial_observations(
            SimpleNamespace(before=row, after=row, blockers=()), sha)


def test_fixture_checkout_does_not_inherit_prior_recovery_marker(tmp_path):
    import subprocess
    from ops import ci_g5_adoption_observer as lab
    from ops import g5_adoption_observer as observer

    source = tmp_path / "source"
    source.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
    git("init", "-q")
    (source / ".gitignore").write_text(".ops-state/\n")
    git("add", ".gitignore")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "fixture")
    sha = git("rev-parse", "HEAD")
    state = source / ".ops-state"
    state.mkdir(mode=0o700)
    marker = state / "recovery-required"
    marker.write_text("synthetic prior drill")
    assert observer._read_metadata(source).state is observer.MetadataState.INCIDENT
    target = tmp_path / "isolated-checkout"
    lab._clone_fixture_checkout(source, target, sha)
    assert observer._read_metadata(target).state is observer.MetadataState.ABSENT
    assert marker.read_text() == "synthetic prior drill"
    assert not (target / ".ops-state").exists()
