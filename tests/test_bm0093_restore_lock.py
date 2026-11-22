"""BM-0093: standalone restores must serialize with release operations."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def restore_lab(tmp_path):
    ops = tmp_path / "ops"
    ops.mkdir()
    for filename in ("restore_postgres.sh", "deploy_remote.sh", "preflight.py"):
        shutil.copy2(PROJECT_ROOT / "ops" / filename, ops / filename)

    state = tmp_path / ".ops-state"
    state.mkdir()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup = backup_dir / "synthetic.dump"
    backup.write_bytes(b"synthetic archive")
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    (backup_dir / "synthetic.dump.sha256").write_text(
        f"{digest}  {backup}\n", encoding="utf-8"
    )
    env_file = tmp_path / "restore.env"
    env_file.write_text(
        f"""APP_ENV=staging
SECRET_KEY=ci-only-secret-key-that-is-long-enough-1234567890
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
DB_URL=postgresql://database:5432/batalla_ci
SMTP_HOST=smtp.example.invalid
FROM_EMAIL=no-reply@example.invalid
SUPPORT_CONTACT=support@example.invalid
BACKEND_IMAGE=registry.example.invalid/game/backend:{"a" * 40}
FRONTEND_IMAGE=registry.example.invalid/game/frontend:{"a" * 40}
BACKUP_DIR={backup_dir}
BACKUP_RETENTION_DAYS=14
""",
        encoding="utf-8",
    )
    (tmp_path / "base.env").write_text(env_file.read_text(encoding="utf-8"), encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$BM_DOCKER_TRACE\"\n"
        "if [[ \"$*\" == *'pg_restore --list'* ]]; then\n"
        "  if [[ -n \"${BM_LIST_INPUT:-}\" ]]; then cat > \"$BM_LIST_INPUT\"; else cat >/dev/null; fi\n"
        "  if [[ -n \"${BM_REPLACE_BACKUP_WITH:-}\" ]]; then mv -- \"$BM_REPLACE_BACKUP_WITH\" \"$BM_BACKUP_PATH\"; fi\n"
        "  printf '; dbname: %s\\n' \"${BM_ARCHIVE_DB:-batalla_ci}\"; exit 0\n"
        "fi\n"
        "if [[ \"$*\" == *'stop backend worker'* ]]; then exit \"${BM_STOP_EXIT:-0}\"; fi\n"
        "if [[ \"$*\" == *'pg_restore --clean --if-exists --create'* ]]; then\n"
        "  if [[ -n \"${BM_CLEAN_INPUT:-}\" ]]; then cat > \"$BM_CLEAN_INPUT\"; else cat >/dev/null; fi\n"
        "  exit \"${BM_PG_RESTORE_EXIT:-0}\"\n"
        "fi\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    trace = tmp_path / "docker.trace"
    env = dict(os.environ)
    env.update({"PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
                "BM_DOCKER_TRACE": str(trace)})
    return {
        "root": tmp_path,
        "lock": state / "deploy.lock",
        "marker": state / "recovery-required",
        "base_env": tmp_path / "base.env",
        "env_file": env_file,
        "backup": backup,
        "trace": trace,
        "env": env,
    }


def _run(lab, *, backup=None, extra_env=None, pass_fds=()):
    env = dict(lab["env"])
    env.update(extra_env or {})
    return subprocess.run(
        [
            "bash",
            "ops/restore_postgres.sh",
            str(lab["env_file"]),
            str(backup or lab["backup"]),
            "RESTORE:batalla_ci",
        ],
        cwd=lab["root"],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
        pass_fds=pass_fds,
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


def _configure_rollback_lab(lab):
    shutil.copy2(PROJECT_ROOT / "ops" / "rollback_remote.sh", lab["root"] / "ops")
    (lab["root"] / "ops" / "smoke_http.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8"
    )
    state = lab["root"] / ".ops-state"
    releases = state / "releases"
    deployments = state / "deployments"
    releases.mkdir(exist_ok=True)
    deployments.mkdir(exist_ok=True)
    current_sha = "d" * 40
    previous_sha = "e" * 40
    active_env = lab["env_file"].read_text(encoding="utf-8")
    (lab["root"] / ".release.env").write_text(active_env, encoding="utf-8")
    (lab["root"] / ".release-sha").write_text(current_sha + "\n", encoding="utf-8")
    (releases / f"{previous_sha}.env").write_text(active_env, encoding="utf-8")
    (deployments / f"{current_sha}.json").write_text(
        json.dumps({
            "previous_release_sha": previous_sha,
            "rollback_backup": str(lab["backup"]),
        }),
        encoding="utf-8",
    )
    return current_sha, previous_sha


def test_standalone_restore_refuses_while_release_operation_lock_is_held(restore_lab):
    with restore_lab["lock"].open("a+", encoding="utf-8") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = _run(restore_lab)

    assert result.returncode == 2
    assert "another deploy, rollback or restore is already running" in result.stderr
    assert not restore_lab["trace"].exists()


def test_restore_inherits_lock_from_deploy_or_rollback(restore_lab):
    with restore_lab["lock"].open("a+", encoding="utf-8") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = _run(
            restore_lab,
            extra_env={
                "DEPLOY_LOCK_FD": str(holder.fileno()),
                "RESTORE_START_SERVICES": "0",
            },
            pass_fds=(holder.fileno(),),
        )

        assert result.returncode == 0, result.stderr
        trace = restore_lab["trace"].read_text(encoding="utf-8").splitlines()
        assert any(line.endswith("stop backend worker") for line in trace)
        assert any("pg_restore --clean --if-exists --create" in line for line in trace)
        refused = _run(restore_lab)
        assert refused.returncode == 2
        assert "another deploy, rollback or restore is already running" in refused.stderr

    retried = _run(restore_lab)
    assert retried.returncode == 0, retried.stderr


def test_restore_inherits_lock_through_bash_descriptor(restore_lab):
    command = (
        'exec {DEPLOY_LOCK_FD}>>.ops-state/deploy.lock; '
        'flock -n "$DEPLOY_LOCK_FD"; export DEPLOY_LOCK_FD; '
        'RESTORE_START_SERVICES=0 bash ops/restore_postgres.sh "$1" "$2" "$3"'
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            command,
            "restore-lock-test",
            str(restore_lab["env_file"]),
            str(restore_lab["backup"]),
            "RESTORE:batalla_ci",
        ],
        cwd=restore_lab["root"],
        env=restore_lab["env"],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    trace = restore_lab["trace"].read_text(encoding="utf-8").splitlines()
    assert any(line.endswith("stop backend worker") for line in trace)
    assert any("pg_restore --clean --if-exists --create" in line for line in trace)


def test_unlocked_inherited_descriptor_is_not_mistaken_for_nested_restore(restore_lab):
    with restore_lab["lock"].open("a+", encoding="utf-8") as holder:
        result = _run(
            restore_lab,
            extra_env={
                "DEPLOY_LOCK_FD": str(holder.fileno()),
                "BM_PG_RESTORE_EXIT": "33",
            },
            pass_fds=(holder.fileno(),),
        )

    assert result.returncode == 33
    assert restore_lab["marker"].is_file()
    assert "standalone_restore_requires_operator_certification" in (
        restore_lab["marker"].read_text(encoding="utf-8")
    )
    deploy = _run_deploy(restore_lab)
    assert deploy.returncode == 2
    assert "unresolved recovery incident" in deploy.stderr


def test_restore_uses_verified_snapshot_after_original_path_is_replaced(restore_lab):
    original = restore_lab["backup"].read_bytes()
    replacement = restore_lab["root"] / "replacement.dump"
    replacement.write_bytes(b"replacement archive with different bytes")
    list_input = restore_lab["root"] / "list.input"
    clean_input = restore_lab["root"] / "clean.input"
    env = {
        "BM_BACKUP_PATH": str(restore_lab["backup"]),
        "BM_REPLACE_BACKUP_WITH": str(replacement),
        "BM_LIST_INPUT": str(list_input),
        "BM_CLEAN_INPUT": str(clean_input),
    }

    result = _run(restore_lab, extra_env=env)

    assert result.returncode == 0, result.stderr
    assert list_input.read_bytes() == original
    assert clean_input.read_bytes() == original
    assert restore_lab["backup"].read_bytes() != original


def test_prepared_snapshot_can_be_restored_by_the_real_restore_script(restore_lab):
    prepared = _run(
        restore_lab,
        extra_env={"RESTORE_PREPARE_ONLY": "1", "RESTORE_START_SERVICES": "0"},
    )
    assert prepared.returncode == 0, prepared.stderr
    snapshot = restore_lab["root"] / prepared.stdout.strip()
    assert snapshot.is_file()
    assert Path(f"{snapshot}.sha256").is_file()
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() in Path(
        f"{snapshot}.sha256"
    ).read_text(encoding="utf-8")

    restored = _run(
        restore_lab,
        backup=snapshot,
        extra_env={"RESTORE_START_SERVICES": "0"},
    )
    assert restored.returncode == 0, restored.stderr
    assert any(
        "pg_restore --clean --if-exists --create" in line
        for line in restore_lab["trace"].read_text(encoding="utf-8").splitlines()
    )
    shutil.rmtree(snapshot.parent)
    assert not snapshot.parent.exists()


def test_manual_rollback_uses_prepared_snapshot_with_real_restore_script(restore_lab):
    current_sha, previous_sha = _configure_rollback_lab(restore_lab)
    list_input = restore_lab["root"] / "rollback-list.input"
    clean_input = restore_lab["root"] / "rollback-clean.input"
    env = dict(restore_lab["env"])
    env.update({
        "BM_LIST_INPUT": str(list_input),
        "BM_CLEAN_INPUT": str(clean_input),
    })

    result = subprocess.run(
        ["bash", "ops/rollback_remote.sh", current_sha, f"ROLLBACK:{current_sha}"],
        cwd=restore_lab["root"],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list_input.read_bytes() == restore_lab["backup"].read_bytes()
    assert clean_input.read_bytes() == restore_lab["backup"].read_bytes()
    assert (restore_lab["root"] / ".release-sha").read_text(encoding="utf-8") == previous_sha + "\n"
    assert not restore_lab["marker"].exists()
    assert not list((restore_lab["root"] / ".ops-state").glob("restore.*"))


def test_database_rollback_preserves_preexisting_recovery_marker(restore_lab):
    current_sha, previous_sha = _configure_rollback_lab(restore_lab)
    marker_contents = "reason=operator_recovery_still_pending\n"
    restore_lab["marker"].write_text(marker_contents, encoding="utf-8")
    env = dict(restore_lab["env"])
    env.update({
        "BM_LIST_INPUT": str(restore_lab["root"] / "rollback-list.input"),
        "BM_CLEAN_INPUT": str(restore_lab["root"] / "rollback-clean.input"),
    })

    result = subprocess.run(
        ["bash", "ops/rollback_remote.sh", current_sha, f"ROLLBACK:{current_sha}"],
        cwd=restore_lab["root"],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (restore_lab["root"] / ".release-sha").read_text(encoding="utf-8") == previous_sha + "\n"
    assert restore_lab["marker"].read_text(encoding="utf-8") == marker_contents


@pytest.mark.parametrize(
    ("invalid_archive", "expected_error"),
    [
        ("checksum", "checksum mismatch"),
        ("database", "does not match configured"),
    ],
)
def test_rollback_rejects_bad_snapshot_before_creating_recovery_marker(
    restore_lab, invalid_archive, expected_error
):
    current_sha, _previous_sha = _configure_rollback_lab(restore_lab)
    env = dict(restore_lab["env"])
    if invalid_archive == "checksum":
        (restore_lab["backup"].with_name(restore_lab["backup"].name + ".sha256")).write_text(
            f'{"0" * 64}  {restore_lab["backup"]}\n', encoding="utf-8"
        )
    else:
        env["BM_ARCHIVE_DB"] = "foreign_ci"

    result = subprocess.run(
        ["bash", "ops/rollback_remote.sh", current_sha, f"ROLLBACK:{current_sha}"],
        cwd=restore_lab["root"],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert not restore_lab["marker"].exists()
    trace = restore_lab["trace"].read_text(encoding="utf-8").splitlines() if restore_lab["trace"].exists() else []
    assert not any("stop backend worker" in line for line in trace)
    assert not any("pg_restore --clean --if-exists --create" in line for line in trace)
    assert (restore_lab["root"] / ".release-sha").read_text(encoding="utf-8") == current_sha + "\n"


@pytest.mark.parametrize(
    ("failure_env", "expected_docker_operation"),
    [
        ({"BM_STOP_EXIT": "31"}, "stop backend worker"),
        ({"BM_PG_RESTORE_EXIT": "32"}, "pg_restore --clean --if-exists --create"),
    ],
)
def test_failed_standalone_restore_marks_recovery_and_blocks_deploy(
    restore_lab, failure_env, expected_docker_operation
):
    result = _run(restore_lab, extra_env=failure_env)
    assert result.returncode in {31, 32}
    assert expected_docker_operation in "\n".join(
        restore_lab["trace"].read_text(encoding="utf-8").splitlines()
    )
    assert restore_lab["marker"].is_file()
    assert "standalone_restore_requires_operator_certification" in (
        restore_lab["marker"].read_text(encoding="utf-8")
    )

    trace_before_deploy = restore_lab["trace"].read_text(encoding="utf-8")
    deploy = _run_deploy(restore_lab)
    assert deploy.returncode == 2
    assert "unresolved recovery incident" in deploy.stderr
    assert restore_lab["trace"].read_text(encoding="utf-8") == trace_before_deploy


def test_successful_standalone_restore_keeps_marker_for_operator_certification(restore_lab):
    result = _run(restore_lab, extra_env={"RESTORE_START_SERVICES": "0"})
    assert result.returncode == 0, result.stderr
    assert restore_lab["marker"].is_file()
    assert "standalone_restore_requires_operator_certification" in (
        restore_lab["marker"].read_text(encoding="utf-8")
    )


def test_nested_restore_does_not_replace_parent_recovery_marker(restore_lab):
    restore_lab["marker"].write_text("reason=parent_recovery_protocol\n", encoding="utf-8")
    with restore_lab["lock"].open("a+", encoding="utf-8") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = _run(
            restore_lab,
            extra_env={
                "DEPLOY_LOCK_FD": str(holder.fileno()),
                "RESTORE_START_SERVICES": "0",
            },
            pass_fds=(holder.fileno(),),
        )

    assert result.returncode == 0, result.stderr
    assert restore_lab["marker"].read_text(encoding="utf-8") == "reason=parent_recovery_protocol\n"

def test_replay_inherited_prepare_env_cannot_report_rollback_success_without_restore(restore_lab):
    """Adversarial regression: a prepare-only env may leak into actual rollback."""
    current_sha, _ = _configure_rollback_lab(restore_lab)
    clean_input = restore_lab["root"] / "actual_restore_input"
    env = dict(restore_lab["env"])
    env.update({"RESTORE_PREPARE_ONLY": "1", "BM_CLEAN_INPUT": str(clean_input)})
    result = subprocess.run(
        ["bash", "ops/rollback_remote.sh", current_sha, f"ROLLBACK:{current_sha}"],
        cwd=restore_lab["root"], env=env, text=True,
        capture_output=True, timeout=20, check=False,
    )
    assert result.returncode != 0 or clean_input.exists(), (
        "Rollback returned success without calling pg_restore because "
        "RESTORE_PREPARE_ONLY leaked into the nested restoration. "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )

def test_replay_inherited_no_start_env_cannot_leave_services_stopped(restore_lab):
    """Adversarial regression: stale RESTORE_START_SERVICES=0 cannot suppress start in rollback."""
    current_sha, _ = _configure_rollback_lab(restore_lab)
    env = dict(restore_lab["env"])
    env.update({"RESTORE_START_SERVICES": "0"})
    result = subprocess.run(
        ["bash", "ops/rollback_remote.sh", current_sha, f"ROLLBACK:{current_sha}"],
        cwd=restore_lab["root"], env=env, text=True,
        capture_output=True, timeout=20, check=False,
    )
    trace = restore_lab["trace"].read_text(encoding="utf-8") if restore_lab["trace"].exists() else ""
    assert result.returncode != 0 or "up -d --remove-orphans" in trace, (
        "Rollback marked success without restarting services under inherited "
        "RESTORE_START_SERVICES=0; trace=" + trace
    )

def test_manifest_parse_failure_never_trusts_inherited_rollback_values(restore_lab):
    """Adversarial: malformed manifest must not be replaced by exported variables."""
    current_sha, previous_sha = _configure_rollback_lab(restore_lab)
    (restore_lab["root"] / ".ops-state" / "deployments" / (current_sha + ".json")).write_text("{", encoding="utf-8")
    env = dict(restore_lab["env"])
    env.update({"PREVIOUS_RELEASE_SHA": previous_sha, "ROLLBACK_BACKUP": str(restore_lab["backup"])})
    result = subprocess.run(
        ["bash", "ops/rollback_remote.sh", current_sha, f"ROLLBACK:{current_sha}"],
        cwd=restore_lab["root"], env=env, text=True, capture_output=True, timeout=20, check=False,
    )
    trace = restore_lab["trace"].read_text(encoding="utf-8") if restore_lab["trace"].exists() else ""
    assert result.returncode != 0 and "pg_restore --clean" not in trace, (
        "Malformed manifest unexpectedly fell back to inherited PREVIOUS_RELEASE_SHA and "
        "ROLLBACK_BACKUP. stdout=" + result.stdout + " stderr=" + result.stderr
    )
