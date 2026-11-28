import sys
from pathlib import Path

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
    _SOCKET_IO_PROBE,
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
    assert b"proxy_pass http://backend/;" in nginx
    assert b"proxy_pass http://frontend;" in nginx
    assert b"proxy_set_header Upgrade $http_upgrade;" in nginx
    assert b"listen 8081;" in frontend
    for name, (path, digest) in configs.items():
        assert read_config(path, digest) == digest
        fixed_config(name, path.read_bytes(), digest)
        assert_rejected_config(path, digest)
        assert read_config(path, digest) == digest


def test_ci_probe_programs_are_valid_python():
    compile(_APP_PROBE, "edge-http-probe", "exec")
    compile(_SOCKET_IO_PROBE, "edge-socketio-probe", "exec")


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
