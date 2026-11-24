"""Real Docker G5 writer-stop rehearsal; GitHub CI only, no live deployment."""
from __future__ import annotations

import os
import sys
from uuid import uuid4

from ops.g5_docker_writer_fence import DockerWriterFence, DockerFenceError, local_docker


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
        print("CI-only isolated Docker writer shutdown rehearsal", file=sys.stderr)
        return 2
    project = "bm-g5-writer-" + uuid4().hex
    created: list[str] = []

    def create(service: str, *, target_project=project) -> str:
        identity = local_docker([
            "run", "-d", "--network", "none", "--restart", "always",
            "--label", "com.docker.compose.project=" + target_project,
            "--label", "com.docker.compose.service=" + service,
            "--entrypoint", "/bin/sh", "postgres:15-alpine",
            "-c", "exec sleep 300",
        ]).strip()
        created.append(identity)
        return identity

    try:
        passive = [create("database"), create("nginx")]
        writers = [create(s) for s in ("backend", "backend", "worker", "migrate", "seed")]
        # A completed one-shot retains a restart policy until explicitly disabled.
        local_docker(["stop", "--time", "1", writers[-1]])
        other = create("worker", target_project=project + "-foreign")

        fence = DockerWriterFence(project)
        fence.engage()
        fence.assert_closed()
        for identity in writers:
            if local_docker([
                "inspect", "--format", "{{.State.Running}}|{{.HostConfig.RestartPolicy.Name}}",
                identity,
            ]).strip() != "false|no":
                raise RuntimeError("writer not stopped or restart disabled")
        for identity in passive + [other]:
            if local_docker(["inspect", "--format", "{{.State.Running}}|{{.HostConfig.RestartPolicy.Name}}", identity]).strip() != "true|always":
                raise RuntimeError("writer shutdown changed passive or foreign container")

        # An out-of-band administrator can still start containers; the gate
        # must detect that and never claim a universal barrier.
        local_docker(["start", writers[0]])
        try:
            fence.assert_closed()
        except DockerFenceError:
            pass
        else:
            raise RuntimeError("manually restarted writer was not detected")
        print("G5 real Docker writer shutdown rehearsal passed (isolated project)")
        return 0
    finally:
        if created:
            local_docker(["rm", "-f", *created])


if __name__ == "__main__":
    raise SystemExit(main())
