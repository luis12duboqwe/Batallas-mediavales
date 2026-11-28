import sys
from pathlib import Path
import subprocess

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_edge_provenance import (
    ContainerContract,
    ProvenanceError,
    fixed_config,
    legacy_host_observation,
    read_config,
    sha256,
    verify_container,
    verify_network,
)
from ops.ci_g5_edge_provenance import (
    _APP_PROBE,
    _CLOSED_GATE_PROBE,
    _ROUTE_DEVIATION_PROBE,
    _SOCKET_IO_PROBE,
    FixtureError,
    _validate_ci_context,
    _verify_synced_pull_request,
    assert_rejected_config,
    config_bundle,
)


FIXTURE = "bm-g5-edge-provenance-fixture"
CONTAINER_ID = "a" * 64
IMAGE_ID = "sha256:" + "b" * 64
NETWORK_ID = "c" * 64
CONFIG_BYTES = b"events { worker_connections 128; }\n"


def fixture():
    contract = ContainerContract(
        service="nginx", container_id=CONTAINER_ID, image_id=IMAGE_ID,
        network_name=FIXTURE, network_id=NETWORK_ID, alias="nginx",
        command=("nginx", "-g", "daemon off; pid /tmp/nginx.pid;"),
        uid=101,
        bind_mounts=(("/tmp/nginx.conf", "/etc/nginx/nginx.conf"),),
        tmpfs_options=(("/tmp", "rw,noexec,nosuid,size=32m,uid=101,gid=101,mode=700"),),
    )
    row = {
        "Id": CONTAINER_ID,
        "Image": IMAGE_ID,
        "Path": "nginx",
        "Args": ["-g", "daemon off; pid /tmp/nginx.pid;"],
        "Config": {"User": "101:101", "Labels": {
            "medievol.g5.edge-fixture": FIXTURE,
            "com.docker.compose.project": FIXTURE,
            "com.docker.compose.service": "nginx",
        }},
        "State": {"Running": True, "Paused": False},
        "HostConfig": {
            "Privileged": False, "ReadonlyRootfs": True, "CapAdd": [],
            "CapDrop": ["ALL"], "RestartPolicy": {"Name": "no"},
            "SecurityOpt": ["no-new-privileges:true"],
            "PortBindings": {}, "PublishAllPorts": False, "NetworkMode": FIXTURE,
            "Memory": 512 * 1024 * 1024, "NanoCpus": 1_000_000_000,
            "PidsLimit": 64,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=32m,uid=101,gid=101,mode=700"},
        },
        "NetworkSettings": {"Networks": {
            FIXTURE: {"NetworkID": NETWORK_ID, "Aliases": ["nginx", CONTAINER_ID]},
        }},
        "Mounts": [
            {"Type": "bind", "Source": "/tmp/nginx.conf",
             "Destination": "/etc/nginx/nginx.conf", "RW": False},
            {"Type": "tmpfs", "Destination": "/tmp", "RW": True},
        ],
    }
    cmdline = b"nginx\0-g\0daemon off; pid /tmp/nginx.pid;\0"
    status = "Name:\tnginx\nUid:\t101\t101\t101\t101\n"
    return contract, row, cmdline, status


def test_controlled_container_identity_is_accepted():
    contract, row, cmdline, status = fixture()
    verify_container(row, contract, cmdline, status)


@pytest.mark.parametrize(
    "change",
    [
        "container-replaced", "image-replaced", "wrong-command", "wrong-uid",
        "paused", "not-running", "privileged", "writable-root", "extra-capability",
        "capabilities-not-dropped", "restart-policy", "published-port",
        "wrong-network", "alias-drift", "writable-bind", "extra-bind",
        "extra-tmpfs", "missing-tmpfs", "writable-security", "unbounded-resources",
    ],
)
def test_container_runtime_drift_fails_closed(change):
    contract, row, cmdline, status = fixture()
    if change == "container-replaced":
        row["Id"] = "d" * 64
    elif change == "image-replaced":
        row["Image"] = "sha256:" + "e" * 64
    elif change == "wrong-command":
        row["Args"] = ["-s", "reload"]
    elif change == "wrong-uid":
        status = "Name:\tnginx\nUid:\t0\t0\t0\t0\n"
    elif change == "paused":
        row["State"]["Paused"] = True
    elif change == "not-running":
        row["State"]["Running"] = False
    elif change == "privileged":
        row["HostConfig"]["Privileged"] = True
    elif change == "writable-root":
        row["HostConfig"]["ReadonlyRootfs"] = False
    elif change == "extra-capability":
        row["HostConfig"]["CapAdd"] = ["SYS_ADMIN"]
    elif change == "capabilities-not-dropped":
        row["HostConfig"]["CapDrop"] = []
    elif change == "restart-policy":
        row["HostConfig"]["RestartPolicy"]["Name"] = "always"
    elif change == "published-port":
        row["HostConfig"]["PortBindings"] = {"8080/tcp": [{"HostPort": "8080"}]}
    elif change == "wrong-network":
        row["NetworkSettings"]["Networks"][FIXTURE]["NetworkID"] = "f" * 64
    elif change == "alias-drift":
        row["NetworkSettings"]["Networks"][FIXTURE]["Aliases"] = ["other"]
    elif change == "writable-bind":
        row["Mounts"][0]["RW"] = True
    elif change == "extra-bind":
        row["Mounts"].append({
            "Type": "bind", "Source": "/host", "Destination": "/untrusted", "RW": False,
        })
    elif change == "extra-tmpfs":
        row["Mounts"].append({"Type": "tmpfs", "Destination": "/unplanned", "RW": True})
        row["HostConfig"]["Tmpfs"]["/unplanned"] = "rw"
    elif change == "missing-tmpfs":
        row["Mounts"] = row["Mounts"][:-1]
    elif change == "writable-security":
        row["HostConfig"]["SecurityOpt"] = []
    elif change == "unbounded-resources":
        row["HostConfig"]["Memory"] = 0

    with pytest.raises(ProvenanceError):
        verify_container(row, contract, cmdline, status)


def test_config_hash_and_unpinned_include_guards(tmp_path):
    content = b"server { listen 8080; }\n"
    digest = sha256(content)
    path = tmp_path / "nginx.conf"
    path.write_bytes(content)
    path.chmod(0o444)
    assert fixed_config("nginx.conf", content, digest) == digest
    assert read_config(path, digest) == digest

    with pytest.raises(ProvenanceError, match="content changed"):
        fixed_config("nginx.conf", content + b"# altered\n", digest)
    for source in (b"include /etc/nginx/*.conf;\n", b"import unpinned.caddy\n"):
        with pytest.raises(ProvenanceError, match="include or import"):
            fixed_config("Caddyfile", source, sha256(source))


def test_ci_config_bundle_is_derived_and_routes_are_pinned(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    configs = config_bundle(repo, tmp_path)
    caddy = configs["Caddyfile"][0].read_bytes()
    nginx = configs["nginx.conf"][0].read_bytes()
    frontend = configs["frontend.conf"][0].read_bytes()
    assert b"admin off" in caddy
    assert b"reverse_proxy nginx:8080" in caddy
    assert b"listen 8080;" in nginx
    assert b"proxy_pass http://backend;" in nginx
    assert b"proxy_pass http://frontend;" in nginx
    assert b"auth_request /_edge_maintenance_check;" in nginx
    assert b"proxy_set_header Upgrade $http_upgrade;" in nginx
    assert b"listen 8081;" in frontend
    assert b"server frontend:8081;" in nginx
    for name, (path, digest) in configs.items():
        assert read_config(path, digest) == digest
        fixed_config(name, path.read_bytes(), digest)
        assert_rejected_config(path, digest)
        assert read_config(path, digest) == digest


def test_ci_probe_programs_are_valid_python():
    compile(_APP_PROBE, "edge-http-probe", "exec")
    compile(_CLOSED_GATE_PROBE, "edge-closed-gate-probe", "exec")
    compile(_ROUTE_DEVIATION_PROBE, "edge-route-deviation-probe", "exec")
    compile(_SOCKET_IO_PROBE, "edge-socketio-probe", "exec")


def trusted_ci_context():
    return {
        "GITHUB_ACTIONS": "true",
        "CI": "true",
        "GITHUB_REPOSITORY": "luis12duboqwe/Batallas-mediavales",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_EVENT_NAME": "pull_request",
        "G5_EDGE_PROVENANCE_PR_OPT_IN": "true",
    }


def trusted_pr_payload():
    repository = "luis12duboqwe/Batallas-mediavales"
    return {
        "pull_request": {
            "number": 123,
            "state": "open",
            "draft": False,
            "author_association": "COLLABORATOR",
            "head": {
                "repo": {"full_name": repository, "fork": False},
                "ref": "copilot/g5-edge",
                "sha": "a" * 40,
            },
            "base": {
                "repo": {"full_name": repository, "fork": False},
                "ref": "main",
                "sha": "b" * 40,
            },
        },
    }


def test_hosted_pr_guard_requires_explicit_opt_in_and_trusted_same_repo():
    event = trusted_pr_payload()
    assert _validate_ci_context(trusted_ci_context(), event) == event["pull_request"]
    assert _validate_ci_context({
        **trusted_ci_context(), "GITHUB_EVENT_NAME": "push",
    }) is None

    for env in (
        {**trusted_ci_context(), "G5_EDGE_PROVENANCE_PR_OPT_IN": "false"},
        {**trusted_ci_context(), "RUNNER_ENVIRONMENT": "self-hosted"},
        {**trusted_ci_context(), "GITHUB_REPOSITORY": "attacker/fork"},
        {**trusted_ci_context(), "GITHUB_EVENT_NAME": "pull_request_target"},
    ):
        with pytest.raises(FixtureError):
            _validate_ci_context(env, event)


@pytest.mark.parametrize(
    "change",
    ["fork", "other-repo", "untrusted-author", "draft", "closed", "invalid-sha", "missing-base"],
)
def test_hosted_pr_guard_rejects_untrusted_or_unverifiable_event(change):
    event = trusted_pr_payload()
    pr = event["pull_request"]
    if change == "fork":
        pr["head"]["repo"]["fork"] = True
    elif change == "other-repo":
        pr["head"]["repo"]["full_name"] = "attacker/Batallas-mediavales"
    elif change == "untrusted-author":
        pr["author_association"] = "CONTRIBUTOR"
    elif change == "draft":
        pr["draft"] = True
    elif change == "closed":
        pr["state"] = "closed"
    elif change == "invalid-sha":
        pr["head"]["sha"] = "not-a-commit"
    else:
        pr["base"] = None

    with pytest.raises(FixtureError):
        _validate_ci_context(trusted_ci_context(), event)


def test_pr_sync_check_requires_the_exact_base_to_be_in_pr_head(tmp_path):
    remote = tmp_path / "origin.git"
    work = tmp_path / "work"
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(work), *args], text=True).strip()

    git("config", "user.email", "ci@example.invalid")
    git("config", "user.name", "CI fixture")
    (work / "tracked").write_text("base\n")
    git("add", "tracked")
    git("commit", "-m", "base")
    base_sha = git("rev-parse", "HEAD")
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "main")
    git("checkout", "-b", "pr")
    (work / "tracked").write_text("pr\n")
    git("commit", "-am", "pr change")
    head_sha = git("rev-parse", "HEAD")
    git("push", "origin", "pr:refs/pull/42/head")
    subprocess.run(["git", "clone", str(remote), str(checkout)], check=True, capture_output=True)

    pull_request = {
        "number": 42,
        "head": {"ref": "pr", "sha": head_sha},
        "base": {"ref": "main", "sha": base_sha},
    }
    _verify_synced_pull_request(checkout, pull_request)

    git("checkout", "main")
    (work / "tracked").write_text("new base\n")
    git("commit", "-am", "new base")
    new_base_sha = git("rev-parse", "HEAD")
    git("push", "origin", "main")
    pull_request["base"]["sha"] = new_base_sha
    with pytest.raises(FixtureError, match="exact current base"):
        _verify_synced_pull_request(checkout, pull_request)


def test_config_reader_rejects_symlink_and_writable_files(tmp_path):
    target = tmp_path / "target"
    target.write_bytes(CONFIG_BYTES)
    target.chmod(0o444)
    link = tmp_path / "nginx.conf"
    link.symlink_to(target)
    with pytest.raises(ProvenanceError):
        read_config(link, sha256(CONFIG_BYTES))

    link.unlink()
    link.write_bytes(CONFIG_BYTES)
    link.chmod(0o664)
    with pytest.raises(ProvenanceError):
        read_config(link, sha256(CONFIG_BYTES))


def test_network_must_be_internal_and_content_identified():
    row = {
        "Id": NETWORK_ID, "Name": FIXTURE, "Driver": "bridge",
        "Internal": True, "EnableIPv6": False, "Options": {},
        "Labels": {"medievol.g5.edge-fixture": FIXTURE},
    }
    verify_network(row, NETWORK_ID, FIXTURE)
    for changed in (
        row | {"Internal": False},
        row | {"Driver": "overlay"},
        row | {"Id": "f" * 64},
        row | {"Labels": {}},
        row | {"EnableIPv6": True},
    ):
        with pytest.raises(ProvenanceError):
            verify_network(changed, NETWORK_ID, FIXTURE)
    with pytest.raises(ProvenanceError):
        verify_network(row | {"Containers": {"d" * 64: {}}}, NETWORK_ID, FIXTURE,
                       {CONTAINER_ID})


def test_legacy_observation_is_never_configuration_or_bypass_proof():
    observation = legacy_host_observation(
        container_id=CONTAINER_ID, image_ref="nginx:mutable", probe_results=(200, 101),
    )
    assert observation["kind"] == "legacy-host-observation"
    assert observation["status"] == "inconclusive"
    assert observation["proves_loaded_configuration"] is False
    assert observation["proves_absence_of_bypass"] is False
