"""BM-0093: real PostgreSQL snapshot and write-barrier invariants.

Only disposable PostgreSQL 15 containers are used; they have no network,
published ports, or persistent volumes.
"""

from contextlib import ExitStack
import os
from pathlib import Path
import shutil
import subprocess
import time
from unittest.mock import Mock
import uuid

import pytest


DATABASE = "bm0093_test"
IMAGE = "postgres:15-alpine"
LOCK_KEY = 930093


def _run(command, *, timeout=30, check=True):
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=check,
    )


def _postgres_unavailable(reason):
    if os.environ.get("CI", "").lower() == "true":
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


def _docker_setup_command(command, reason, *, timeout=15):
    try:
        result = _run(command, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        _postgres_unavailable(f"{reason}: {exc}")
    if result.returncode:
        _postgres_unavailable(f"{reason}: {result.stderr.strip()}")


def _ensure_docker_and_image():
    if not shutil.which("docker"):
        _postgres_unavailable("Docker is not installed")
    _docker_setup_command(["docker", "info"], "Docker daemon is unavailable")
    _docker_setup_command(
        ["docker", "image", "inspect", IMAGE],
        f"Required local image {IMAGE} is unavailable",
    )


def _remove_containers(containers):
    errors = []
    for name in containers:
        try:
            result = _run(["docker", "rm", "-f", name], timeout=15, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        error = result.stderr.strip()
        # Docker --rm can already have removed a container that exited.
        if result.returncode and error != (
            f"Error response from daemon: No such container: {name}"
        ):
            errors.append(f"{name}: exit {result.returncode}: {error}")
    if errors:
        pytest.fail("Docker cleanup failed:\n" + "\n".join(errors), pytrace=False)


def _wait_for_postgres(name):
    deadline = time.monotonic() + 30
    last_error = "PID 1 is not postgres"
    while time.monotonic() < deadline:
        try:
            pid1 = _run(
                ["docker", "exec", name, "cat", "/proc/1/comm"], timeout=2,
            )
            if pid1.stdout.strip() == "postgres":
                _run(
                    ["docker", "exec", name, "pg_isready", "-U", "postgres", "-d", DATABASE],
                    timeout=2,
                )
                version = _sql(name, "SHOW server_version_num;", timeout=2)
                if int(version) // 10000 != 15:
                    _postgres_unavailable(f"Expected PostgreSQL 15 in {name}, got {version}")
                return
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            last_error = str(exc)
        time.sleep(0.1)
    _postgres_unavailable(f"Timed out waiting for PostgreSQL 15 in {name}: {last_error}")


@pytest.fixture(scope="module")
def postgres_pair():
    _ensure_docker_and_image()
    suffix = uuid.uuid4().hex[:12]
    containers = [f"bm0093-src-{suffix}", f"bm0093-dst-{suffix}"]
    try:
        for name in containers:
            _docker_setup_command(
                [
                    "docker", "run", "--detach", "--rm", "--network", "none",
                    "--pull", "never", "--name", name,
                    "--tmpfs", "/var/lib/postgresql/data",
                    "--env", f"POSTGRES_DB={DATABASE}",
                    "--env", "POSTGRES_HOST_AUTH_METHOD=trust",
                    IMAGE,
                ],
                f"Could not start disposable PostgreSQL 15 container {name}",
                timeout=60,
            )
            _wait_for_postgres(name)
        yield tuple(containers)
    finally:
        _remove_containers(containers)


def _sql(container, statement, *, timeout=30):
    result = _run(
        [
            "docker", "exec", container,
            "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
            "-d", DATABASE, "-Atqc", statement,
        ],
        timeout=timeout,
    )
    return result.stdout.strip()


def _reset_tables(source, destination):
    _sql(
        source,
        "DROP TABLE IF EXISTS bm0093_markers; "
        "CREATE TABLE bm0093_markers (marker text PRIMARY KEY);",
    )
    _sql(
        destination,
        "DROP TABLE IF EXISTS bm0093_markers; "
        "CREATE TABLE bm0093_markers (marker text PRIMARY KEY);",
    )


def _dump(source, tmp_path):
    archive = Path(tmp_path) / f"{uuid.uuid4().hex}.dump"
    with archive.open("wb") as output:
        result = subprocess.run(
            [
                "docker", "exec", source, "pg_dump", "--format=custom",
                "--no-owner", "--no-privileges", "-U", "postgres", "-d", DATABASE,
            ],
            stdout=output,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert archive.stat().st_size > 0
    return archive


def _restore(destination, archive):
    with archive.open("rb") as dump:
        result = subprocess.run(
            [
                "docker", "exec", "--interactive", destination, "pg_restore",
                "--clean", "--if-exists", "--no-owner", "--no-privileges",
                "--exit-on-error", "-U", "postgres", "-d", DATABASE,
            ],
            stdin=dump,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_committed_write_after_dump_is_absent_from_restored_snapshot(
    postgres_pair, tmp_path
):
    source, destination = postgres_pair
    _reset_tables(source, destination)
    _sql(source, "INSERT INTO bm0093_markers VALUES ('A');")
    archive = _dump(source, tmp_path)

    _sql(source, "INSERT INTO bm0093_markers VALUES ('B');")
    assert _sql(
        source,
        "SELECT string_agg(marker, ',' ORDER BY marker) FROM bm0093_markers;",
    ) == "A,B"

    _restore(destination, archive)
    assert _sql(destination, "SELECT marker FROM bm0093_markers ORDER BY marker;") == "A"


def test_committed_write_before_dump_is_preserved(postgres_pair, tmp_path):
    source, destination = postgres_pair
    _reset_tables(source, destination)
    _sql(source, "INSERT INTO bm0093_markers VALUES ('A');")
    archive = _dump(source, tmp_path)

    _restore(destination, archive)
    assert _sql(destination, "SELECT marker FROM bm0093_markers ORDER BY marker;") == "A"


def _wait_for_lock(container, app_name, mode, granted):
    deadline = time.monotonic() + 10
    while (remaining := deadline - time.monotonic()) > 0:
        count = _sql(
            container,
            "SELECT count(*) FROM pg_locks JOIN pg_stat_activity USING (pid) "
            "WHERE locktype='advisory' AND classid=0 AND objsubid=1 "
            f"AND objid={LOCK_KEY} AND mode='{mode}' "
            f"AND granted={str(granted).lower()} AND application_name='{app_name}';",
            timeout=remaining,
        )
        if count == "1":
            return
        time.sleep(0.05)
    pytest.fail(f"Timed out waiting for {app_name} {mode} with granted={granted}")


def _close_psql(process):
    try:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def _start_psql(stack, container, app_name):
    process = subprocess.Popen(
        [
            "docker", "exec", "--interactive", "--env", f"PGAPPNAME={app_name}",
            "--env", "PGOPTIONS=-c statement_timeout=60000 -c idle_session_timeout=60000 "
            "-c idle_in_transaction_session_timeout=60000",
            container, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
            "-d", DATABASE, "-Atq",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stack.callback(_close_psql, process)
    return process


def _send_sql(process, statement):
    process.stdin.write(statement + "\n")
    process.stdin.flush()


def _finish_psql(process, statement=None):
    output, error = process.communicate(input=statement, timeout=10)
    assert process.returncode == 0, error
    return output.strip()


def test_advisory_barrier_drains_and_blocks_protocol_participants(postgres_pair):
    source, destination = postgres_pair
    _reset_tables(source, destination)
    before_name = "bm0093-writer-before"
    barrier_name = "bm0093-barrier"
    during_name = "bm0093-writer-during"
    with ExitStack() as sessions:
        before = _start_psql(sessions, source, before_name)
        _send_sql(
            before,
            "BEGIN; "
            f"SELECT pg_advisory_xact_lock_shared({LOCK_KEY}); "
            "INSERT INTO bm0093_markers VALUES ('before');",
        )
        _wait_for_lock(source, before_name, "ShareLock", True)

        barrier = _start_psql(sessions, source, barrier_name)
        _send_sql(barrier, f"SELECT pg_advisory_lock({LOCK_KEY});")
        _wait_for_lock(source, barrier_name, "ExclusiveLock", False)

        during = _start_psql(sessions, source, during_name)
        _send_sql(
            during,
            "BEGIN; "
            f"SELECT pg_advisory_xact_lock_shared({LOCK_KEY}); "
            "INSERT INTO bm0093_markers VALUES ('during'); COMMIT;",
        )
        _wait_for_lock(source, during_name, "ShareLock", False)

        _finish_psql(before, "COMMIT;\n")
        _wait_for_lock(source, barrier_name, "ExclusiveLock", True)
        _wait_for_lock(source, during_name, "ShareLock", False)
        assert _sql(
            source, "SELECT marker FROM bm0093_markers ORDER BY marker;"
        ) == "before"

        assert _finish_psql(barrier, f"SELECT pg_advisory_unlock({LOCK_KEY});\n") == "t"
        _finish_psql(during)
        assert _sql(source, "SELECT marker FROM bm0093_markers ORDER BY marker;") == "before\nduring"


@pytest.mark.parametrize(
    "first_result",
    [
        subprocess.TimeoutExpired("docker rm", 15),
        OSError("docker could not be executed"),
        subprocess.CompletedProcess([], 1, stderr="daemon unavailable"),
    ],
    ids=["timeout", "os-error", "nonzero"],
)
def test_cleanup_reports_failure_and_still_removes_second_container(monkeypatch, first_result):
    run = Mock(side_effect=[first_result, subprocess.CompletedProcess([], 0, stderr="")])
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(pytest.fail.Exception, match="Docker cleanup failed:.*\nsource:"):
        _remove_containers(["source", "destination"])

    assert [entry.args[0] for entry in run.call_args_list] == [
        ["docker", "rm", "-f", "source"],
        ["docker", "rm", "-f", "destination"],
    ]


def test_cleanup_accepts_already_removed_container(monkeypatch):
    run = Mock(side_effect=[
        subprocess.CompletedProcess(
            [], 1, stderr="Error response from daemon: No such container: source",
        ),
        subprocess.CompletedProcess([], 0, stderr=""),
    ])
    monkeypatch.setattr(subprocess, "run", run)

    _remove_containers(["source", "destination"])

    assert run.call_count == 2


@pytest.mark.parametrize("ci", [False, True], ids=["local-skip", "ci-fail"])
@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("cli", "Docker is not installed"),
        ("daemon", "Docker daemon is unavailable"),
        ("image", "Required local image"),
        ("start", "Could not start disposable PostgreSQL 15"),
        ("readiness", "Timed out waiting for PostgreSQL 15"),
    ],
)
def test_postgres_setup_failure_policy(monkeypatch, ci, failure, message):
    if ci:
        monkeypatch.setenv("CI", "true")
    else:
        monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _: None if failure == "cli" else "/mock/docker")
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=0))
    if failure == "readiness":
        monkeypatch.setattr(time, "monotonic", Mock(side_effect=[0, 0, 30]))
        monkeypatch.setattr(time, "sleep", Mock())

    def run(command, **kwargs):
        operation = command[1]
        if (failure, operation) == ("start", "run"):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if (failure, operation) in {("daemon", "info"), ("image", "image")}:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="unavailable")
        if operation == "exec":
            assert command[-2:] == ["cat", "/proc/1/comm"]
            return subprocess.CompletedProcess(command, 0, stdout="docker-entrypoi\n", stderr="")
        assert operation in {"info", "image", "run", "rm"}
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    mocked_run = Mock(side_effect=run)
    monkeypatch.setattr(subprocess, "run", mocked_run)
    outcome = pytest.fail.Exception if ci else pytest.skip.Exception
    with pytest.raises(outcome, match=message):
        next(postgres_pair.__wrapped__())

    removals = [
        entry.args[0] for entry in mocked_run.call_args_list if entry.args[0][1] == "rm"
    ]
    expected = [
        ["docker", "rm", "-f", "bm0093-src-000000000000"],
        ["docker", "rm", "-f", "bm0093-dst-000000000000"],
    ]
    assert removals == (expected if failure in {"start", "readiness"} else [])


def test_readiness_waits_for_definitive_postgres_and_checks_sql(monkeypatch):
    name = "source"
    run = Mock(side_effect=[
        subprocess.CompletedProcess([], 0, stdout="docker-entrypoi\n"),
        subprocess.CompletedProcess([], 0, stdout="postgres\n"),
        subprocess.CompletedProcess([], 0),
        subprocess.CompletedProcess([], 0, stdout="150023\n"),
    ])
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(time, "sleep", Mock())

    _wait_for_postgres(name)

    commands = [entry.args[0] for entry in run.call_args_list]
    assert commands[:3] == [
        ["docker", "exec", name, "cat", "/proc/1/comm"],
        ["docker", "exec", name, "cat", "/proc/1/comm"],
        ["docker", "exec", name, "pg_isready", "-U", "postgres", "-d", DATABASE],
    ]
    assert commands[3][:4] == ["docker", "exec", name, "psql"]
    assert commands[3][-1] == "SHOW server_version_num;"
