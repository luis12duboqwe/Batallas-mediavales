"""BM-0093 automatic deploy recovery: no false success after failed rollback.

Only temporary fixture scripts are run. No real Docker, network, or database.
"""

import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

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
        "printf 'restore:%s:%s\\n' \"$1\" \"$2\" >> \"$BM_TRACE\"\n"
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
    (ops / "backup_postgres.sh").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'backup\n' >> "$BM_TRACE"
backup="$BM_TEST_BACKUP_DIR/batalla_ci-20261120T123456Z-A1b2C3d4.dump"
printf 'fixture database dump' > "$backup"
printf 'fixture checksum' > "$backup.sha256"
if [[ "$BM_RECEIPT_MODE" == "empty" ]]; then exit 0; fi
if [[ "$BM_RECEIPT_MODE" == "foreign" ]]; then
  printf 'unrelated existing archive' > "$BM_TEST_BACKUP_DIR/other.dump"
  printf 'unrelated checksum' > "$BM_TEST_BACKUP_DIR/other.dump.sha256"
  printf '%s\n' "$BM_TEST_BACKUP_DIR/other.dump" > "$BACKUP_RECEIPT_FILE"
else
  printf '%s\n' "$backup" > "$BACKUP_RECEIPT_FILE"
fi
""",
        encoding="utf-8",
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'docker:%s\\n' \"$*\" >> \"$BM_TRACE\"\n"
        "if [[ \"$*\" == *'ps -a -q'* ]]; then\n"
        "  if [[ \"${BM_COMPOSE_PS_EXIT:-0}\" != 0 ]]; then exit \"$BM_COMPOSE_PS_EXIT\"; fi\n"
        "  printf '%s' \"${BM_COMPOSE_PS_OUTPUT:-}\"; exit 0\n"
        "fi\n"
        "if [[ \"$*\" == *'up -d database'* ]]; then exit \"$BM_DATABASE_START_EXIT\"; fi\n"
        "if [[ \"$*\" == *'SELECT to_regclass'* ]]; then\n"
        "  if [[ \"$BM_SCHEMA_PROBE_EXIT\" != 0 ]]; then exit \"$BM_SCHEMA_PROBE_EXIT\"; fi\n"
        "  printf '%s\\n' \"$BM_SCHEMA_PROBE_VALUE\"; exit 0\n"
        "fi\n"
        "if [[ \"$*\" == *'up -d --remove-orphans'* ]]; then exit \"$BM_RELEASE_START_EXIT\"; fi\n"
        "if [[ \"$*\" == *'pull migrate seed backend worker frontend nginx caddy'* ]]; then\n"
        "  exit \"$BM_RELEASE_PULL_EXIT\"\n"
        "fi\n"
        "if [[ \"$*\" == *'pull backend worker frontend'* ]]; then\n"
        "  exit \"$BM_RECOVERY_PULL_EXIT\"\n"
        "fi\n"
        "exit 0\n", encoding="utf-8"
    )
    docker.chmod(0o755)

    # Fault injection for recovery preparation and metadata publication.
    (bin_dir / "mktemp").write_text(
        """#!/usr/bin/env bash
if [[ "$*" == *'.release.env.recovery.'* && -n "${BM_MKTEMP_EXIT:-}" ]]; then
  exit "$BM_MKTEMP_EXIT"
fi
exec /usr/bin/mktemp "$@"
""",
        encoding="utf-8",
    )
    (bin_dir / "mv").write_text(
        """#!/usr/bin/env bash
if [[ "$*" == *'.release.env.recovery.'* && -n "${BM_RECOVERY_MV_EXIT:-}" ]]; then
  exit "$BM_RECOVERY_MV_EXIT"
fi
exec /usr/bin/mv "$@"
""",
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
    env.update({
        "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
        "BM_TRACE": str(trace),
        "BM_TEST_BACKUP_DIR": str(backups),
        "BM_DATABASE_START_EXIT": "41",
        "BM_SCHEMA_PROBE_EXIT": "0",
        "BM_SCHEMA_PROBE_VALUE": "t",
        "BM_RELEASE_PULL_EXIT": "0",
        "BM_RELEASE_START_EXIT": "0",
        "BM_RECOVERY_PULL_EXIT": "0",
        "BM_RECEIPT_MODE": "valid",
    })
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


def test_database_start_failure_does_not_start_migration_dependencies(deploy_lab):
    result = _run(deploy_lab)
    assert result.returncode == 41, result.stderr
    assert not _marker(deploy_lab).exists()
    assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]
    assert (deploy_lab["root"] / ".release-sha").read_text(encoding="utf-8") == OLD_SHA + "\n"
    assert not any("up -d --remove-orphans" in line for line in _trace(deploy_lab))
    assert not any(line.startswith("restore:") for line in _trace(deploy_lab))
    assert not list(deploy_lab["root"].glob(".release.env.recovery.*"))


@pytest.mark.parametrize("extra_env", [
    {"BM_RESTORE_EXIT": "42"},
    {"BM_SMOKE_EXIT": "43"},
])
def test_failed_automatic_rollback_flags_incident_and_blocks_redeploy(deploy_lab, extra_env):
    first = _run(deploy_lab, {**extra_env, "BM_DATABASE_START_EXIT": "0", "BM_RELEASE_START_EXIT": "41"})
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
    result = _run(deploy_lab, {"BM_DATABASE_START_EXIT": "0", "BM_RELEASE_START_EXIT": "41"})
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
    result = _run(deploy_lab, extra_env={**failed_recovery_step, "BM_DATABASE_START_EXIT": "0", "BM_RELEASE_START_EXIT": "41"})
    assert result.returncode == 41, result.stderr
    assert _marker(deploy_lab).is_file()
    assert (deploy_lab["root"] / ".release-sha").read_text(encoding="utf-8") == OLD_SHA + "\n"
    assert "new@example.invalid" in (deploy_lab["root"] / ".release.env").read_text(
        encoding="utf-8"
    )
    again = _run(deploy_lab)
    assert again.returncode == 2
    assert "unresolved recovery incident" in again.stderr


def test_failed_schema_probe_never_assumes_first_install(deploy_lab):
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0", "BM_SCHEMA_PROBE_EXIT": "47"
    })
    assert result.returncode != 0
    assert "Database schema probe failed" in result.stderr
    assert "first deployment" not in result.stdout
    trace = _trace(deploy_lab)
    assert "backup" not in trace
    assert not any("pull migrate seed" in line for line in trace)
    assert not any("up -d --remove-orphans" in line for line in trace)
    assert _marker(deploy_lab).is_file()
    assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]


def test_unrecognized_schema_probe_value_is_refused(deploy_lab):
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0", "BM_SCHEMA_PROBE_VALUE": "unknown"
    })
    assert result.returncode != 0
    assert "Unexpected schema probe result" in result.stderr
    assert "backup" not in _trace(deploy_lab)
    assert not any("pull migrate seed" in line for line in _trace(deploy_lab))
    assert not any("up -d --remove-orphans" in line for line in _trace(deploy_lab))
    assert not any(line.startswith("restore:") for line in _trace(deploy_lab))
    assert _marker(deploy_lab).is_file()


def test_existing_release_with_missing_schema_is_refused(deploy_lab):
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0",
        "BM_SCHEMA_PROBE_VALUE": "f",
    })
    assert result.returncode != 0
    assert "Existing release has no users schema" in result.stderr
    assert "backup" not in _trace(deploy_lab)
    assert not any("pull migrate seed" in line for line in _trace(deploy_lab))
    assert not any("up -d --remove-orphans" in line for line in _trace(deploy_lab))
    assert not any(line.startswith("restore:") for line in _trace(deploy_lab))
    assert _marker(deploy_lab).is_file()


@pytest.mark.parametrize("existing", ["running", "stopped"])
def test_unmanaged_compose_containers_refused_before_services_change(deploy_lab, existing):
    # A historical preview has no release pointers but has Compose containers.
    root = deploy_lab["root"]
    (root / ".release.env").unlink()
    (root / ".release-sha").unlink()
    result = _run(deploy_lab, {"BM_COMPOSE_PS_OUTPUT": "existing-preview-container-id"})
    assert result.returncode == 2, result.stderr
    assert "unmanaged Docker Compose containers exist" in result.stderr
    assert not (root / ".release.env").exists()
    assert not (root / ".release.env.next").exists()
    assert not _marker(deploy_lab).exists()
    trace = _trace(deploy_lab)
    assert len(trace) == 1
    assert "ps -a -q" in trace[0]
    assert "up -d" not in trace[0]


def test_unmanaged_compose_probe_failure_is_fail_closed(deploy_lab):
    root = deploy_lab["root"]
    (root / ".release.env").unlink()
    (root / ".release-sha").unlink()
    result = _run(deploy_lab, {"BM_COMPOSE_PS_EXIT": "47"})
    assert result.returncode == 2, result.stderr
    assert "unable to inspect existing Docker Compose project" in result.stderr
    assert not (root / ".release.env").exists()
    assert not (root / ".release.env.next").exists()
    assert not _marker(deploy_lab).exists()
    assert len(_trace(deploy_lab)) == 1


@pytest.mark.parametrize("orphan_type", ["release_pointer", "previous_env", "manifest", "archive"])
def test_orphaned_metadata_without_active_env_is_refused(deploy_lab, orphan_type):
    root = deploy_lab["root"]
    (root / ".release.env").unlink()
    if orphan_type != "release_pointer":
        (root / ".release-sha").unlink()
    if orphan_type == "previous_env":
        (root / ".release.env.previous").write_text(deploy_lab["active"], encoding="utf-8")
    if orphan_type == "manifest":
        manifests = root / ".ops-state" / "deployments"
        manifests.mkdir(parents=True, exist_ok=True)
        (manifests / ("a" * 40 + ".json")).write_text(
            "{}", encoding="utf-8",
        )
    if orphan_type == "archive":
        releases = root / ".ops-state" / "releases"
        releases.mkdir(parents=True, exist_ok=True)
        (releases / ("a" * 40 + ".env")).write_text(
            deploy_lab["active"], encoding="utf-8",
        )
    result = _run(deploy_lab)
    assert result.returncode == 2, result.stderr
    assert any(fragment in result.stderr for fragment in (
        "metadata", "manifests exist", "archived releases exist"
    ))
    assert _trace(deploy_lab) == []
    assert not (root / ".release.env.next").exists()
    assert not _marker(deploy_lab).exists()


def test_populated_database_without_previous_release_never_runs_migrations(deploy_lab):
    root = deploy_lab["root"]
    (root / ".release.env").unlink()
    (root / ".release-sha").unlink()
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0",
        "BM_SCHEMA_PROBE_VALUE": "t",
    })
    assert result.returncode != 0
    assert "Existing users schema without managed release metadata" in result.stderr
    trace = _trace(deploy_lab)
    assert any("SELECT to_regclass" in line for line in trace)
    assert "backup" not in trace
    assert not any("pull migrate seed" in line for line in trace)
    assert not any("up -d --remove-orphans" in line for line in trace)
    assert _marker(deploy_lab).exists()  # Unmanaged DB demands manual recovery review.


def test_confirmed_empty_database_can_take_first_install_path(deploy_lab):
    (deploy_lab["root"] / ".release.env").unlink()
    (deploy_lab["root"] / ".release-sha").unlink()
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0",
        "BM_SCHEMA_PROBE_VALUE": "f",
        "BM_RELEASE_PULL_EXIT": "52",
    })
    assert result.returncode == 52
    assert "No existing application schema" in result.stdout
    assert "backup" not in _trace(deploy_lab)
    # A failed first deploy has no previous release to roll back to.
    assert _marker(deploy_lab).exists()


def test_deploy_restores_exact_new_backup_not_newest_directory_file(deploy_lab):
    backup_dir = deploy_lab["root"] / "backups"
    decoy = backup_dir / "batalla_ci-20991231T235959Z-Z9Z9Z9Z9.dump"
    decoy.write_bytes(b"unrelated backup with a newer filename")
    (backup_dir / (decoy.name + ".sha256")).write_text("decoy", encoding="utf-8")
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0",
        "BM_RELEASE_START_EXIT": "53",
    })
    assert result.returncode == 53, result.stderr
    restored = [line for line in _trace(deploy_lab) if line.startswith("restore:")]
    assert len(restored) == 1
    assert restored[0].endswith(
        "/batalla_ci-20261120T123456Z-A1b2C3d4.dump"
    )
    assert decoy.exists()
    assert not list((deploy_lab["root"] / ".ops-state").glob("backup-receipt.*"))
    assert not _marker(deploy_lab).exists()


@pytest.mark.parametrize("receipt_mode", ["empty", "foreign"])
def test_invalid_backup_receipt_blocks_release_pull(deploy_lab, receipt_mode):
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0",
        "BM_RECEIPT_MODE": receipt_mode,
    })
    assert result.returncode != 0
    trace = _trace(deploy_lab)
    assert "backup" in trace
    assert not any("pull migrate seed" in line for line in trace)
    assert not any(line.startswith("restore:") for line in trace)
    assert not list((deploy_lab["root"] / ".ops-state").glob("backup-receipt.*"))


def test_backup_receipt_accepts_trailing_directory_separator(deploy_lab):
    backup_dir = deploy_lab["root"] / "backups"
    for path in (deploy_lab["base"], deploy_lab["root"] / ".release.env"):
        original = path.read_text(encoding="utf-8")
        path.write_text(
            original.replace("BACKUP_DIR=" + str(backup_dir),
                             "BACKUP_DIR=" + str(backup_dir) + "/"),
            encoding="utf-8",
        )
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0",
        "BM_RELEASE_START_EXIT": "54",
        "BM_TEST_BACKUP_DIR": str(backup_dir) + "/",
    })
    assert result.returncode == 54, result.stderr
    assert any(
        line.startswith("restore:") and
        line.endswith("/batalla_ci-20261120T123456Z-A1b2C3d4.dump")
        for line in _trace(deploy_lab)
    )
    assert not _marker(deploy_lab).exists()


def test_pre_migration_image_pull_failure_does_not_restore_or_migrate(deploy_lab):
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0",
        "BM_RELEASE_PULL_EXIT": "55",
    })
    assert result.returncode == 55
    trace = _trace(deploy_lab)
    assert "backup" in trace
    assert not any("up -d --remove-orphans" in line for line in trace)
    assert not any(line.startswith("restore:") for line in trace)
    assert not any(line.startswith("smoke:") for line in trace)
    assert not _marker(deploy_lab).exists()
    assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]


def test_deployment_fails_before_mutation_if_operation_lock_is_held(deploy_lab):
    lock_path = deploy_lab["root"] / ".ops-state" / "deploy.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        refused = _run(deploy_lab)
        assert refused.returncode == 2
        assert "another deploy or rollback is already running" in refused.stderr
        assert _trace(deploy_lab) == []
        assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]
        assert not _marker(deploy_lab).exists()

    # Once the holder releases the lock, this path reaches the normal
    # database-start failure rather than being permanently locked.
    retried = _run(deploy_lab)
    assert retried.returncode == 41
    assert "already running" not in retried.stderr

def test_https_edge_timeout_activates_rollback_instead_of_simple_exit(deploy_lab):
    """Adversarial regression: explicit exit 1 must not bypass ERR rollback trap."""
    bin_dir = Path(deploy_lab["env"]["PATH"].split(os.pathsep)[0])
    python_shim = bin_dir / "python3"
    python_shim.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "-" && "$2" == "https://staging.example.invalid" ]]; then\n'
        "  cat >/dev/null\n"
        "  exit 1\n"
        "fi\n"
        f'exec {shlex.quote(sys.executable)} "$@"\n',
        encoding="utf-8",
    )
    python_shim.chmod(0o755)
    sleep_shim = bin_dir / "sleep"
    sleep_shim.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    sleep_shim.chmod(0o755)
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0",
        "BM_RELEASE_START_EXIT": "0",
    })
    trace = _trace(deploy_lab)
    assert result.returncode != 0
    assert any(s.startswith("restore:") for s in trace), (
        "HTTPS timeout exited without attempting automatic rollback; "
        "stderr=" + result.stderr + ", trace=" + repr(trace)
    )

def test_auto_rollback_forces_restore_mode_after_inherited_environment(deploy_lab):
    """The parent must override inherited preflight and no-start flags."""
    stub = deploy_lab["root"] / "ops" / "restore_postgres.sh"
    old = stub.read_text(encoding="utf-8")
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "${RESTORE_PREPARE_ONLY:-0}" != "0" || "${RESTORE_START_SERVICES:-1}" != "1" ]]; then exit 97; fi\n'
        + old.split("\n", 1)[1],
        encoding="utf-8",
    )
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0",
        "BM_RELEASE_START_EXIT": "41",
        "RESTORE_PREPARE_ONLY": "1",
        "RESTORE_START_SERVICES": "0",
    })
    assert result.returncode == 41, result.stderr
    assert not _marker(deploy_lab).exists(), result.stderr
    assert any(s.startswith("restore:") for s in _trace(deploy_lab))


def test_edge_timeout_with_failed_restore_retains_recovery_marker(deploy_lab):
    """The recovery marker must remain when HTTPS timeout rollback itself fails."""
    bin_dir = Path(deploy_lab["env"]["PATH"].split(os.pathsep)[0])
    python_shim = bin_dir / "python3"
    python_shim.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "-" && "$2" == "https://staging.example.invalid" ]]; then\n'
        "  cat >/dev/null\n"
        "  exit 1\n"
        "fi\n"
        f'exec {shlex.quote(sys.executable)} "$@"\n', encoding="utf-8",
    )
    python_shim.chmod(0o755)
    sleep_shim = bin_dir / "sleep"
    sleep_shim.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    sleep_shim.chmod(0o755)
    result = _run(deploy_lab, {
        "BM_DATABASE_START_EXIT": "0",
        "BM_RELEASE_START_EXIT": "0",
        "BM_RESTORE_EXIT": "42",
    })
    assert result.returncode != 0
    assert _marker(deploy_lab).is_file(), result.stderr
    assert any(s.startswith("restore:") for s in _trace(deploy_lab))


@pytest.mark.parametrize("dangling", [True, False])
def test_marker_symlink_always_blocks_deploy(deploy_lab, dangling):
    marker = _marker(deploy_lab)
    marker.parent.mkdir(parents=True, exist_ok=True)
    target = deploy_lab["root"] / "marker-target"
    if not dangling:
        target.write_text("original incident\n")
    marker.symlink_to(target)

    result = _run(deploy_lab)

    assert result.returncode == 2, result.stderr
    assert "unresolved recovery incident" in result.stderr
    assert marker.is_symlink()
    if dangling:
        assert not target.exists()
    else:
        assert target.read_text() == "original incident\n"
    assert _trace(deploy_lab) == []
