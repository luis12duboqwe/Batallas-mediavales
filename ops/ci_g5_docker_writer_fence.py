"""Real Docker G5 writer-stop rehearsal; GitHub CI only, no live deployment."""
from __future__ import annotations

import json
import os
import re
import sys
from uuid import uuid4

from ops.g5_docker_writer_fence import DockerWriterFence, DockerFenceError, local_docker


def fixture_ids(fixture: str, run=local_docker) -> list[str]:
    if not re.fullmatch(r"bm-g5-writer-[0-9a-f]{32}", fixture):
        raise RuntimeError("invalid CI fixture identity")
    ids = run(["ps", "--all", "--no-trunc", "--filter",
               "label=medievol.g5.fixture=" + fixture, "--format", "{{.ID}}"]).splitlines()
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[0-9a-f]{64}", i) for i in ids):
        raise RuntimeError("invalid CI fixture container inventory")
    return ids


def cleanup_fixture(fixture: str, run=local_docker) -> None:
    # The fixture label is assigned BEFORE creation; discovery includes a
    # container created by the daemon even if the client lost its response.
    ids = fixture_ids(fixture, run)
    volumes = set()
    for identity in ids:
        mounts = json.loads(run(["inspect", "--format", "{{json .Mounts}}", identity]))
        for mount in mounts:
            if mount.get("Type") == "volume":
                name = mount.get("Name")
                if not isinstance(name, str) or not name:
                    raise RuntimeError("invalid disposable volume identity")
                volumes.add(name)
    if ids:
        run(["rm", "--force", "--volumes", *ids])
    if fixture_ids(fixture, run):
        raise RuntimeError("CI fixture containers survived cleanup")
    if volumes.intersection(run(["volume", "ls", "--quiet"]).splitlines()):
        raise RuntimeError("CI fixture anonymous volumes survived cleanup")


def create(fixture, service, *, target_project=None, run=local_docker):
    project = target_project or fixture
    return run([
        "run", "-d", "--network", "none", "--restart", "always",
        "--label", "medievol.g5.fixture=" + fixture,
        "--label", "com.docker.compose.project=" + project,
        "--label", "com.docker.compose.service=" + service,
        "--entrypoint", "/bin/sh", "postgres:15-alpine",
        "-c", "exec sleep 300",
    ]).strip()


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
        print("CI-only isolated Docker writer shutdown rehearsal", file=sys.stderr)
        return 2
    project = "bm-g5-writer-" + uuid4().hex

    try:
        passive = [create(project, "database"), create(project, "nginx")]
        writers = [create(project, s) for s in ("backend", "backend", "worker", "migrate", "seed")]
        local_docker(["stop", "--time", "1", writers[-1]])
        other = create(project, "worker", target_project=project + "-foreign")

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

        local_docker(["start", writers[0]])
        try:
            fence.assert_closed()
        except DockerFenceError:
            pass
        else:
            raise RuntimeError("manually restarted writer was not detected")
    finally:
        cleanup_fixture(project)

    # Real daemon-side creation with an intentionally lost client response.
    # No returned ID reaches the caller; label discovery must clean it.
    failed = "bm-g5-writer-" + uuid4().hex

    def lost_response(args):
        local_docker(args)
        raise DockerFenceError("injected lost create response")

    try:
        try:
            create(failed, "worker", run=lost_response)
        except DockerFenceError:
            if len(fixture_ids(failed)) != 1:
                raise RuntimeError("lost-response fixture was not created")
        else:
            raise RuntimeError("lost-response injection did not fire")
    finally:
        cleanup_fixture(failed)
    print("G5 real Docker writer shutdown and cleanup rehearsal passed (isolated projects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
