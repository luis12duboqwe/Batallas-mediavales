"""BM-0093: standalone restores must serialize with release operations."""

import fcntl
import hashlib
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
        "if [[ \"$*\" == *'pg_restore --list'* ]]; then printf '; dbname: batalla_ci\\n'; fi\n"
        "if [[ \"$*\" == *'stop backend worker'* ]]; then exit \"${BM_STOP_EXIT:-0}\"; fi\n"
        "if [[ \"$*\" == *'pg_restore --clean --if-exists --create'* ]]; then exit \"${BM_PG_RESTORE_EXIT:-0}\"; fi\n",
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


def _run(lab, *, extra_env=None, pass_fds=()):
    env = dict(lab["env"])
    env.update(extra_env or {})
    return subprocess.run(
        [
            "bash",
            "ops/restore_postgres.sh",
            str(lab["env_file"]),
            str(lab["backup"]),
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
