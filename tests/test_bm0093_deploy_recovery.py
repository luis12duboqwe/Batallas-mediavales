"""BM-0093 automatic deploy recovery: no false success after failed rollback.

Only temporary fixture scripts are run. No real Docker, network, or database.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


PROJECT = Path(__file__).resolve().parents[1]
OLD_SHA = "a" * 40
NEW_SHA = "b" * 40


def _env(backup_dir, email):
    return f"""APP_ENV=staging
SECRET_KEY=testing-only-secret-for-deploy-recovery-scenarios
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
SUPPORT_CONTACT={email}
BACKEND_IMAGE=registry.example.invalid/game/backend:{OLD_SHA}
FRONTEND_IMAGE=registry.example.invalid/game/frontend:{OLD_SHA}
BACKUP_DIR={backup_dir}
BACKUP_RETENTION_DAYS=14
"""


@pytest.fixture
def deploy_lab(tmp_path):
    ops = tmp_path / "ops"
    ops.mkdir()
    for file in ("deploy_remote.sh", "preflight.py"):
        shutil.copy2(PROJECT / "ops" / file, ops / file)
    (ops / "restore_postgres.sh").write_text(
        "#!/usr/bin/env bash\n"
        "printf 'restore:%s\\n' \"$1\" >> \"$BM_TRACE\"\n"
        "exit \"${BM_RESTORE_EXIT:-0}\"\n", encoding="utf-8"
    )
    (ops / "smoke_http.py").write_text(
        "import os, sys\n"
        "with open(os.environ['BM_TRACE'], 'a', encoding='utf-8') as f:\n"
        "    f.write('smoke:' + sys.argv[sys.argv.index('--base-url') + 1] + '\\n')\n"
        "sys.exit(int(os.environ.get('BM_SMOKE_EXIT', '0')))\n",
        encoding="utf-8"
    )
    (ops / "load_smoke.py").write_text("raise SystemExit(0)\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'docker:%s\\n' \"$*\" >> \"$BM_TRACE\"\n"
        "if [[ \"$*\" == *'up -d database'* ]]; then exit 41; fi\n"
        "if [[ \"$*\" == *'pull backend worker frontend'* ]]; then\n"
        "  exit \"${BM_RECOVERY_PULL_EXIT:-0}\"\n"
        "fi\n"
        "exit 0\n", encoding="utf-8"
    )
    docker.chmod(0o755)

    # Fault injection for recovery preparation and the metadata rename.
    (bin_dir / "mktemp").write_text(
        "#!/usr/bin/env bash\\n"
        "if [[ \\\"$*\\\" == *'.release.env.recovery.'* && -n \\\"${BM_MKTEMP_EXIT:-}\\\" ]]; then\\n"
        "  exit \\\"$BM_MKTEMP_EXIT\\\"\\n"
        "fi\\n"
        "exec /usr/bin/mktemp \\\"$@\\\"\\n",
        encoding="utf-8",
    )
    (bin_dir / "mv").write_text(
        "#!/usr/bin/env bash\\n"
        "if [[ \\\"$*\\\" == *'.release.env.recovery.'* && -n \\\"${BM_RECOVERY_MV_EXIT:-}\\\" ]]; then\\n"
        "  exit \\\"$BM_RECOVERY_MV_EXIT\\\"\\n"
        "fi\\n"
        "exec /usr/bin/mv \\\"$@\\\"\\n",
        encoding="utf-8",
    )
    (bin_dir / "mktemp").chmod(0o755)
    (bin_dir / "mv").chmod(0o755)

    backups = tmp_path / "backups"
    backups.mkdir()
    active = _env(backups, "active@example.invalid")
    base = _env(backups, "new@example.invalid")
    (tmp_path / ".release.env").write_text(active, encoding="utf-8")
    (tmp_path / ".release-sha").write_text(OLD_SHA + "\n", encoding="utf-8")
    base_env = tmp_path / "base.env"
    base_env.write_text(base, encoding="utf-8")
    trace = tmp_path / "trace"
    env = dict(os.environ)
    env.update({"PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""), "BM_TRACE": str(trace)})
    return {"root": tmp_path, "base": base_env, "active": active, "env": env, "trace": trace}


def _run(lab, extra_env=None):
    env = dict(lab["env"])
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", "ops/deploy_remote.sh", str(lab["base"]), NEW_SHA,
         "registry.example.invalid/game/backend", "registry.example.invalid/game/frontend"],
        cwd=lab["root"], capture_output=True, text=True, env=env, timeout=20, check=False,
    )


def _trace(lab):
    return lab["trace"].read_text(encoding="utf-8").splitlines() if lab["trace"].exists() else []


def _marker(lab):
    return lab["root"] / ".ops-state" / "recovery-required"


def test_failed_deploy_with_verified_rollback_restores_previous_metadata(deploy_lab):
    result = _run(deploy_lab)
    assert result.returncode == 41, result.stderr
    assert not _marker(deploy_lab).exists()
    assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]
    assert (deploy_lab["root"] / ".release-sha").read_text(encoding="utf-8") == OLD_SHA + "\n"
    assert _trace(deploy_lab)[-1] == "smoke:https://staging.example.invalid"
    assert not list(deploy_lab["root"].glob(".release.env.recovery.*"))


@pytest.mark.parametrize("extra_env", [
    {"BM_RECOVERY_PULL_EXIT": "42"},
    {"BM_SMOKE_EXIT": "43"},
])
def test_failed_automatic_rollback_flags_incident_and_blocks_redeploy(deploy_lab, extra_env):
    first = _run(deploy_lab, extra_env)
    assert first.returncode == 41, first.stderr
    assert "manual recovery required" in first.stderr
    assert _marker(deploy_lab).is_file()
    assert "failed_release=" + NEW_SHA in _marker(deploy_lab).read_text(encoding="utf-8")
    assert (deploy_lab["root"] / ".release-sha").read_text(encoding="utf-8") == OLD_SHA + "\n"
    assert "new@example.invalid" in (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8")
    assert not list(deploy_lab["root"].glob(".release.env.recovery.*"))

    before = _trace(deploy_lab)
    second = _run(deploy_lab)
    assert second.returncode == 2
    assert "unresolved recovery incident" in second.stderr
    assert _trace(deploy_lab) == before


def test_missing_previous_release_sha_is_refused_before_docker(deploy_lab):
    (deploy_lab["root"] / ".release-sha").unlink()
    result = _run(deploy_lab)
    assert result.returncode == 2
    assert "no trustworthy .release-sha" in result.stderr
    assert _trace(deploy_lab) == []
    assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]


def test_existing_recovery_incident_refuses_deployment_early(deploy_lab):
    _marker(deploy_lab).parent.mkdir(parents=True, exist_ok=True)
    _marker(deploy_lab).write_text("unresolved\n", encoding="utf-8")
    result = _run(deploy_lab)
    assert result.returncode == 2
    assert "unresolved recovery incident" in result.stderr
    assert _trace(deploy_lab) == []
    assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]


def test_recovery_smoke_targets_previous_origin_not_new_origin(deploy_lab):
    # Changing the public URL must not make rollback verify the new release.
    old_base = "https://staging.example.invalid"
    new_base = "https://new.example.invalid"
    base = deploy_lab["base"]
    base.write_text(
        base.read_text(encoding="utf-8").replace(
            "staging.example.invalid", "new.example.invalid"
        ),
        encoding="utf-8",
    )
    result = _run(deploy_lab)
    assert result.returncode == 41, result.stderr
    assert _trace(deploy_lab)[-1] == "smoke:" + old_base
    assert not _marker(deploy_lab).exists()


def test_database_identity_change_requires_separate_migration(deploy_lab):
    base = deploy_lab["base"]
    base.write_text(
        base.read_text(encoding="utf-8").replace(
            "POSTGRES_DB=batalla_ci", "POSTGRES_DB=unrehearsed_db"
        ),
        encoding="utf-8",
    )
    result = _run(deploy_lab)
    assert result.returncode == 2
    assert "PostgreSQL connection changed" in result.stderr
    assert _trace(deploy_lab) == []
    assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]


@pytest.mark.parametrize("failed_recovery_step", [
    {"BM_MKTEMP_EXIT": "28"},
    {"BM_RECOVERY_MV_EXIT": "29"},
])
def test_recovery_internal_failure_preserves_incident_marker_and_original_error(
    deploy_lab, failed_recovery_step
):
    result = _run(deploy_lab, extra_env=failed_recovery_step)
    assert result.returncode == 41, result.stderr
    assert _marker(deploy_lab).is_file()
    assert (deploy_lab["root"] / ".release-sha").read_text(encoding="utf-8") == OLD_SHA + "\n"
    assert "new@example.invalid" in (deploy_lab["root"] / ".release.env").read_text(
        encoding="utf-8"
    )
    again = _run(deploy_lab)
    assert again.returncode == 2
    assert "unresolved recovery incident" in again.stderr
