"""Regression coverage for the CI fixture's fail-closed file handling."""

import os
import signal
from types import SimpleNamespace

import pytest

from ops import ci_g5_actual_reopen as reopen
from ops.g5_cutover_state import StateError


@pytest.fixture
def publication(tmp_path):
    port = object.__new__(reopen.ActualReopenPort)
    port.request = SimpleNamespace(host_root=str(tmp_path))
    port.release = tmp_path / ".release-sha"
    port.release_identity = None
    identity = SimpleNamespace(candidate_sha="b" * 40)
    port.publish_candidate(identity)
    return port, identity


def test_publication_is_pinned_and_readable(publication):
    port, identity = publication
    port.require_publication(identity)


def test_publication_rejects_wrong_owner(publication, monkeypatch):
    port, identity = publication
    real_fstat = os.fstat

    def wrong_owner(fd):
        info = real_fstat(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_uid=info.st_uid + 1,
                               st_nlink=info.st_nlink, st_dev=info.st_dev,
                               st_ino=info.st_ino, st_size=info.st_size)

    monkeypatch.setattr(reopen.os, "fstat", wrong_owner)
    with pytest.raises(StateError, match="unsafe candidate publication"):
        port.require_publication(identity)


@pytest.mark.parametrize("drift", ["symlink", "replacement", "mode", "hardlink", "content", "fifo"])
def test_publication_rejects_drift(publication, tmp_path, drift):
    port, identity = publication
    if drift == "symlink":
        saved = tmp_path / "saved"
        port.release.rename(saved)
        port.release.symlink_to(saved)
    elif drift == "replacement":
        saved = tmp_path / "saved"
        port.release.rename(saved)
        port.release.write_text(identity.candidate_sha + "\n")
        port.release.chmod(0o600)
    elif drift == "mode":
        port.release.chmod(0o644)
    elif drift == "hardlink":
        os.link(port.release, tmp_path / "second-link")
    elif drift == "content":
        port.release.write_text("c" * 40 + "\n")
    else:
        port.release.unlink()
        os.mkfifo(port.release, 0o600)
    with pytest.raises(StateError):
        port.require_publication(identity)


def test_fifo_receipt_is_rejected_without_waiting(tmp_path):
    database = reopen.OriginalDatabase("game_ci", 100, "game_app", 101, "postgres",
                                       102, 12, True, 150009)
    row = {
        "Id": "a" * 64, "Image": "sha256:" + "b" * 64,
        "Config": {"Labels": {"com.docker.compose.project": "ci_project",
                              "com.docker.compose.service": "worker"}},
        "HostConfig": {"RestartPolicy": {"Name": "no", "MaximumRetryCount": 0}},
    }
    original = reopen.OriginalContainer.capture(row, "ci_project", "worker")
    path = tmp_path / "receipt"
    os.mkfifo(path, 0o600)

    def timeout(_signum, _frame):
        raise AssertionError("FIFO receipt read blocked")

    previous = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(3)
    try:
        with pytest.raises(StateError):
            reopen.require_original_receipt(path, database, [original])
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def test_cleanup_failure_preserves_workspace_and_reports_project(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(reopen, "__file__", "/fictional-checkout/ops/ci_g5_actual_reopen.py")
    monkeypatch.setattr(reopen.shutil, "copyfile", lambda _src, dst: dst.write_text("fixture"))

    def fail_command(_args):
        raise RuntimeError("network creation failed")

    def fail_cleanup(_project):
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(reopen, "run", fail_command)
    monkeypatch.setattr(reopen, "cleanup_fixture", fail_cleanup)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        reopen.run_case("precommit", str(tmp_path))
    roots = list(tmp_path.iterdir())
    assert len(roots) == 1
    assert (roots[0] / "host" / ".ops-state").is_dir()
    error = capsys.readouterr().err
    assert "fixture cleanup uncertain; project=bm-g5-edge-" in error
    assert str(roots[0]) in error


def test_removed_health_scenario_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    with pytest.raises(StateError, match="unknown fixture scenario"):
        reopen.run_case("health", str(tmp_path))
