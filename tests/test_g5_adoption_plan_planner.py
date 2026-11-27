from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_adoption_plan import (
    CheckoutObservation,
    CloneRestoreDeclaration,
    ContainerObservation,
    EdgeObservation,
    ExternalCopyDeclaration,
    ExternalDeclarations,
    HostInventory,
    HostObservations,
    ImageObservation,
    MetadataObservation,
    MetadataState,
    PlanStatus,
    ProxyRoute,
    TargetIdentity,
    plan_adoption,
)
from ops.g5_cutover_state import Identity, Manifest, Phase


NOW = datetime(2026, 11, 27, 17, tzinfo=timezone.utc)
SHA = "a" * 40


def valid_evidence():
    identity = TargetIdentity(
        compose_project="medievol",
        compose_sha256="b" * 64,
        network_id="c" * 64,
        volume_id="medievol_postgres-data",
        database="game_db",
        database_oid=16384,
        schema_sha256="d" * 64,
        current_release_sha=SHA,
        application_role="game_app",
        maintenance_role="game_admin",
        caddy_container_id="e" * 64,
    )
    images = (
        ImageObservation("backend", "ghcr.io/example/backend@sha256:" + "1" * 64,
                         "sha256:" + "3" * 64, SHA),
        ImageObservation("frontend", "ghcr.io/example/frontend@sha256:" + "2" * 64,
                         "sha256:" + "4" * 64, SHA),
        ImageObservation("worker", "ghcr.io/example/backend@sha256:" + "1" * 64,
                         "sha256:" + "3" * 64, SHA),
    )
    containers = (
        ContainerObservation("backend", "1" * 64, "medievol", "c" * 64, True,
                             "unless-stopped", "sha256:" + "3" * 64),
        ContainerObservation("frontend", "2" * 64, "medievol", "c" * 64, True,
                             "unless-stopped", "sha256:" + "4" * 64),
        ContainerObservation("worker", "3" * 64, "medievol", "c" * 64, True,
                             "unless-stopped", "sha256:" + "3" * 64),
        ContainerObservation("database", "4" * 64, "medievol", "c" * 64, True,
                             "unless-stopped", volume_id="medievol_postgres-data"),
        ContainerObservation("nginx", "5" * 64, "medievol", "c" * 64, True,
                             "unless-stopped"),
        ContainerObservation("caddy", "e" * 64, "medievol", "c" * 64, True,
                             "unless-stopped"),
    )
    edge = EdgeObservation(
        caddy_container_id="e" * 64,
        caddy_target_service="nginx",
        caddy_target_container_id="5" * 64,
        caddy_routes=(ProxyRoute("/", "nginx", "5" * 64),),
        nginx_container_id="5" * 64,
        nginx_routes=(
            ProxyRoute("/", "frontend", "2" * 64),
            ProxyRoute("/api/", "backend", "1" * 64),
            ProxyRoute("/socket.io/", "backend", "1" * 64),
        ),
        tls_ready=True,
    )
    legacy = MetadataObservation(MetadataState.LEGACY_MANAGED, legacy_release_sha=SHA)
    inventory = HostInventory(
        CheckoutObservation(SHA, True), identity, images, containers, legacy, edge
    )
    observations = HostObservations(
        before=inventory,
        after=inventory,
        observed_from=NOW - timedelta(seconds=10),
        observed_until=NOW - timedelta(seconds=2),
    )
    declarations = ExternalDeclarations(
        external_copy=ExternalCopyDeclaration(
            evidence_id="copy-evidence-1",
            sha256="6" * 64,
            database_oid=16384,
            schema_sha256="d" * 64,
            source_release_sha=SHA,
            observed_at=NOW - timedelta(seconds=5),
            verified=True,
        ),
        clone_restore=CloneRestoreDeclaration(
            evidence_id="restore-evidence-1",
            source_sha256="6" * 64,
            restored_schema_sha256="d" * 64,
            restored_database_oid=16384,
            clone_id="isolated-clone-1",
            clone_network_id="7" * 64,
            clone_volume_id="isolated-clone-volume",
            observed_at=NOW - timedelta(seconds=3),
            restored=True,
            isolated=True,
        ),
        capacity_available_bytes=200,
        capacity_required_bytes=100,
        capacity_observed_at=NOW - timedelta(seconds=4),
        maintenance_window_starts=NOW + timedelta(hours=1),
        maintenance_window_ends=NOW + timedelta(hours=2),
        human_authorization_recorded=True,
    )
    return observations, declarations


def plan(observations=None, declarations=None, **kwargs):
    observed, declared = valid_evidence()
    return plan_adoption(
        observations if observations is not None else observed,
        declarations if declarations is not None else declared,
        now=NOW,
        **kwargs,
    )


def replace_after(observations, **changes):
    return replace(observations, after=replace(observations.after, **changes))


def replace_both(observations, **changes):
    return replace(
        observations,
        before=replace(observations.before, **changes),
        after=replace(observations.after, **changes),
    )


def test_consistent_legacy_host_produces_only_a_conditional_no_go_plan():
    result = plan()

    assert result.status is PlanStatus.NO_GO_PLAN_ONLY
    assert result.blockers == ()
    assert len(result.steps) == 10
    assert "Caddy-to-Nginx" in result.steps[2]
    assert "durable database write barrier" in result.steps[4]
    assert "After verified rollback evidence" in result.steps[7]
    assert "verify candidate health before any public probe" in result.steps[8]
    assert result.external_declarations_are_unverified is True
    assert result.requires_human_authorization is True


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"checkout": CheckoutObservation(SHA, False)}, "clean worktree"),
        ({"images": ()}, "image evidence"),
        (
            {"images": (
                ImageObservation("backend", "ghcr.io/example/backend:latest",
                                 "sha256:" + "3" * 64, SHA),
            )},
            "immutable SHA-256 digests",
        ),
    ],
)
def test_dirty_or_incomplete_release_evidence_blocks(change, expected):
    observations, declarations = valid_evidence()
    after = replace(observations.after, **change)
    result = plan(replace(observations, after=after), declarations)
    assert any(expected in blocker for blocker in result.blockers)
    assert result.status is PlanStatus.NO_GO_PLAN_ONLY


@pytest.mark.parametrize(
    "metadata,expected",
    [
        (MetadataObservation(MetadataState.ABSENT), "absent"),
        (MetadataObservation(MetadataState.LEGACY_UNMANAGED), "no managed release identity"),
        (
            MetadataObservation(
                MetadataState.ABSENT,
                marker_operation_id="marker",
                recovery_marker_present=True,
            ),
            "contradicts an existing marker",
        ),
        (
            MetadataObservation(MetadataState.ABSENT, legacy_release_sha=SHA),
            "contradicts an existing marker",
        ),
        (
            MetadataObservation(
                MetadataState.LEGACY_MANAGED,
                legacy_release_sha=SHA,
                marker_operation_id="marker",
            ),
            "Legacy-managed metadata contradicts",
        ),
        (MetadataObservation(MetadataState.INCIDENT), "reconciliation"),
    ],
)
def test_unmanaged_or_contradictory_metadata_never_passes(metadata, expected):
    observations, declarations = valid_evidence()
    result = plan(replace_after(observations, metadata=metadata), declarations)
    assert any(expected in blocker for blocker in result.blockers)
    assert result.status is PlanStatus.NO_GO_PLAN_ONLY


def test_legacy_managed_and_terminal_g5_receipt_are_distinct_variants():
    observations, declarations = valid_evidence()
    assert plan(observations, declarations).blockers == ()

    receipt = Identity("g5-prior", "f" * 40, SHA, "8" * 64,
                       "/private/verified.dump", "medievol", "game_db")
    g5_metadata = MetadataObservation(
        MetadataState.G5_MANAGED,
        marker_operation_id="g5-prior",
        manifest=Manifest(receipt, Phase.COMMITTED_WRITERS_ALLOWED),
    )
    assert plan(replace_both(observations, metadata=g5_metadata), declarations).blockers == ()
    nonterminal = replace(g5_metadata, manifest=Manifest(receipt, Phase.PREPARED))
    result = plan(replace_after(observations, metadata=nonterminal), declarations)
    assert any("G5 terminal receipt" in blocker for blocker in result.blockers)


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("network_id", "x" * 64, "identity changed"),
        ("volume_id", "other_volume", "identity changed"),
        ("database_oid", 99999, "identity changed"),
        ("schema_sha256", "9" * 64, "identity changed"),
        ("current_release_sha", "f" * 40, "identity changed"),
    ],
)
def test_any_full_inventory_identity_drift_blocks(field, value, expected):
    observations, declarations = valid_evidence()
    identity = replace(observations.after.identity, **{field: value})
    result = plan(replace_after(observations, identity=identity), declarations)
    assert any(expected in blocker for blocker in result.blockers)


@pytest.mark.parametrize("field,value", [
    ("images", ()),
    ("containers", ()),
    ("edge", None),
    ("metadata", MetadataObservation(MetadataState.INCIDENT)),
])
def test_independent_inventory_drift_blocks_even_when_target_identity_matches(field, value):
    observations, declarations = valid_evidence()
    before = replace(observations.before, **{field: value})
    result = plan(replace(observations, before=before), declarations)
    assert any("changed during observation" in blocker for blocker in result.blockers)


@pytest.mark.parametrize(
    "inventory,expected",
    [
        (None, "Host inventory is missing"),
        (replace(valid_evidence()[0].after, identity=None), "target identity"),
    ],
)
def test_malformed_inventory_fails_closed(inventory, expected):
    observations, declarations = valid_evidence()
    result = plan(replace(observations, after=inventory), declarations)
    assert any(expected.lower() in blocker.lower() for blocker in result.blockers)
    assert result.status is PlanStatus.NO_GO_PLAN_ONLY


def test_image_digest_id_runtime_identity_and_backend_worker_parity():
    observations, declarations = valid_evidence()
    images = list(observations.after.images)
    images[2] = replace(images[2], image_id="sha256:" + "f" * 64)
    result = plan(replace_after(observations, images=tuple(images)), declarations)
    assert any("backend and worker" in blocker.lower() for blocker in result.blockers)

    images = list(observations.after.images)
    images[2] = replace(images[2], reference="ghcr.io/example/worker@sha256:" + "9" * 64)
    result = plan(replace_after(observations, images=tuple(images)), declarations)
    assert any("same immutable backend image" in blocker for blocker in result.blockers)


@pytest.mark.parametrize("service", ["migrate", "seed"])
@pytest.mark.parametrize("running,restart", [(True, "no"), (False, "unless-stopped")])
def test_one_shot_services_must_be_stopped_and_non_restartable(service, running, restart):
    observations, declarations = valid_evidence()
    container = ContainerObservation(
        service, "9" * 64, "medievol", "c" * 64, running, restart
    )
    result = plan(replace_after(observations, containers=observations.after.containers + (container,)),
                  declarations)
    assert any(f"{service} must be stopped" in blocker for blocker in result.blockers)


@pytest.mark.parametrize(
    "route,expected",
    [
        (ProxyRoute("/api/", "frontend", "2" * 64), "Nginx /api/"),
        (ProxyRoute("/socket.io/", "frontend", "2" * 64), "Nginx /socket.io/"),
        (ProxyRoute("/", "backend", "1" * 64), "Nginx /"),
        (ProxyRoute("/admin/", "backend", "1" * 64), "bypass route"),
    ],
)
def test_wrong_or_bypass_proxy_routes_block(route, expected):
    observations, declarations = valid_evidence()
    routes = tuple(route if row.path == route.path else row for row in observations.after.edge.nginx_routes)
    if route.path == "/admin/":
        routes += (route,)
    edge = replace(observations.after.edge, nginx_routes=routes)
    result = plan(replace_after(observations, edge=edge), declarations)
    assert any(expected in blocker for blocker in result.blockers)


def test_caddy_must_proxy_to_observed_nginx_and_both_containers_must_exist():
    observations, declarations = valid_evidence()
    wrong_edge = replace(observations.after.edge, caddy_target_service="backend")
    result = plan(replace_after(observations, edge=wrong_edge), declarations)
    assert any("Caddy-to-Nginx" in blocker for blocker in result.blockers)

    bypass_edge = replace(
        observations.after.edge,
        caddy_routes=observations.after.edge.caddy_routes
        + (ProxyRoute("/direct/", "backend", "1" * 64),),
    )
    result = plan(replace_after(observations, edge=bypass_edge), declarations)
    assert any("Caddy has a missing, bypassing" in blocker for blocker in result.blockers)

    containers = tuple(c for c in observations.after.containers if c.service != "nginx")
    result = plan(replace_after(observations, containers=containers), declarations)
    assert any("Nginx container evidence is missing" in blocker for blocker in result.blockers)

    containers = tuple(c for c in observations.after.containers if c.service != "caddy")
    result = plan(replace_after(observations, containers=containers), declarations)
    assert any("Caddy identity" in blocker for blocker in result.blockers)


def test_external_copy_clone_and_capacity_are_bound_and_fresh():
    observations, declarations = valid_evidence()
    bad_copy = replace(declarations.external_copy, schema_sha256="9" * 64)
    result = plan(observations, replace(declarations, external_copy=bad_copy))
    assert any("differs from the observed source identity" in blocker for blocker in result.blockers)

    bad_clone = replace(declarations.clone_restore, clone_network_id="c" * 64)
    result = plan(observations, replace(declarations, clone_restore=bad_clone))
    assert any("differs from the observed source identity" in blocker for blocker in result.blockers)

    stale = replace(declarations, capacity_observed_at=NOW - timedelta(minutes=10))
    assert any("Capacity evidence is stale" in blocker for blocker in plan(observations, stale).blockers)
    assert any("Clone-restore evidence is stale" in blocker for blocker in plan(
        observations,
        replace(declarations, clone_restore=replace(
            declarations.clone_restore, observed_at=NOW - timedelta(minutes=10)
        )),
    ).blockers)


class NoOffsetTimezone(tzinfo):
    def utcoffset(self, dt):
        return None


class BrokenTimezone(tzinfo):
    def utcoffset(self, dt):
        raise RuntimeError("untrusted tzinfo")


def test_naive_or_invalid_timezone_values_fail_closed_without_crashing():
    observations, declarations = valid_evidence()
    result = plan(replace(observations, observed_until=datetime(2026, 11, 27, 17)))
    assert any("valid timezone offset" in blocker for blocker in result.blockers)

    result = plan(
        observations,
        replace(declarations, maintenance_window_starts=NOW.replace(tzinfo=NoOffsetTimezone())),
    )
    assert any("valid offsets" in blocker for blocker in result.blockers)

    result = plan(replace(observations, observed_from=NOW.replace(tzinfo=BrokenTimezone())))
    assert any("valid timezone offset" in blocker for blocker in result.blockers)

    _, declarations = valid_evidence()
    assert plan_adoption(None, declarations, now=NOW).status is PlanStatus.NO_GO_PLAN_ONLY


def test_external_clone_schema_and_database_identity_must_match():
    observations, declarations = valid_evidence()
    clone = replace(declarations.clone_restore, restored_database_oid=999)
    assert any("differs from the observed source identity" in blocker for blocker in plan(
        observations, replace(declarations, clone_restore=clone)
    ).blockers)
    clone = replace(declarations.clone_restore, restored_schema_sha256="9" * 64)
    assert any("differs from the observed source identity" in blocker for blocker in plan(
        observations, replace(declarations, clone_restore=clone)
    ).blockers)


def test_role_split_errors_do_not_echo_credentials_or_database_urls():
    observations, declarations = valid_evidence()
    identity = replace(observations.after.identity, application_role="game_admin")
    result = plan(replace_after(observations, identity=identity), declarations)
    rendered = " ".join(result.blockers)
    assert "fail the G5 split contract" in rendered
    assert "synthetic" not in rendered
    assert "postgresql+psycopg" not in rendered
