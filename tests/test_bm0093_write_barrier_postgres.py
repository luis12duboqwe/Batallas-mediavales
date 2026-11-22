"""BM-0093: real PostgreSQL snapshot and write-barrier invariants.

Only disposable PostgreSQL 15 containers are used; they have no network,
published ports, or persistent volumes.
"""

from pathlib import Path
import shutil
import subprocess
import time
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


def _ensure_docker_and_image():
    if not shutil.which("docker"):
        pytest.skip("Docker is not installed; disposable PostgreSQL 15 is unavailable")
    try:
        docker_info = _run(["docker", "info"], timeout=15, check=False)
    except subprocess.TimeoutExpired:
        pytest.skip("Docker daemon did not respond; disposable PostgreSQL 15 is unavailable")
    if docker_info.returncode:
        pytest.skip("Docker daemon is unavailable; disposable PostgreSQL 15 is unavailable")
    if _run(["docker", "image", "inspect", IMAGE], check=False).returncode:
        try:
            pulled = _run(["docker", "pull", IMAGE], timeout=120, check=False)
        except subprocess.TimeoutExpired:
            pytest.skip("Timed out obtaining the disposable PostgreSQL 15 image")
        if pulled.returncode:
            pytest.skip(
                "PostgreSQL 15 image is unavailable and could not be pulled: "
                + pulled.stderr.strip()
            )


@pytest.fixture(scope="module")
def postgres_pair():
    _ensure_docker_and_image()
    suffix = uuid.uuid4().hex[:12]
    containers = [f"bm0093-src-{suffix}", f"bm0093-dst-{suffix}"]
    started = []
    try:
        for name in containers:
            started.append(name)
            try:
                result = _run(
                    [
                        "docker", "run", "--detach", "--rm", "--network", "none",
                        "--name", name,
                        "--env", f"POSTGRES_DB={DATABASE}",
                        "--env", "POSTGRES_HOST_AUTH_METHOD=trust",
                        IMAGE,
                    ],
                    timeout=60,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                pytest.skip("Timed out starting disposable PostgreSQL 15")
            if result.returncode:
                pytest.skip(
                    "Could not start disposable PostgreSQL 15: "
                    + result.stderr.strip()
                )
            for _ in range(60):
                ready = _run(
                    [
                        "docker", "exec", name, "pg_isready", "-U", "postgres",
                        "-d", DATABASE,
                    ],
                    check=False,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.5)
            else:
                pytest.skip(f"Disposable PostgreSQL 15 container {name} did not become ready")

            version = _sql(name, "SHOW server_version_num;")
            assert int(version) // 10000 == 15
        yield containers[0], containers[1]
    finally:
        for name in started:
            _run(["docker", "rm", "--force", name], check=False)


def _sql(container, statement, *, app_name="bm0093-test"):
    result = _run(
        [
            "docker", "exec", "--env", f"PGAPPNAME={app_name}", container,
            "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
            "-d", DATABASE, "-Atqc", statement,
        ]
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


def _wait_for_lock(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    pytest.fail("PostgreSQL advisory-lock invariant did not reach the expected state")


def _lock_count(container, mode, granted):
    return int(
        _sql(
            container,
            "SELECT count(*) FROM pg_locks "
            f"WHERE locktype='advisory' AND objid={LOCK_KEY} AND objsubid=1 "
            f"AND mode='{mode}' AND granted={str(granted).lower()};",
        )
    )


def _start_psql(container, app_name, sql):
    return subprocess.Popen(
        [
            "docker", "exec", "--env", f"PGAPPNAME={app_name}", container,
            "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
            "-d", DATABASE, "-c", sql,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_advisory_barrier_drains_and_blocks_protocol_participants(postgres_pair):
    source, destination = postgres_pair
    _reset_tables(source, destination)
    writers = []
    barrier = None
    try:
        before = _start_psql(
            source,
            "bm0093-writer-before",
            "BEGIN; "
            f"SELECT pg_advisory_xact_lock_shared({LOCK_KEY}); "
            "INSERT INTO bm0093_markers VALUES ('before'); "
            "SELECT pg_sleep(0.8); COMMIT;",
        )
        writers.append(before)
        _wait_for_lock(lambda: _lock_count(source, "ShareLock", True) == 1)

        barrier = _start_psql(
            source,
            "bm0093-barrier",
            f"SELECT pg_advisory_lock({LOCK_KEY}); SELECT pg_sleep(1.5); "
            f"SELECT pg_advisory_unlock({LOCK_KEY});",
        )
        _wait_for_lock(lambda: _lock_count(source, "ExclusiveLock", False) == 1)

        during = _start_psql(
            source,
            "bm0093-writer-during",
            "BEGIN; "
            f"SELECT pg_advisory_xact_lock_shared({LOCK_KEY}); "
            "INSERT INTO bm0093_markers VALUES ('during'); COMMIT;",
        )
        writers.append(during)
        _wait_for_lock(lambda: _lock_count(source, "ShareLock", False) == 1)

        _, before_error = before.communicate(timeout=10)
        assert before.returncode == 0, before_error
        _wait_for_lock(lambda: _lock_count(source, "ExclusiveLock", True) == 1)
        assert _sql(
            source, "SELECT marker FROM bm0093_markers ORDER BY marker;"
        ) == "before"
        assert during.poll() is None

        _, barrier_error = barrier.communicate(timeout=10)
        assert barrier.returncode == 0, barrier_error
        _, during_error = during.communicate(timeout=10)
        assert during.returncode == 0, during_error
        assert _sql(source, "SELECT marker FROM bm0093_markers ORDER BY marker;") == "before\nduring"
    finally:
        for process in [*writers, barrier]:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
