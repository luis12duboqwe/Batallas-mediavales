import json
import os
from pathlib import Path

import pytest


def test_fixture_compose_does_not_persist_generated_credentials(tmp_path):
    from ops.ci_g5_adoption_observer import _compose_file

    project = "bm-g5-adoption-" + "a" * 32
    compose_path, env_file = _compose_file(tmp_path, project, "b" * 40)
    config = json.loads(compose_path.read_text(encoding="utf-8"))
    assert env_file.read_text(encoding="ascii") == ""
    assert env_file.stat().st_mode & 0o777 == 0o600
    assert config["services"]["database"]["environment"]["POSTGRES_PASSWORD"] == (
        "${POSTGRES_PASSWORD:?required}"
    )
    assert config["services"]["backend"]["environment"]["DATABASE_URL"] == (
        "${DB_URL:?required}"
    )


_LIVE_CI = (
    os.environ.get("GITHUB_ACTIONS") == "true"
    and os.environ.get("CI") == "true"
    and Path("/var/run/docker.sock").is_socket()
)


@pytest.mark.skipif(not _LIVE_CI, reason="requires GitHub-hosted CI local Docker")
def test_owned_live_compose_pg15_observation_and_runtime_mutation():
    from ops.ci_g5_adoption_observer import run

    run()
