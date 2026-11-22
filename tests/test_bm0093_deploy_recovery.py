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
BACKUP_NAME = "batalla_ci-20261120T123456Z-A1b2C3d4.dump"


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
        r"""#!/usr/bin/env bash
set -euo pipefail
[[ "/proc/$$/fd/$DEPLOY_LOCK_FD" -ef .ops-state/deploy.lock ]]
flock -n "$DEPLOY_LOCK_FD"
archive="$4/archive.dump"
receipt() {
  local digest
  digest="$(sha256sum < "$archive")"
  printf '%s:%s\n' "${digest%% *}" "$(stat -c '%d:%i' -- "$archive")"
}
if [[ "$3" == "PREPARE:batalla_ci" ]]; then
  [[ "$RESTORE_PREPARE_ONLY:$RESTORE_START_SERVICES:$#" == 1:0:4 ]]
  [[ "$1" == .release.env.previous ]]
  cmp -s "$1" .release.env
  printf 'prepare:%s\n' "$2" >> "$BM_TRACE"
  cp -- "$2" "$archive"
  chmod 400 "$archive"
  if [[ "${BM_INVALID_PREPARED_RECEIPT:-0}" == 1 ]]; then
    printf 'invalid receipt\n'
  else
    receipt
  fi
else
  [[ "$3" == "RESTORE:batalla_ci" && "$RESTORE_PREPARE_ONLY:$RESTORE_START_SERVICES:$#" == 0:1:5 ]]
  [[ "$2" == "$archive" && "$5" == "$(receipt)" ]]
  grep -qx 'SUPPORT_CONTACT=active@example.invalid' "$1"
  printf 'restore:%s:%s\n' "$1" "$2" >> "$BM_TRACE"
  exit "${BM_RESTORE_EXIT:-0}"
fi
""", encoding="utf-8"
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
sha256sum "$backup" > "$backup.sha256"
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
        "if [[ \"$*\" == *'pg_restore --list'* ]]; then\n"
        "  [[ \"$(cat)\" == 'fixture database dump' ]] || exit 90\n"
        "  printf ';     dbname: %s\\n' \"${BM_ARCHIVE_DB:-batalla_ci}\"; exit 0\n"
        "fi\n"
        "if [[ \"$*\" == *'pg_restore --clean'* ]]; then\n"
        "  [[ \"$(cat)\" == 'fixture database dump' ]] || exit 91\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$*\" == *'up -d --remove-orphans backend worker frontend nginx caddy'* ]]; then exit 0; fi\n"
        "if [[ \"$*\" == *'up -d --remove-orphans'* ]]; then\n"
        "  if [[ \"${BM_REMOVE_SOURCE_ON_START:-0}\" == 1 ]]; then\n"
        "    rm -- \"$BM_TEST_BACKUP_DIR\"/*.dump \"$BM_TEST_BACKUP_DIR\"/*.sha256\n"
        "  fi\n"
        "  exit \"$BM_RELEASE_START_EXIT\"\n"
        "fi\n"
        "if [[ \"$*\" == *'pull migrate seed backend worker frontend nginx caddy'* ]]; then\n"
        "  exit \"$BM_RELEASE_PULL_EXIT\"\n"
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
        "BM_DATABASE_START_EXIT": "0",
        "BM_SCHEMA_PROBE_EXIT": "0",
        "BM_SCHEMA_PROBE_VALUE": "t",
        "BM_RELEASE_PULL_EXIT": "0",
        "BM_RELEASE_START_EXIT": "0",
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


def _assert_temporary_files_cleaned(lab):
    root = lab["root"]
    for pattern in (
        ".ops-state/restore.*", ".ops-state/backup-receipt.*",
        ".ops-state/recovery-required.*", ".release.env.next", ".release.env.recovery.*",
    ):
        assert not list(root.glob(pattern)), pattern


def _use_real_restore(lab):
    shutil.copy2(PROJECT / "ops" / "restore_postgres.sh", lab["root"] / "ops")
    cat = lab["root"] / "bin" / "cat"
    cat.write_text(
        r"""#!/usr/bin/env bash
if [[ "${1:-}" == -- && "${2:-}" == *.dump ]]; then
  printf 'copy:%s\n' "$2" >> "$BM_TRACE"
  case "${BM_COPY_FAILURE:-}" in
    enospc)
      printf 'partial copy'
      printf 'cat: write error: No space left on device\n' >&2
      exit 1
      ;;
    checksum)
      printf 'corrupt copy'
      exit 0
      ;;
  esac
fi
exec /usr/bin/cat "$@"
""", encoding="utf-8",
    )
    cat.chmod(0o755)


def test_database_start_failure_does_not_start_migration_dependencies(deploy_lab):
    (deploy_lab["root"] / ".release.env").unlink()
    (deploy_lab["root"] / ".release-sha").unlink()
    result = _run(deploy_lab, {"BM_DATABASE_START_EXIT": "41"})
    assert result.returncode == 41, result.stderr
    assert _marker(deploy_lab).exists()
    assert not any("up -d --remove-orphans" in line for line in _trace(deploy_lab))
    assert not any(line.startswith("restore:") for line in _trace(deploy_lab))
    assert not list(deploy_lab["root"].glob(".release.env.recovery.*"))


@pytest.mark.parametrize("extra_env", [
    {"BM_RESTORE_EXIT": "42"},
    {"BM_SMOKE_EXIT": "43"},
])
def test_failed_automatic_rollback_flags_incident_and_blocks_redeploy(deploy_lab, extra_env):
    first = _run(deploy_lab, {**extra_env, "BM_RELEASE_START_EXIT": "41"})
    assert first.returncode == 41, first.stderr
    assert "manual recovery required" in first.stderr
    assert _marker(deploy_lab).is_file()
    assert "failed_release=" + NEW_SHA in _marker(deploy_lab).read_text(encoding="utf-8")
    assert (deploy_lab["root"] / ".release-sha").read_text(encoding="utf-8") == OLD_SHA + "\n"
    assert "new@example.invalid" in (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8")
    _assert_temporary_files_cleaned(deploy_lab)

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
    result = _run(deploy_lab, {"BM_RELEASE_START_EXIT": "41"})
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
    result = _run(deploy_lab, extra_env={**failed_recovery_step, "BM_RELEASE_START_EXIT": "41"})
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
        "BM_SCHEMA_PROBE_EXIT": "47"
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
        "BM_SCHEMA_PROBE_VALUE": "unknown"
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
        "BM_RELEASE_START_EXIT": "53",
    })
    assert result.returncode == 53, result.stderr
    trace = _trace(deploy_lab)
    prepared, = [line for line in trace if line.startswith("prepare:")]
    restored, = [line for line in trace if line.startswith("restore:")]
    candidate_up, = [line for line in trace if " up -d --remove-orphans" in line]
    assert prepared.endswith("/batalla_ci-20261120T123456Z-A1b2C3d4.dump")
    assert restored.endswith("/archive.dump")
    assert trace.index(prepared) < trace.index(candidate_up) < trace.index(restored)
    assert decoy.exists()
    assert not list((deploy_lab["root"] / ".ops-state").glob("backup-receipt.*"))
    assert not _marker(deploy_lab).exists()


@pytest.mark.parametrize(("fault", "diagnostic"), [
    ("receipt", "invalid prepared archive receipt"),
    ("enospc", "No space left on device"),
    ("checksum", "archive checksum mismatch"),
    ("dbname", "does not match configured 'batalla_ci'"),
])
def test_prepare_failure_preserves_active_release_without_starting_services(
    deploy_lab, fault, diagnostic
):
    if fault == "receipt":
        env = {"BM_INVALID_PREPARED_RECEIPT": "1"}
    else:
        _use_real_restore(deploy_lab)
        env = {"BM_COPY_FAILURE": fault, "BM_ARCHIVE_DB": "other_db"}
    result = _run(deploy_lab, env)
    assert result.returncode != 0
    assert diagnostic in result.stderr
    trace = _trace(deploy_lab)
    assert "backup" in trace
    assert not any(
        fragment in line
        for line in trace
        for fragment in (" up -d --remove-orphans", "migrate", "seed", "restore:", "pg_restore --clean", " stop ")
    )
    root = deploy_lab["root"]
    assert (root / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]
    assert (root / ".release-sha").read_text(encoding="utf-8") == OLD_SHA + "\n"
    assert (root / "backups" / BACKUP_NAME).read_bytes() == b"fixture database dump"
    assert not _marker(deploy_lab).exists()
    _assert_temporary_files_cleaned(deploy_lab)


def test_real_auto_restore_reuses_prepared_copy_after_source_disappears(deploy_lab):
    _use_real_restore(deploy_lab)
    result = _run(deploy_lab, {"BM_RELEASE_START_EXIT": "53", "BM_REMOVE_SOURCE_ON_START": "1"})
    assert result.returncode == 53, result.stderr
    trace = _trace(deploy_lab)
    copy, = [i for i, line in enumerate(trace) if line.startswith("copy:")]
    prepare_list, restore_list = [i for i, line in enumerate(trace) if "pg_restore --list" in line]
    candidate_up, previous_up = [i for i, line in enumerate(trace) if " up -d --remove-orphans" in line]
    restore, = [i for i, line in enumerate(trace) if "pg_restore --clean" in line]
    assert copy < prepare_list < candidate_up < restore_list < restore < previous_up
    assert "--env-file .release.env.previous " in trace[prepare_list]
    assert "backend worker frontend nginx caddy" in trace[previous_up]
    assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]
    assert not (deploy_lab["root"] / "backups" / BACKUP_NAME).exists()
    assert not _marker(deploy_lab).exists()
    _assert_temporary_files_cleaned(deploy_lab)


def test_successful_deploy_cleans_private_copy_and_keeps_original_backup_in_manifest(deploy_lab):
    python = deploy_lab["root"] / "bin" / "python3"
    python.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1:$2" == "-:https://staging.example.invalid" ]]; then\n'
        "  cat >/dev/null\n"
        "  exit 0\n"
        "fi\n"
        f'exec {shlex.quote(sys.executable)} "$@"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    result = _run(deploy_lab)
    assert result.returncode == 0, result.stderr
    trace = _trace(deploy_lab)
    prepared, = [i for i, line in enumerate(trace) if line.startswith("prepare:")]
    candidate_up, = [i for i, line in enumerate(trace) if " up -d --remove-orphans" in line]
    assert prepared < candidate_up
    assert not any(line.startswith("restore:") for line in trace)
    root = deploy_lab["root"]
    manifest = json.loads((root / ".ops-state" / "deployments" / f"{NEW_SHA}.json").read_text())
    backup = root / "backups" / BACKUP_NAME
    assert manifest["rollback_backup"] == str(backup)
    assert backup.is_file()
    assert not _marker(deploy_lab).exists()
    _assert_temporary_files_cleaned(deploy_lab)


@pytest.mark.parametrize("receipt_mode", ["empty", "foreign"])
def test_invalid_backup_receipt_blocks_release_pull(deploy_lab, receipt_mode):
    result = _run(deploy_lab, {
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
        "BM_RELEASE_START_EXIT": "54",
        "BM_TEST_BACKUP_DIR": str(backup_dir) + "/",
    })
    assert result.returncode == 54, result.stderr
    assert any(
        line.startswith("prepare:") and
        line.endswith("/batalla_ci-20261120T123456Z-A1b2C3d4.dump")
        for line in _trace(deploy_lab)
    )
    assert not _marker(deploy_lab).exists()


def test_pre_migration_image_pull_failure_does_not_restore_or_migrate(deploy_lab):
    result = _run(deploy_lab, {
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
    _assert_temporary_files_cleaned(deploy_lab)


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
    # image-pull failure.
    retried = _run(deploy_lab, {"BM_RELEASE_PULL_EXIT": "55"})
    assert retried.returncode == 55
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
    result = _run(deploy_lab, {
        "BM_RELEASE_START_EXIT": "41",
        "RESTORE_PREPARE_ONLY": "invalid",
        "RESTORE_START_SERVICES": "invalid",
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


def test_compose_project_change_is_refused_before_database_access(deploy_lab):
    """A same-named database in a different Compose project is not the old database."""
    active_path = deploy_lab["root"] / ".release.env"
    active_path.write_text(active_path.read_text(encoding="utf-8") +
                           "COMPOSE_PROJECT_NAME=historical_world\n", encoding="utf-8")
    candidate = deploy_lab["base"]
    candidate.write_text(candidate.read_text(encoding="utf-8") +
                         "COMPOSE_PROJECT_NAME=different_project\n", encoding="utf-8")
    result = _run(deploy_lab)
    assert result.returncode == 2
    assert "PostgreSQL connection changed" in result.stderr
    assert _trace(deploy_lab) == []
    assert not _marker(deploy_lab).exists()
    assert (deploy_lab["root"] / ".release-sha").read_text(encoding="utf-8") == OLD_SHA + "\n"
    assert not (deploy_lab["root"] / ".release.env.next").exists()


def test_managed_database_start_failure_is_retryable(deploy_lab):
    """A stopped DB may be restarted with the old environment, without migrate/seed."""
    failed = _run(deploy_lab, {"BM_DATABASE_START_EXIT": "41"})
    assert failed.returncode == 41
    assert not _marker(deploy_lab).exists()
    assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]
    assert not any("migrate seed" in line or "up -d --remove-orphans" in line
                   for line in _trace(deploy_lab))
    retry = _run(deploy_lab, {"BM_DATABASE_START_EXIT": "0", "BM_RELEASE_PULL_EXIT": "55"})
    assert retry.returncode == 55, retry.stderr
    trace = _trace(deploy_lab)
    assert any("up -d database" in line for line in trace)
    assert not any("up -d --remove-orphans" in line for line in trace)
    assert not _marker(deploy_lab).exists()
    assert (deploy_lab["root"] / ".release-sha").read_text(encoding="utf-8") == OLD_SHA + "\n"
    _assert_temporary_files_cleaned(deploy_lab)


def test_base_env_alias_to_next_candidate_is_rejected_without_removing_input(deploy_lab):
    candidate = deploy_lab["root"] / ".release.env.next"
    source = deploy_lab["base"].read_bytes()
    candidate.write_bytes(source)
    result = subprocess.run(
        ["bash", "ops/deploy_remote.sh", str(candidate), NEW_SHA,
         "registry.example.invalid/game/backend",
         "registry.example.invalid/game/frontend"],
        cwd=deploy_lab["root"], capture_output=True, text=True,
        env=deploy_lab["env"], timeout=20, check=False,
    )
    assert result.returncode == 2
    assert "aliases a temporary candidate" in result.stderr
    assert candidate.read_bytes() == source
    assert (deploy_lab["root"] / ".release.env").read_text(encoding="utf-8") == deploy_lab["active"]
    assert (deploy_lab["root"] / ".release-sha").read_text(encoding="utf-8") == OLD_SHA + "\n"
    assert not _marker(deploy_lab).exists()
    assert _trace(deploy_lab) == []
