"""BM-0093: rollback must not commit release metadata before recovery succeeds.

All commands run in a temporary fixture repository; Docker, restore, and smoke
are stubs. These tests never touch a staging or production deployment.
"""

import fcntl
import hashlib
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
        "if [[ \"${RESTORE_PREPARE_ONLY:-0}\" == 1 ]]; then\n"
        "  backup=\"$2\"\n"
        "  if [[ ! -s \"${backup}.sha256\" ]] || ! sha256sum --check \"${backup}.sha256\" >/dev/null 2>&1; then\n"
        "    echo 'Restore preflight checksum mismatch' >&2\n"
        "    exit 2\n"
        "  fi\n"
        '  [[ "$3" == PREPARE:batalla_ci && "$RESTORE_START_SERVICES" == 0 ]] || exit 98\n'
        '  cp -- "$backup" "$4/archive.dump"\n'
        '  hash="$(sha256sum < "$4/archive.dump" | cut -d" " -f1)"\n'
        '  printf "%s:%s\\n" "$hash" "$(stat -c %d:%i "$4/archive.dump")"\n'
        "  exit 0\n"
        "fi\n"
        "printf 'restore:%s\\n' \"$1\" >> \"$BM_TRACE\"\n"
        "exit \"${BM_RESTORE_EXIT:-0}\"\n",
        encoding="utf-8",
    )
    (ops / "smoke_http.py").write_text(
        "import os, sys\n"
        "from pathlib import Path\n"
        "with open(os.environ['BM_TRACE'], 'a', encoding='utf-8') as f:\n"
        "    f.write('smoke\\n')\n"
        "if os.environ.get('BM_SWAP_RECOVERY_MARKER') == '1':\n"
        "    marker = Path('.ops-state/recovery-required')\n"
        "    marker.unlink()\n"
        "    marker.write_text('reason=foreign_operator_incident\\n')\n"
        "if os.environ.get('BM_DELETE_RECOVERY_MARKER') == '1':\n"
        "    Path('.ops-state/recovery-required').unlink()\n"
        "    if os.environ.get('BM_DELETE_ORIGINAL_MARKER') == '1':\n"
        "        for old in Path('.ops-state').glob('recovery-required.*'):\n"
        "            old.unlink()\n"
        "sys.exit(int(os.environ.get('BM_SMOKE_EXIT', '0')))\n",
        encoding="utf-8",
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'docker:%s\\n' \"$*\" >> \"$BM_TRACE\"\n"
        "if [[ \"$*\" == *' up --no-deps '* ]]; then\n"
        "  if [[ \"${BM_SIGNAL_UP:-0}\" == 1 ]]; then\n"
        "    kill -\"${BM_SIGNAL_KIND:-TERM}\" \"$PPID\"\n"
        "    sleep 0.2\n"
        "    if [[ \"${BM_SIGNAL_AGAIN:-0}\" == 1 ]]; then kill -\"${BM_SIGNAL_KIND:-TERM}\" \"$PPID\"; fi\n"
        "    printf 'writer-started-late\\n' >> \"$BM_TRACE\"\n"
        "  fi\n"
        "  exit \"${BM_UP_EXIT:-0}\"\n"
        "fi\n"
        "if [[ \"$*\" == *' stop -t 120 '* ]]; then exit \"${BM_STOP_EXIT:-0}\"; fi\n"
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
    (backups / "sample.dump.sha256").write_text(
        f"{hashlib.sha256(backup.read_bytes()).hexdigest()}  {backup}\n",
        encoding="utf-8",
    )
    manifest = tmp_path / ".ops-state" / "deployments" / (CURRENT_SHA + ".json")
    manifest.write_text(
        json.dumps({"previous_release_sha": PREVIOUS_SHA, "rollback_backup": None}),
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


@pytest.mark.parametrize("backup_exists", [True, False])
def test_snapshot_rollback_is_refused_even_without_prior_incident(rollback_lab, backup_exists):
    # A valid archive is not proof that post-snapshot commits can be discarded.
    rollback_lab["manifest"].write_text(
        json.dumps({"previous_release_sha": PREVIOUS_SHA,
                    "rollback_backup": str(rollback_lab["backup"])}),
        encoding="utf-8",
    )
    if not backup_exists:
        rollback_lab["backup"].unlink()
    result = _run(rollback_lab)
    assert result.returncode == 2, result.stderr
    assert "snapshot-based legacy rollback is disabled" in result.stderr
    assert _trace(rollback_lab) == []
    _assert_active_unchanged(rollback_lab)
    assert not (rollback_lab["root"] / ".ops-state" / "recovery-required").exists()

@pytest.mark.parametrize("failed_step", ["docker", "smoke"])
def test_failed_application_only_recovery_preserves_active_release_pointers(
    rollback_lab, failed_step
):
    env = {"BM_DOCKER_EXIT": "35"} if failed_step == "docker" else {"BM_SMOKE_EXIT": "36"}
    result = _run(rollback_lab, extra_env=env)
    assert result.returncode == (35 if failed_step == "docker" else 36)
    trace = _trace(rollback_lab)
    assert trace and trace[0].startswith("docker:compose --env-file ./.release.env.rollback.")
    assert ("smoke" in trace) == (failed_step == "smoke")
    stop = [line for line in trace if " stop -t 120 backend worker migrate seed" in line]
    assert len(stop) == (1 if failed_step == "smoke" else 0), trace
    if stop:
        assert "CRITICAL: rollback did not pass smoke" in result.stderr
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


def test_application_only_rollback_stops_writers_if_compose_partially_starts(rollback_lab):
    result = _run(rollback_lab, extra_env={"BM_UP_EXIT": "43"})
    assert result.returncode == 43, result.stderr
    trace = _trace(rollback_lab)
    assert any(" up --no-deps -d --remove-orphans " in line for line in trace)
    assert sum(" stop -t 120 backend worker migrate seed" in line for line in trace) == 1
    assert "smoke" not in trace
    assert "CRITICAL: rollback did not pass smoke" in result.stderr
    assert (rollback_lab["root"] / ".ops-state/recovery-required").is_file()
    _assert_active_unchanged(rollback_lab)


@pytest.mark.parametrize(
    ("signal_kind", "expected_code"),
    [("TERM", 143), ("HUP", 129), ("USR1", 138), ("PIPE", 141), ("ALRM", 142)],
)
@pytest.mark.parametrize("repeat_signal", [False, True])
def test_termination_signals_wait_for_compose_up_before_stopping_writers(
    rollback_lab, repeat_signal, signal_kind, expected_code
):
    result = _run(rollback_lab, extra_env={
        "BM_SIGNAL_UP": "1",
        "BM_SIGNAL_KIND": signal_kind,
        "BM_SIGNAL_AGAIN": "1" if repeat_signal else "0",
    })
    assert result.returncode == expected_code, result.stderr
    trace = _trace(rollback_lab)
    assert "writer-started-late" in trace, trace
    stops = [i for i, line in enumerate(trace)
             if " stop -t 120 backend worker migrate seed" in line]
    assert len(stops) == 1 and trace.index("writer-started-late") < stops[0], trace
    assert "smoke" not in trace
    assert (rollback_lab["root"] / ".ops-state/recovery-required").is_file()
    _assert_active_unchanged(rollback_lab)


@pytest.mark.parametrize("missing_original", [False, True])
def test_rollback_rearms_missing_durable_incident_marker(rollback_lab, missing_original):
    result = _run(rollback_lab, extra_env={
        "BM_DELETE_RECOVERY_MARKER": "1",
        "BM_DELETE_ORIGINAL_MARKER": "1" if missing_original else "0",
    })
    assert result.returncode == 2, result.stderr
    assert "recovery marker was replaced or disappeared" in result.stderr
    trace = _trace(rollback_lab)
    assert "smoke" in trace
    assert sum(" stop -t 120 backend worker migrate seed" in line for line in trace) == 1
    marker = rollback_lab["root"] / ".ops-state/recovery-required"
    assert marker.is_file()
    text = marker.read_text(encoding="utf-8")
    expected_reason = (
        "reason=rollback_recovery_marker_rearmed" if missing_original
        else "reason=manual_rollback_in_progress"
    )
    assert expected_reason in text
    assert not list((rollback_lab["root"] / ".ops-state").glob("recovery-required.*"))
    assert (rollback_lab["root"] / ".release-sha").read_text().strip() == PREVIOUS_SHA


def test_app_only_rollback_reports_stop_failure_without_masking_smoke_error(rollback_lab):
    result = _run(rollback_lab, extra_env={"BM_SMOKE_EXIT": "36", "BM_STOP_EXIT": "50"})
    assert result.returncode == 36, result.stderr
    assert "CRITICAL: writer stop failed" in result.stderr
    assert sum(" stop -t 120 backend worker migrate seed" in line for line in _trace(rollback_lab)) == 1
    assert (rollback_lab["root"] / ".ops-state/recovery-required").is_file()
    _assert_active_unchanged(rollback_lab)


def test_app_only_rollback_rejects_replaced_incident_marker_after_smoke(rollback_lab):
    result = _run(rollback_lab, extra_env={"BM_SWAP_RECOVERY_MARKER": "1"})
    assert result.returncode == 2, result.stderr
    assert "recovery marker was replaced or disappeared" in result.stderr
    trace = _trace(rollback_lab)
    assert "smoke" in trace
    stop = [line for line in trace if " stop -t 120 backend worker migrate seed" in line]
    assert len(stop) == 1, trace
    assert "--env-file .release.env " in stop[0]  # staged env was already moved
    assert (rollback_lab["root"] / ".ops-state/recovery-required").read_text() == (
        "reason=foreign_operator_incident\n"
    )
    assert (rollback_lab["root"] / ".release-sha").read_text().strip() == PREVIOUS_SHA
    assert not list(rollback_lab["root"].glob(".release*.rollback.*"))


def test_success_commits_both_release_pointers_after_smoke(rollback_lab):
    result = _run(rollback_lab)
    assert result.returncode == 0, result.stderr
    assert _trace(rollback_lab)[-1] == "smoke"
    assert (rollback_lab["root"] / ".release.env").read_text(encoding="utf-8") == rollback_lab["previous"]
    assert (rollback_lab["root"] / ".release-sha").read_text(encoding="utf-8") == PREVIOUS_SHA + "\n"
    assert not (rollback_lab["root"] / ".ops-state" / "recovery-required").exists()
    assert not list(rollback_lab["root"].glob(".release.env.rollback.*"))
    assert not list(rollback_lab["root"].glob(".release-sha.rollback.*"))


def test_application_only_rollback_never_starts_migrate_or_seed(rollback_lab):
    result = _run(rollback_lab)
    assert result.returncode == 0, result.stderr
    commands = _trace(rollback_lab)
    up = [line for line in commands if " up " in line]
    assert len(up) == 1, commands
    assert " up --no-deps -d --remove-orphans backend worker frontend nginx caddy" in up[0]
    assert "migrate" not in up[0].split()
    assert "seed" not in up[0].split()
    assert (rollback_lab["root"] / ".release-sha").read_text().strip() == PREVIOUS_SHA


@pytest.mark.parametrize("receipt_kind", ["file", "symlink", "directory"])
def test_orphaned_incident_evidence_blocks_deploy_and_app_only_rollback(
    rollback_lab, receipt_kind
):
    orphan = rollback_lab["root"] / ".ops-state/recovery-required.orphaned"
    sentinel = rollback_lab["root"] / "external-sentinel"
    sentinel.write_text("do not alter\\n", encoding="utf-8")
    if receipt_kind == "file":
        orphan.write_text("reason=failed_rearm\\n", encoding="utf-8")
    elif receipt_kind == "symlink":
        orphan.symlink_to(sentinel)
    else:
        orphan.mkdir()
    rollback = _run(rollback_lab)
    deploy = _run_deploy(rollback_lab)
    assert rollback.returncode == 2, rollback.stderr
    assert deploy.returncode == 2, deploy.stderr
    assert "orphaned recovery evidence" in rollback.stderr
    assert "orphaned recovery evidence" in deploy.stderr
    assert _trace(rollback_lab) == []
    assert sentinel.read_text() == "do not alter\\n"
    _assert_active_unchanged(rollback_lab)
    assert orphan.is_symlink() if receipt_kind == "symlink" else orphan.exists()


def test_application_only_rollback_refuses_existing_recovery_incident(rollback_lab):
    rollback_lab["manifest"].write_text(
        json.dumps({"previous_release_sha": PREVIOUS_SHA, "rollback_backup": None}),
        encoding="utf-8",
    )
    marker = rollback_lab["root"] / ".ops-state" / "recovery-required"
    marker.write_text("reason=database_recovery_still_pending\n", encoding="utf-8")

    result = _run(rollback_lab)

    assert result.returncode == 2, result.stderr
    assert "existing recovery incident requires certified G5" in result.stderr
    assert _trace(rollback_lab) == []
    _assert_active_unchanged(rollback_lab)
    assert marker.read_text(encoding="utf-8") == "reason=database_recovery_still_pending\n"


def test_invalid_snapshot_never_bypasses_g5_legacy_rollback_guard(rollback_lab):
    rollback_lab["manifest"].write_text(
        json.dumps({"previous_release_sha": PREVIOUS_SHA,
                    "rollback_backup": str(rollback_lab["backup"])}),
        encoding="utf-8",
    )
    sidecar = rollback_lab["backup"].with_name(rollback_lab["backup"].name + ".sha256")
    sidecar.write_text(f'{"0" * 64}  {rollback_lab["backup"]}\n', encoding="utf-8")
    result = _run(rollback_lab)
    assert result.returncode == 2
    assert "snapshot-based legacy rollback is disabled" in result.stderr
    assert not (rollback_lab["root"] / ".ops-state" / "recovery-required").exists()
    assert _trace(rollback_lab) == []
    _assert_active_unchanged(rollback_lab)

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
