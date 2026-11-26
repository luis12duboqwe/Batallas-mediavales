"""Opt-in real Docker/PG15 rehearsal; never reaches a configured game database."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    os.environ.get("BM_G5_FULL_SCHEMA_RESTORE") != "1"
    or os.environ.get("GITHUB_ACTIONS") != "true"
    or os.environ.get("CI") != "true",
    reason="explicit opt-in and GitHub CI required for disposable Docker PG15",
)
def test_real_full_schema_restore_adversaries():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "ops.ci_g5_full_schema_restore", "--scenario", "all"],
        cwd=root, capture_output=True, text=True, timeout=1800, check=False,
    )
    print(result.stdout, end="")
    assert result.returncode == 0, result.stderr
    evidence = [json.loads(line) for line in result.stdout.splitlines()]
    assert [item["scenario"] for item in evidence] == [
        "rollback", "restore-failure", "tampered", "drift", "dependency"]
    for item in evidence:
        assert item["result"] == "passed"
        assert item["same_database"] and item["app_barrier_closed"]
        assert item["tables"] > 2 and item["sequences"] > 2
        assert item["catalog_blocks"] > item["tables"]
        assert "snapshot removed" in item["cleanup"]
    assert [item["outcome"] for item in evidence] == [
        "previous_restored", "candidate_retained",
        "restore_refused", "restore_refused", "restore_refused"]
