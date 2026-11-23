"""BM-0093: legacy operations must never bypass a durable G5 cutover slot.

All subprocesses run in disposable directories. No real Docker, PostgreSQL or VPS.
"""
from pathlib import Path
import os
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ("deploy_remote.sh", "rollback_remote.sh", "restore_postgres.sh")
MARKERS = ("g5-cutover.json", "g5-cutover-activated")


@pytest.fixture
def legacy_lab(tmp_path):
    (tmp_path / "ops").mkdir()
    for script in SCRIPTS:
        shutil.copy2(REPO_ROOT / "ops" / script, tmp_path / "ops" / script)
    state = tmp_path / ".ops-state"
    state.mkdir()
    (tmp_path / "base.env").write_text("APP_ENV=staging\n", encoding="utf-8")
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "docker").write_text(
        "#!/bin/sh\necho docker-invoked >> docker.trace\nexit 99\n",
        encoding="utf-8",
    )
    (tools / "docker").chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(tools) + os.pathsep + env.get("PATH", "")
    return {"root": tmp_path, "state": state, "tools": tools, "env": env}


def run_script(lab, script):
    sha = "b" * 40
    args = {
        "deploy_remote.sh": ["base.env", sha, "registry.invalid/backend", "registry.invalid/frontend"],
        "rollback_remote.sh": [sha, f"ROLLBACK:{sha}"],
        "restore_postgres.sh": ["base.env", "archive.dump", "RESTORE:batalla_ci"],
    }[script]
    return subprocess.run(
        ["bash", "ops/" + script, *args],
        cwd=lab["root"], env=lab["env"], capture_output=True,
        text=True, timeout=10, check=False,
    )


def assert_blocked_early(lab, result):
    assert result.returncode == 2, result.stderr
    assert "Legacy G5 operation refused" in result.stderr
    assert "certified coordinator required" in result.stderr or "unsafe .ops-state" in result.stderr
    assert not (lab["root"] / "docker.trace").exists()
    assert not (lab["root"] / ".release.env.next").exists()
    assert not (lab["root"] / ".ops-state" / "recovery-required").exists()


@pytest.mark.parametrize("script", SCRIPTS)
@pytest.mark.parametrize("marker", MARKERS)
@pytest.mark.parametrize("kind", ("file", "directory", "dangling-symlink"))
def test_legacy_entrypoints_reject_existing_g5_cutover_state(
    legacy_lab, script, marker, kind
):
    target = legacy_lab["state"] / marker
    if kind == "file":
        target.write_bytes(b"corrupt, untrusted and not an authorizing manifest")
    elif kind == "directory":
        target.mkdir()
    else:
        target.symlink_to(legacy_lab["root"] / "absent-cutover-target")
    assert_blocked_early(legacy_lab, run_script(legacy_lab, script))
    # A rejected attempt must preserve the marker, including symlink attacks.
    assert target.exists() or target.is_symlink()


@pytest.mark.parametrize("script", SCRIPTS)
def test_legacy_entrypoint_refuses_symlinked_state_directory(legacy_lab, script):
    state = legacy_lab["state"]
    actual = legacy_lab["root"] / "different-state-root"
    state.rename(actual)
    state.symlink_to(actual)
    assert_blocked_early(legacy_lab, run_script(legacy_lab, script))
    assert state.is_symlink()


@pytest.mark.parametrize("script", SCRIPTS)
def test_cutover_started_between_initial_check_and_lock_is_rejected(
    legacy_lab, script
):
    # The coordinator must use the shared release lock. This shim models
    # the marker becoming visible exactly as the legacy caller gets that lock.
    flock = legacy_lab["tools"] / "flock"
    flock.write_text(
        "#!/bin/sh\n"
        "printf cutover-injected > .ops-state/g5-cutover.json\n"
        "exit 0\n",
        encoding="utf-8",
    )
    flock.chmod(0o755)
    result = run_script(legacy_lab, script)
    assert_blocked_early(legacy_lab, result)
    assert (legacy_lab["state"] / "g5-cutover.json").read_text() == "cutover-injected"


@pytest.mark.parametrize("script", SCRIPTS)
def test_no_false_cutover_detection_when_slot_is_absent(legacy_lab, script):
    # This asserts backwards compatibility of the early check; it deliberately
    # does not authorize a real deploy/rollback/restore.
    result = run_script(legacy_lab, script)
    assert "Legacy G5 operation refused" not in result.stderr
    assert not (legacy_lab["root"] / "docker.trace").exists()
