"""BM-0093: rollback must not commit release metadata before recovery succeeds.

All commands run in a temporary fixture repository; Docker, restore, and smoke
are stubs. These tests never touch a staging or production deployment.
"""

import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_SHA = "a" * 40
PREVIOUS_SHA = "b" * 40


def _deployment_env(backup_directory: Path, contact: str) -> str:
    return f"""APP_ENV=staging
SECRET_KEY=ci-only-test-secret-that-is-over-thirty-two-characters
PUBLIC_HOST=staging.example.invalid
PUBLIC_BASE_URL=https://staging.example.invalid
FRONTEND_URL=https://staging.example.invalid
CORS_ORIGINS=https://staging.example.invalid
TLS_EMAIL=ops@example.invalid
HTTP_PORT=18080
HTTPS_PORT=18443
POSTGRES_USER=batalla
POSTGRES_PASSWORD=ci-password
POSTGRES_DB=batalla_ci
DB_URL=postgresql+psycopg://batalla:ci-password@database:5432/batalla_ci
SMTP_HOST=smtp.example.invalid
FROM_EMAIL=no-reply@example.invalid
SUPPORT_CONTACT={contact}
BACKEND_IMAGE=registry.example.invalid/game/backend:{PREVIOUS_SHA}
FRONTEND_IMAGE=registry.example.invalid/game/frontend:{PREVIOUS_SHA}
BACKUP_DIR={backup_directory}
BACKUP_RETENTION_DAYS=14
"""


@pytest.fixture
def rollback_lab(tmp_path):
    (tmp_path / "ops").mkdir()
    for filename in ("rollback_remote.sh", "deploy_remote.sh", "preflight.py"):
        shutil.copy2(PROJECT_ROOT / "ops" / filename, tmp_path / "ops" / filename)

    ops = tmp_path / "ops"
    (ops / "restore_postgres.sh").write_text(
        "#!/usr/bin/env bash\n"
        "printf 'restore:%s\\n' \"$1\" >> \"$BM_TRACE\"\n"
        "exit \"${BM_RESTORE_EXIT:-0}\"\n",
        encoding="utf-8",
    )
    (ops / "smoke_http.py").write_text(
        "import os, sys\n"
        "with open(os.environ['BM_TRACE'], 'a', encoding='utf-8') as f:\n"
        "    f.write('smoke\\n')\n"
        "sys.exit(int(os.environ.get('BM_SMOKE_EXIT', '0')))\n",
        encoding="utf-8",
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'docker:%s\\n' \"$*\" >> \"$BM_TRACE\"\n"
        "exit \"${BM_DOCKER_EXIT:-0}\"\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    (tmp_path / ".ops-state" / "deployments").mkdir(parents=True)
    (tmp_path / ".ops-state" / "releases").mkdir()
    backups = tmp_path / "backups"
    backups.mkdir()
    active = _deployment_env(backups, "active@example.invalid")
    previous = _deployment_env(backups, "previous@example.invalid")
    base_env = tmp_path / "base.env"
    base_env.write_text(active, encoding="utf-8")
    (tmp_path / ".release.env").write_text(active, encoding="utf-8")
    (tmp_path / ".release-sha").write_text(CURRENT_SHA + "\n", encoding="utf-8")
    (tmp_path / ".ops-state" / "releases" / (PREVIOUS_SHA + ".env")).write_text(
        previous, encoding="utf-8"
    )

    backup = backups / "sample.dump"
    backup.write_bytes(b"test-only-data")
    manifest = tmp_path / ".ops-state" / "deployments" / (CURRENT_SHA + ".json")
    manifest.write_text(
        json.dumps({"previous_release_sha": PREVIOUS_SHA, "rollback_backup": str(backup)}),
        encoding="utf-8",
    )
    trace = tmp_path / "trace.log"
    env = dict(os.environ)
    env.update({"PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""), "BM_TRACE": str(trace)})
    return {
        "root": tmp_path,
        "env": env,
        "trace": trace,
        "active": active,
        "previous": previous,
        "base_env": base_env,
        "manifest": manifest,
        "backup": backup,
    }


def _run(lab, *, current=CURRENT_SHA, extra_env=None):
    env = dict(lab["env"])
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", "ops/rollback_remote.sh", current, "ROLLBACK:" + current],
        cwd=lab["root"],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _run_deploy(lab):
    return subprocess.run(
        [
            "bash",
            "ops/deploy_remote.sh",
            str(lab["base_env"]),
            "c" * 40,
            "registry.example.invalid/game/backend",
            "registry.example.invalid/game/frontend",
        ],
        cwd=lab["root"],
        env=lab["env"],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _assert_active_unchanged(lab):
    assert (lab["root"] / ".release.env").read_text(encoding="utf-8") == lab["active"]
    assert (lab["root"] / ".release-sha").read_text(encoding="utf-8") == CURRENT_SHA + "\n"
    assert not list(lab["root"].glob(".release.env.rollback.*"))
    assert not list(lab["root"].glob(".release-sha.rollback.*"))


def _trace(lab):
    return lab["trace"].read_text(encoding="utf-8").splitlines() if lab["trace"].exists() else []


def test_reject_stale_current_release_without_mutating_anything(rollback_lab):
    result = _run(rollback_lab, current="c" * 40)
    assert result.returncode == 2
    assert "does not match active release" in result.stderr
    assert _trace(rollback_lab) == []
    _assert_active_unchanged(rollback_lab)


def test_reject_missing_snapshot_before_any_mutation(rollback_lab):
    rollback_lab["backup"].unlink()
    result = _run(rollback_lab)
    assert result.returncode == 2
    assert "snapshot missing" in result.stderr
    assert _trace(rollback_lab) == []
    _assert_active_unchanged(rollback_lab)


@pytest.mark.parametrize("failed_step", ["restore", "smoke"])
def test_failed_recovery_preserves_active_release_pointers(rollback_lab, failed_step):
    env = {"BM_RESTORE_EXIT": "35"} if failed_step == "restore" else {"BM_SMOKE_EXIT": "36"}
    result = _run(rollback_lab, extra_env=env)
    assert result.returncode == (35 if failed_step == "restore" else 36)
    trace = _trace(rollback_lab)
    assert trace[0].startswith("restore:./.release.env.rollback.")
    assert ("smoke" in trace) == (failed_step == "smoke")
    _assert_active_unchanged(rollback_lab)
    marker = rollback_lab["root"] / ".ops-state" / "recovery-required"
    assert marker.is_file()
    assert "reason=manual_rollback_in_progress" in marker.read_text(encoding="utf-8")

    before_retry = _trace(rollback_lab)
    deploy = _run_deploy(rollback_lab)
    assert deploy.returncode == 2
    assert "unresolved recovery incident" in deploy.stderr
    assert _trace(rollback_lab) == before_retry


def test_failed_application_only_rollback_keeps_metadata(rollback_lab):
    rollback_lab["manifest"].write_text(
        json.dumps({"previous_release_sha": PREVIOUS_SHA, "rollback_backup": None}),
        encoding="utf-8",
    )
    result = _run(rollback_lab, extra_env={"BM_DOCKER_EXIT": "41"})
    assert result.returncode == 41
    assert any(line.startswith("docker:compose --env-file ./.release.env.rollback.")
               for line in _trace(rollback_lab))
    assert "smoke" not in _trace(rollback_lab)
    _assert_active_unchanged(rollback_lab)
    assert (rollback_lab["root"] / ".ops-state" / "recovery-required").is_file()


def test_success_commits_both_release_pointers_after_smoke(rollback_lab):
    result = _run(rollback_lab)
    assert result.returncode == 0, result.stderr
    assert _trace(rollback_lab)[-1] == "smoke"
    assert (rollback_lab["root"] / ".release.env").read_text(encoding="utf-8") == rollback_lab["previous"]
    assert (rollback_lab["root"] / ".release-sha").read_text(encoding="utf-8") == PREVIOUS_SHA + "\n"
    assert not (rollback_lab["root"] / ".ops-state" / "recovery-required").exists()
    assert not list(rollback_lab["root"].glob(".release.env.rollback.*"))
    assert not list(rollback_lab["root"].glob(".release-sha.rollback.*"))


def test_successful_application_only_rollback_preserves_existing_recovery_marker(rollback_lab):
    rollback_lab["manifest"].write_text(
        json.dumps({"previous_release_sha": PREVIOUS_SHA, "rollback_backup": None}),
        encoding="utf-8",
    )
    marker = rollback_lab["root"] / ".ops-state" / "recovery-required"
    marker.write_text("reason=database_recovery_still_pending\n", encoding="utf-8")

    result = _run(rollback_lab)

    assert result.returncode == 0, result.stderr
    assert _trace(rollback_lab)[-1] == "smoke"
    assert (rollback_lab["root"] / ".release-sha").read_text(encoding="utf-8") == PREVIOUS_SHA + "\n"
    assert marker.read_text(encoding="utf-8") == "reason=database_recovery_still_pending\n"


def test_manual_rollback_refused_if_release_operation_lock_is_held(rollback_lab):
    lock_path = rollback_lab["root"] / ".ops-state" / "deploy.lock"
    with lock_path.open("a+", encoding="utf-8") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = _run(rollback_lab)
        assert result.returncode == 2
        assert "another deploy or rollback is already running" in result.stderr
        assert _trace(rollback_lab) == []
        _assert_active_unchanged(rollback_lab)

    # After release, manual rollback must be allowed through its own checks.
    retried = _run(rollback_lab)
    assert retried.returncode == 0, retried.stderr
    assert (rollback_lab["root"] / ".release-sha").read_text(encoding="utf-8") == PREVIOUS_SHA + "\n"
