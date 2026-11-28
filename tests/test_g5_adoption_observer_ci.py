import os
from pathlib import Path

import pytest


_LIVE_CI = (
    os.environ.get("GITHUB_ACTIONS") == "true"
    and os.environ.get("CI") == "true"
    and Path("/var/run/docker.sock").is_socket()
)


@pytest.mark.skipif(not _LIVE_CI, reason="requires GitHub-hosted CI local Docker")
def test_owned_live_compose_pg15_observation_and_runtime_mutation():
    from ops.ci_g5_adoption_observer import run

    run()
