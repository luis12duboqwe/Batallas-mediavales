from dataclasses import replace
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops import g5_adoption_observer as observer
from ops.g5_adoption_plan import (
    CheckoutObservation,
    ContainerObservation,
    EdgeObservation,
    HostInventory,
    ImageObservation,
    MetadataObservation,
    MetadataState,
    ProxyRoute,
    TargetIdentity,
)
from ops.g5_activation_fence import arm_cutover
from ops.g5_cutover_state import CutoverStore, Identity, Phase


SHA = "a" * 40
NOW = datetime(2026, 11, 27, tzinfo=timezone.utc)


def inventory():
    identity = TargetIdentity(
        "isolated", "b" * 64, "c" * 64, "isolated_postgres-data",
        "game_db", 16384, "d" * 64, SHA, "game_app", "game_admin",
        "e" * 64, "7345678901234567890",
    )
    images = (
        ImageObservation("backend", "ghcr.io/example/backend@sha256:" + "1" * 64,
                         "sha256:" + "3" * 64, SHA),
        ImageObservation("frontend", "ghcr.io/example/frontend@sha256:" + "2" * 64,
                         "sha256:" + "4" * 64, SHA),
        ImageObservation("worker", "ghcr.io/example/backend@sha256:" + "1" * 64,
                         "sha256:" + "3" * 64, SHA),
    )
    containers = tuple(
        ContainerObservation(service, format(i, "064x"), "isolated", "c" * 64, True,
                             "unless-stopped",
                             "sha256:" + ("3" if service in {"backend", "worker"} else "4") * 64
                             if service in {"backend", "frontend", "worker"} else None,
                             "isolated_postgres-data" if service == "database" else None)
        for i, service in enumerate(
            ("backend", "frontend", "worker", "database", "nginx", "caddy"), 1
        )
    )
    caddy_id = next(c.container_id for c in containers if c.service == "caddy")
    nginx_id = next(c.container_id for c in containers if c.service == "nginx")
    backend_id = next(c.container_id for c in containers if c.service == "backend")
    frontend_id = next(c.container_id for c in containers if c.service == "frontend")
    edge = EdgeObservation(
        caddy_id, "nginx", nginx_id, (ProxyRoute("/", "nginx", nginx_id),),
        nginx_id,
        (ProxyRoute("/", "frontend", frontend_id),
         ProxyRoute("/api/", "backend", backend_id),
         ProxyRoute("/socket.io/", "backend", backend_id)),
        False,
    )
    return HostInventory(
        CheckoutObservation(SHA, True), identity, images, containers,
        MetadataObservation(MetadataState.LEGACY_MANAGED, legacy_release_sha=SHA), edge,
    )


def partial_inventory(base=None, *, blockers=()):
    base = base or inventory()
    return observer.PartialHostInventory(
        base.checkout, base.identity, base.images, base.containers, base.metadata,
        ("/",), tuple(blockers),
    )


def test_observe_partial_takes_two_independent_snapshots(monkeypatch, tmp_path):
    seen = []

    def collect(_request, _runner):
        result = partial_inventory()
        seen.append(result)
        return result

    monkeypatch.setattr(observer, "_collect_once", collect)
    ticks = iter((NOW, NOW.replace(second=1)))
    result = observer.observe_partial(
        observer.ObserverRequest(tmp_path, tmp_path / "env", (tmp_path / "compose.yml",), "isolated"),
        runner=lambda *_args, **_kwargs: "",
        clock=lambda: next(ticks),
    )
    assert result.before == result.after
    assert result.before is not result.after
    assert seen == [result.before, result.after]
    assert result.before.caddy_routes == ("/",)
    assert not isinstance(result.before, HostInventory)


@pytest.mark.parametrize(
    "change",
    [
        {"identity": replace(inventory().identity, postgres_system_identifier="7345678901234567891")},
        {"identity": replace(inventory().identity, volume_id="other_volume")},
        {"identity": replace(inventory().identity, network_id="f" * 64)},
    ],
)
def test_observe_rejects_identity_drift_even_when_database_oid_is_unchanged(
    monkeypatch, tmp_path, change
):
    results = [partial_inventory(), replace(partial_inventory(), **change)]
    monkeypatch.setattr(observer, "_collect_once", lambda *_: results.pop(0))
    result = observer.observe_partial(
        observer.ObserverRequest(tmp_path, tmp_path / "env", (tmp_path / "compose.yml",), "isolated"),
        runner=lambda *_args, **_kwargs: "",
        clock=lambda: NOW,
    )
    assert any("drifted" in blocker for blocker in result.blockers)


def test_full_observation_raises_with_typed_partial_inventory(monkeypatch, tmp_path):
    results = [partial_inventory(), partial_inventory()]
    monkeypatch.setattr(observer, "_collect_once", lambda *_: results.pop(0))
    with pytest.raises(observer.ObservationBlocked) as error:
        observer.observe(
            observer.ObserverRequest(tmp_path, tmp_path / "env", (tmp_path / "compose.yml",), "isolated"),
            runner=lambda *_args, **_kwargs: "",
            clock=lambda: NOW,
        )
    assert isinstance(error.value.partial.before, observer.PartialHostInventory)
    assert error.value.partial.before.identity.database_oid == 16384
    assert "Nginx loaded configuration" in " ".join(error.value.partial.blockers)


def test_runner_uses_bounded_argv_and_sanitizes_command_failures():
    with pytest.raises(observer.ObservationError, match="unsupported executable"):
        observer._run(["python"], timeout=7, max_output_bytes=10)


def test_compose_fingerprint_is_deterministic_without_returning_config_values():
    config = {"services": {"database": {"environment": {"PASSWORD": "secret-value"}}}}
    labels = [{
        "com.docker.compose.project": "isolated",
        "com.docker.compose.service": "database",
        "com.docker.compose.config-hash": "a" * 64,
        "com.docker.compose.project.working_dir": "/fixture",
        "com.docker.compose.project.config_files": "/fixture/compose.yml",
        "com.docker.compose.oneoff": "False",
    }]
    assert observer._compose_fingerprint(config, labels) == observer._compose_fingerprint(
        {"services": {"database": {"environment": {
        "PASSWORD": "secret-value"
    }}}}, labels)
    assert "secret-value" not in observer._compose_fingerprint(config, labels)
    assert observer._compose_fingerprint(config, labels) != observer._compose_fingerprint(
        {"services": {"database": {"environment": {
        "PASSWORD": "different-secret"
    }}}}, labels)


def test_compose_environment_uses_effective_runtime_and_migration_urls():
    app_url = "postgresql+psycopg://" + "game_app:synthetic-app@database:5432/game_db"
    admin_url = (
        "postgresql+psycopg://" + "game_admin:admin-secret@database:5432/game_db"
    )
    config = {"services": {
        "database": {"environment": {
            "POSTGRES_DB": "game_db", "POSTGRES_USER": "game_admin",
            "POSTGRES_PASSWORD": "admin-secret",
        }},
        "backend": {"environment": {"DATABASE_URL": app_url}},
        "worker": {"environment": {"DATABASE_URL": app_url}},
        "migrate": {"environment": {"DATABASE_URL": admin_url}},
        "seed": {"environment": {"DATABASE_URL": admin_url}},
    }}
    result = observer._compose_environment(config)
    assert result["DB_URL"] == app_url
    assert result["G5_MIGRATION_DB_URL"] == admin_url
    assert result["POSTGRES_PASSWORD"] == "admin-secret"


def test_compose_environment_rejects_divergent_workers_and_one_shots():
    app = "postgresql+psycopg://" + "game_app:synthetic-app@database:5432/game_db"
    admin = "postgresql+psycopg://" + "game_admin:admin-secret@database:5432/game_db"
    config = {"services": {
        "database": {"environment": {
            "POSTGRES_DB": "game_db", "POSTGRES_USER": "game_admin",
            "POSTGRES_PASSWORD": "admin",
        }},
        "backend": {"environment": {"DATABASE_URL": app}},
        "worker": {"environment": {"DATABASE_URL":
                   "postgresql+psycopg://" + "other:worker@database:5432/game_db"}},
        "migrate": {"environment": {"DATABASE_URL": admin}},
        "seed": {"environment": {"DATABASE_URL": admin}},
    }}
    with pytest.raises(observer.ObservationError, match="URLs diverge"):
        observer._compose_environment(config)


def test_network_inventory_rejects_extra_networks_and_network_replacement():
    row = {
        "Id": "1" * 64,
        "Name": "/isolated-database-1",
        "NetworkSettings": {"Networks": {"isolated_web": {
            "NetworkID": "c" * 64, "Aliases": ["database", "isolated-database-1"],
            "IPAddress": "172.20.0.2",
        }}},
        "Config": {"Labels": {"com.docker.compose.network": "web",
                              "com.docker.compose.service": "database"}},
        "State": {"Running": True},
    }
    config = {"networks": {"web": {}}}

    def run(argv, **_kwargs):
        assert argv == ("docker", "network", "inspect", "c" * 64)
        return json.dumps([{
            "Id": "c" * 64, "Driver": "bridge",
            "Labels": {"com.docker.compose.project": "isolated",
                       "com.docker.compose.network": "web"},
            "Containers": {"1" * 64: {"IPv4Address": "172.20.0.2/16"}},
        }])

    config["services"] = {"database": {"networks": {"web": {}}}}
    assert observer._network_identity(run, [row], config, "isolated") == "c" * 64
    row["NetworkSettings"]["Networks"]["bypass"] = {"NetworkID": "f" * 64}
    with pytest.raises(observer.ObservationError, match="bypass"):
        observer._network_identity(run, [row], config, "isolated")


def test_caddy_live_route_parser_and_missing_nginx_introspection_fail_closed():
    caddy_id = "1" * 64
    caddy = {
        "apps": {"http": {"servers": {"srv0": {"routes": [{
            "match": [{"host": ["fixture.invalid"]}],
            "handle": [{"handler": "reverse_proxy",
                        "upstreams": [{"dial": "nginx:80"}]}],
        }]}}}},
    }
    assert observer._caddy_routes(caddy) == ({"path": "/", "dial": "nginx:80"},)

    def run(argv, **_kwargs):
        assert argv[-1] == "http://127.0.0.1:2019/config/"
        return json.dumps(caddy)

    with pytest.raises(observer.ObservationError, match="Nginx loaded configuration"):
        observer._runtime_routes(run, {"Id": caddy_id}, {"Id": "2" * 64}, {})

    caddy["apps"]["http"]["servers"]["srv0"]["routes"].append({
        "match": [{"path": ["/bypass/*"]}],
        "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "backend:8000"}]}],
    })
    with pytest.raises(observer.ObservationError, match="bypass"):
        observer._caddy_routes(caddy)


def test_metadata_reader_does_not_initialize_missing_state_and_flags_malformed_release(tmp_path):
    absent = observer._read_metadata(tmp_path)
    assert absent.state is MetadataState.ABSENT
    assert not (tmp_path / ".ops-state").exists()

    state = tmp_path / ".ops-state"
    state.mkdir(mode=0o700)
    lock = state / "deploy.lock"
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    release = tmp_path / ".release-sha"
    release.write_text(SHA)
    release.chmod(0o600)
    env = tmp_path / ".release.env"
    env.write_text("fixture")
    env.chmod(0o600)
    assert observer._read_metadata(tmp_path) == MetadataObservation(
        MetadataState.LEGACY_MANAGED, legacy_release_sha=SHA
    )
    release.write_text("not-a-release")
    assert observer._read_metadata(tmp_path).state is MetadataState.INCIDENT


def test_incomplete_g5_metadata_is_incident_and_does_not_create_deploy_lock(tmp_path):
    state = tmp_path / ".ops-state"
    state.mkdir()
    (state / "g5-cutover-activated").write_text("malformed")
    assert observer._read_metadata(tmp_path).state is MetadataState.INCIDENT
    assert not (state / "deploy.lock").exists()


def test_legacy_unmanaged_and_active_deploy_lock_are_fail_closed(tmp_path):
    state = tmp_path / ".ops-state"
    state.mkdir(mode=0o700)
    lock = state / "deploy.lock"
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    env = tmp_path / ".release.env"
    env.write_text("synthetic")
    env.chmod(0o600)
    assert observer._read_metadata(tmp_path).state is MetadataState.LEGACY_UNMANAGED

    fd = lock.open("r")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert observer._read_metadata(tmp_path).state is MetadataState.INCIDENT
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


def test_valid_terminal_g5_metadata_is_reused_without_writes(tmp_path):
    host = tmp_path / "host"
    host.mkdir(mode=0o700)
    (host / ".ops-state").mkdir(mode=0o700)
    backup_root = tmp_path / "backups"
    backup_root.mkdir(mode=0o700)
    archive = backup_root / "archive.dump"
    archive.write_bytes(b"synthetic backup")
    archive.chmod(0o600)
    identity = Identity(
        "observer-test", "1" * 40, SHA, hashlib.sha256(archive.read_bytes()).hexdigest(),
        str(archive), "isolated", "game_db",
    )
    with arm_cutover(str(host), identity.operation_id):
        store = CutoverStore(str(host))
        store.prepare(identity, str(backup_root))
        store.advance(identity, Phase.PREPARED, Phase.MIGRATING)
        store.advance(identity, Phase.MIGRATING, Phase.VERIFIED_READONLY)
        store.advance(identity, Phase.VERIFIED_READONLY, Phase.COMMITTED_WRITERS_ALLOWED)
    before = sorted(path.name for path in (host / ".ops-state").iterdir())
    metadata = observer._read_metadata(host)
    assert metadata.state is MetadataState.G5_MANAGED
    assert metadata.marker_operation_id == identity.operation_id
    assert metadata.manifest.phase is Phase.COMMITTED_WRITERS_ALLOWED
    assert sorted(path.name for path in (host / ".ops-state").iterdir()) == before


def test_pg_observation_hashes_catalog_only_and_redacts_authentication(monkeypatch, tmp_path):
    db = {
        "Id": "1" * 64, "Config": {"Labels": {"com.docker.compose.service": "database"}},
        "NetworkSettings": {"Networks": {"fixture_web": {
            "IPAddress": "172.20.0.2",
        }}},
    }
    app_row = {"Id": "2" * 64, "Config": {"Labels": {"com.docker.compose.service": "backend"}}}
    worker_row = {"Id": "3" * 64, "Config": {"Labels": {"com.docker.compose.service": "worker"}}}
    values = {
        "POSTGRES_USER": "game_admin", "POSTGRES_DB": "game_db",
        "POSTGRES_PASSWORD": "admin-secret",
        "DB_URL": (
            "postgresql+psycopg://" "game_app:app-secret" "@database:5432/game_db"
        ),
        "G5_MIGRATION_DB_URL": (
            "postgresql+psycopg://" "game_admin:admin-secret" "@database:5432/game_db"
        ),
    }
    calls = []

    def run(argv, **_kwargs):
        calls.append(argv)
        if "psql" in argv:
            assert "SET TRANSACTION READ ONLY" in argv[-1]
            return json.dumps([
                "game_admin", "game_db", 16384, "7345678901234567890",
                "150004", True, "on",
            ])
        if "python" in argv:
            assert "app-secret" not in " ".join(argv)
            return json.dumps([
                "game_app", "game_app", "game_db", 16384, "172.20.0.2",
                False, False, "on",
            ])
        assert "pg_dump" in argv and "--schema-only" in argv
        return "CREATE TABLE synthetic_schema_only (id integer);\n"

    result = observer._pg_snapshot(run, [db, app_row, worker_row], values)
    assert result[:2] == ("game_db", 16384)
    assert result[2] == observer.hashlib.sha256(
        b"CREATE TABLE synthetic_schema_only (id integer);\n"
    ).hexdigest()
    assert result[3:] == ("7345678901234567890", "game_app")
    assert all("secret" not in repr(call) for call in calls)


def test_pg_oid_without_real_maintenance_identity_fails_closed(tmp_path):
    db = {
        "Id": "1" * 64, "Config": {"Labels": {"com.docker.compose.service": "database"}},
        "NetworkSettings": {"Networks": {"fixture_web": {"IPAddress": "172.20.0.2"}}},
    }
    app_row = {"Id": "2" * 64, "Config": {"Labels": {"com.docker.compose.service": "backend"}}}
    values = {"POSTGRES_USER": "game_admin", "POSTGRES_DB": "game_db"}

    def run(_argv, **_kwargs):
        return json.dumps([
            "other_admin", "game_db", 16384, "7345678901234567890",
            "150004", True, "on",
        ])

    with pytest.raises(observer.ObservationError, match="maintenance identity"):
        observer._pg_snapshot(run, [db, app_row], values)


class ComposeFixtureRunner:
    """Deterministic command fixture; it never starts Docker or opens a socket."""

    def __init__(
        self, checkout, compose, *, drift_system_id=False, drift_config=False,
        drift_volume=False, drift_network=False, wrong_runtime_environment=False,
    ):
        self.checkout = checkout
        self.compose = compose
        self.observations = 0
        self.drift_system_id = drift_system_id
        self.drift_config = drift_config
        self.drift_volume = drift_volume
        self.drift_network = drift_network
        self.wrong_runtime_environment = wrong_runtime_environment
        self.network_id = "c" * 64
        self.ids = {service: format(index, "064x") for index, service in enumerate(
            ("backend", "frontend", "worker", "database", "nginx", "caddy", "migrate", "seed"), 1
        )}
        self.image_ids = {
            "backend": "sha256:" + "3" * 64,
            "worker": "sha256:" + "3" * 64,
            "frontend": "sha256:" + "4" * 64,
        }
        self.refs = {
            "backend": "ghcr.io/example/backend@sha256:" + "1" * 64,
            "worker": "ghcr.io/example/backend@sha256:" + "1" * 64,
            "frontend": "ghcr.io/example/frontend@sha256:" + "2" * 64,
        }
        self.config = self._config()
        self.rows = self._rows()

    def _config(self):
        app_url = (
            "postgresql+psycopg://" "game_app:app-secret" "@database:5432/game_db"
        )
        admin_url = (
            "postgresql+psycopg://" "game_admin:admin-secret" "@database:5432/game_db"
        )
        services = {}
        for service in self.ids:
            image = self.refs.get(service, f"fixture/{service}:test")
            spec = {"image": image, "restart": "unless-stopped"}
            if service in {"migrate", "seed"}:
                spec["restart"] = "no"
            if service == "database":
                spec.update(environment={
                    "POSTGRES_DB": "game_db", "POSTGRES_USER": "game_admin",
                    "POSTGRES_PASSWORD": "admin-secret",
                })
                spec["volumes"] = [{
                    "type": "volume", "source": "postgres-data",
                    "target": "/var/lib/postgresql/data",
                }]
            elif service in {"backend", "worker"}:
                spec["environment"] = {"DATABASE_URL": app_url}
            elif service in {"migrate", "seed"}:
                spec["environment"] = {"DATABASE_URL": admin_url}
            elif service == "nginx":
                spec["volumes"] = [{
                    "type": "bind", "source": str(self.checkout / "nginx.g5.conf"),
                    "target": "/etc/nginx/nginx.conf", "read_only": True,
                }]
            elif service == "caddy":
                spec["volumes"] = [
                    {"type": "bind", "source": str(self.checkout / "Caddyfile"),
                     "target": "/etc/caddy/Caddyfile", "read_only": True},
                    {"type": "volume", "source": "caddy-data", "target": "/data"},
                    {"type": "volume", "source": "caddy-config", "target": "/config"},
                ]
            spec.setdefault("networks", {"web": {}})
            services[service] = spec
        return {
            "name": "isolated", "services": services,
            "networks": {"web": {}},
            "volumes": {"postgres-data": {}, "caddy-data": {}, "caddy-config": {}},
        }

    def _rows(self):
        rows = []
        configs = self.config["services"]
        for service, identity in self.ids.items():
            image_id = self.image_ids.get(service, "sha256:" + format(
                int(identity, 16), "064x"
            )[-64:])
            if service in {"backend", "worker", "frontend"}:
                image_id = self.image_ids[service]
            labels = {
                "com.docker.compose.project": "isolated",
                "com.docker.compose.service": service,
                "com.docker.compose.config-hash": format(len(service), "064x"),
                "com.docker.compose.project.working_dir": str(self.checkout),
                "com.docker.compose.project.config_files": str(self.compose),
                "com.docker.compose.oneoff": "True" if service in {"migrate", "seed"} else "False",
                "com.docker.compose.network": "web",
            }
            mounts = []
            for mount in configs[service].get("volumes", []):
                if mount["type"] == "volume":
                    volume_spec = self.config["volumes"].get(mount["source"], {})
                    source = volume_spec.get("name") or f"isolated_{mount['source']}"
                    name = source
                    source = f"/var/lib/docker/volumes/{name}/_data"
                else:
                    source = mount["source"]
                    name = None
                mounts.append({
                    "Type": mount["type"], "Name": name, "Source": source,
                    "Destination": mount["target"], "RW": not mount.get("read_only", False),
                })
            running = service not in {"migrate", "seed"}
            network_settings = {"Ports": {}, "Networks": {}}
            if running:
                network_settings["Networks"] = {
                    "isolated_web": {
                        "NetworkID": self.network_id, "Aliases": [service],
                        "IPAddress": f"172.20.0.{int(identity, 16)}",
                    },
                }
            rows.append({
                "Id": identity, "Image": image_id,
                "Config": {
                    "Image": configs[service]["image"], "Labels": labels,
                    "Entrypoint": None, "Cmd": [],
                    "Env": [f"{key}={value}" for key, value in
                            configs[service].get("environment", {}).items()],
                },
                "State": {"Running": running},
                "HostConfig": {
                    "PortBindings": {},
                    "Privileged": False, "CapAdd": [], "CapDrop": [], "Devices": [],
                    "SecurityOpt": [], "ReadonlyRootfs": False, "UsernsMode": "",
                    "NetworkMode": "isolated_web", "PidMode": "", "IpcMode": "private",
                    "RestartPolicy": {"Name": "no" if service in {"migrate", "seed"}
                                      else "unless-stopped", "MaximumRetryCount": 0},
                },
                "NetworkSettings": network_settings,
                "Mounts": mounts,
            })
        if self.wrong_runtime_environment:
            backend = next(row for row in rows
                           if row["Config"]["Labels"]["com.docker.compose.service"] == "backend")
            backend["Config"]["Env"] = ["DATABASE_URL=private-runtime-value"]
        return rows

    def __call__(self, argv, **_kwargs):
        if argv[:5] == ("git", "-C", str(self.checkout), "rev-parse", "--verify"):
            return SHA + "\n"
        if argv[:4] == ("git", "-C", str(self.checkout), "status"):
            return ""
        if "compose" in argv and argv[-3:] == ("config", "--format", "json"):
            self.observations += 1
            if self.observations == 2:
                if self.drift_config:
                    self.config["x-observed-drift"] = True
                if self.drift_volume:
                    self.config["volumes"]["postgres-data"]["name"] = "isolated_data_replaced"
                if self.drift_network:
                    self.network_id = "d" * 64
                self.rows = self._rows()
            return json.dumps(self.config)
        if "compose" in argv and len(argv) >= 2 and argv[-2] == "--hash":
            service = argv[-1]
            return format(len(service), "064x") + "\n"
        if argv[:3] == ("docker", "ps", "-a"):
            return "\n".join(json.dumps({"ID": row["Id"]}) for row in self.rows)
        if argv[:3] == ("docker", "inspect", "--type"):
            return json.dumps(self.rows)
        if argv[:3] == ("docker", "network", "inspect"):
            running = [row for row in self.rows if row["State"]["Running"]]
            return json.dumps([{
                "Id": self.network_id, "Driver": "bridge",
                "Labels": {"com.docker.compose.project": "isolated",
                           "com.docker.compose.network": "web"},
                "Containers": {
                    row["Id"]: {"IPv4Address": (
                        row["NetworkSettings"]["Networks"]["isolated_web"]["IPAddress"] + "/16"
                    )}
                    for row in running
                },
            }])
        if argv[:3] == ("docker", "volume", "inspect"):
            name = argv[-1]
            volume = next(
                source for source, spec in self.config["volumes"].items()
                if (spec.get("name") or f"isolated_{source}") == name
            )
            return json.dumps([{
                "Name": name, "Driver": "local",
                "Mountpoint": f"/var/lib/docker/volumes/{name}/_data",
                "Labels": {"com.docker.compose.project": "isolated",
                           "com.docker.compose.volume": volume},
            }])
        if argv[:3] == ("docker", "image", "inspect"):
            image_id = argv[-1]
            service = next(
                (name for name, value in self.image_ids.items() if value == image_id), None
            )
            config = {
                "Labels": {"org.opencontainers.image.revision": SHA},
                "Env": [], "Entrypoint": None, "Cmd": [],
            }
            if service is None:
                return json.dumps([{"Id": image_id, "RepoDigests": [], "Config": config}])
            return json.dumps([{
                "Id": image_id, "RepoDigests": [self.refs[service]], "Config": config,
            }])
        if "psql" in argv:
            system_id = "7345678901234567890"
            if self.drift_system_id and self.observations >= 2:
                system_id = "7345678901234567891"
            return json.dumps(["game_admin", "game_db", 16384, system_id, "150004", True, "on"])
        if "python" in argv:
            return json.dumps([
                "game_app", "game_app", "game_db", 16384,
                "172.20.0.4", False, False, "on",
            ])
        if "pg_dump" in argv:
            return "CREATE TABLE synthetic_schema_only (id integer);\n"
        if argv[-1] == "http://127.0.0.1:2019/config/":
            return json.dumps({"apps": {"http": {"servers": {"srv0": {"routes": [{
                "match": [{"host": ["fixture.invalid"]}],
                "handle": [{"handler": "reverse_proxy",
                            "upstreams": [{"dial": "nginx:80"}]}],
            }]}}}}})
        raise AssertionError(f"unhandled fixture command: {argv}")


@pytest.fixture
def compose_fixture(tmp_path):
    (tmp_path / "compose.yml").write_text("fixture")
    (tmp_path / "env").write_text("fixture")
    (tmp_path / "nginx.g5.conf").write_text("fixture")
    (tmp_path / "Caddyfile").write_text("fixture")
    (tmp_path / ".release-sha").write_text(SHA)
    (tmp_path / ".release-sha").chmod(0o600)
    app_url = "postgresql+psycopg://" + "game_app:app-secret@database:5432/game_db"
    admin_url = (
        "postgresql+psycopg://" + "game_admin:admin-secret@database:5432/game_db"
    )
    (tmp_path / ".release.env").write_text(
        "POSTGRES_DB=game_db\n"
        "POSTGRES_USER=game_admin\n"
        "POSTGRES_PASSWORD=admin-secret\n"
        f"DB_URL={app_url}\n"
        f"G5_MIGRATION_DB_URL={admin_url}\n"
        "BACKEND_IMAGE=ghcr.io/example/backend@sha256:" + "1" * 64 + "\n"
        "FRONTEND_IMAGE=ghcr.io/example/frontend@sha256:" + "2" * 64 + "\n"
    )
    (tmp_path / ".release.env").chmod(0o600)
    state = tmp_path / ".ops-state"
    state.mkdir(mode=0o700)
    (state / "deploy.lock").touch(mode=0o600)
    (state / "deploy.lock").chmod(0o600)
    request = observer.ObserverRequest(
        tmp_path, tmp_path / "env", (tmp_path / "compose.yml",), "isolated"
    )
    return request, ComposeFixtureRunner(tmp_path, tmp_path / "compose.yml")


def test_synthetic_compose_fixture_exercises_inventory_assembly(monkeypatch, compose_fixture):
    request, runner = compose_fixture
    monkeypatch.setattr(observer, "_caddy_runtime_routes", lambda *_args: ("/",))
    result = observer.observe_partial(request, runner=runner, clock=lambda: NOW)
    assert result.before == result.after
    assert {row.service for row in result.before.containers} == set(runner.ids)
    assert result.before.identity.postgres_system_identifier == "7345678901234567890"
    assert result.before.identity.database_oid == 16384
    assert len(result.before.images) == 3
    assert result.before.caddy_routes == ("/",)
    assert not isinstance(result.before, HostInventory)
    assert result.before.metadata.state is MetadataState.LEGACY_MANAGED
    assert any("Nginx loaded configuration" in blocker for blocker in result.blockers)


def test_synthetic_compose_fixture_exercises_cluster_drift(monkeypatch, compose_fixture):
    request, _ = compose_fixture
    runner = ComposeFixtureRunner(
        request.checkout, request.compose_files[0], drift_system_id=True
    )
    monkeypatch.setattr(observer, "_caddy_runtime_routes", lambda *_args: ("/",))
    result = observer.observe_partial(request, runner=runner, clock=lambda: NOW)
    assert any("drifted" in blocker for blocker in result.blockers)


def test_effective_compose_rejects_unexpected_environment_mount_and_commands(compose_fixture):
    _, runner = compose_fixture
    observer._validate_service_configuration(runner.config)

    config = json.loads(json.dumps(runner.config))
    config["services"]["backend"]["environment"]["DOCKER_HOST"] = "tcp://example:2375"
    with pytest.raises(observer.ObservationError, match="environment key"):
        observer._validate_service_configuration(config)

    config = json.loads(json.dumps(runner.config))
    config["services"]["backend"]["volumes"] = [{
        "type": "bind", "source": "/", "target": "/host"
    }]
    with pytest.raises(observer.ObservationError, match="mount"):
        observer._validate_service_configuration(config)

    config = json.loads(json.dumps(runner.config))
    config["services"]["worker"]["command"] = ["sh", "-c", "unexpected"]
    with pytest.raises(observer.ObservationError, match="unexpected command"):
        observer._validate_service_configuration(config)


@pytest.mark.parametrize(
    "options,expected",
    [
        ({"drift_config": True}, "drifted"),
        ({"drift_volume": True}, "project-local"),
        ({"drift_network": True}, "drifted"),
        ({"wrong_runtime_environment": True}, "runtime environment"),
    ],
)
def test_compose_fixture_rejects_configuration_mount_and_network_drift(
    monkeypatch, compose_fixture, options, expected
):
    request, _ = compose_fixture
    runner = ComposeFixtureRunner(request.checkout, request.compose_files[0], **options)
    monkeypatch.setattr(observer, "_caddy_runtime_routes", lambda *_args: ("/",))
    with pytest.raises(observer.ObservationError, match=expected):
        observer.observe(request, runner=runner, clock=lambda: NOW)
