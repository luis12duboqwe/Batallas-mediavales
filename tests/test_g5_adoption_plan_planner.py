from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_adoption_plan import (
    CheckoutObservation,
    ContainerObservation,
    CloneRestoreDeclaration,
    EdgeObservation,
    ExternalCopyDeclaration,
    ExternalDeclarations,
    HostObservations,
    ImageObservation,
    MetadataObservation,
    MetadataState,
    PlanStatus,
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
        volume_id="production-volume",
        database="game_db",
        database_oid=16384,
        schema_sha256="d" * 64,
        current_release_sha=SHA,
        application_role="game_app",
        maintenance_role="game_admin",
        caddy_container_id="e" * 64,
    )
    images = tuple(
        ImageObservation(
            service=service,
            reference=f"ghcr.io/example/{service}@sha256:{str(index) * 64}",
            image_id="sha256:" + str(index + 3) * 64,
            source_sha=SHA,
        )
        for index, service in enumerate(("backend", "frontend", "worker"), 1)
    )
    containers = tuple(
        ContainerObservation(
            service=service,
            container_id=hex(index)[2:] * 64,
            compose_project="medievol",
            network_id="c" * 64,
            running=True,
            restart_policy="unless-stopped",
            image_id=images[index - 1].image_id if index <= 3 else None,
            volume_id="production-volume" if service == "database" else None,
        )
        for index, service in enumerate(("backend", "frontend", "worker", "database"), 1)
    ) + (
        ContainerObservation(
            service="caddy",
            container_id="e" * 64,
            compose_project="medievol",
            network_id="c" * 64,
            running=True,
            restart_policy="unless-stopped",
        ),
    )
    state_identity = Identity(
        operation_id="prior-release",
        previous_sha="f" * 40,
        candidate_sha=SHA,
        backup_sha256="1" * 64,
        backup_path="/private/verified.dump",
        compose_project="medievol",
        postgres_db="game_db",
    )
    observations = HostObservations(
        checkout=CheckoutObservation(SHA, True),
        images=images,
        containers=containers,
        identity_before=identity,
        identity_after=identity,
        metadata=MetadataObservation(
            MetadataState.MANAGED,
            "prior-release",
            Manifest(state_identity, Phase.COMMITTED_WRITERS_ALLOWED),
        ),
        edge=EdgeObservation("e" * 64, "frontend", True),
        observed_from=NOW - timedelta(seconds=10),
        observed_until=NOW - timedelta(seconds=2),
    )
    declarations = ExternalDeclarations(
        external_copy=ExternalCopyDeclaration("copy-evidence-1", "2" * 64, 16384, True),
        clone_restore=CloneRestoreDeclaration(
            "restore-evidence-1", "2" * 64, "isolated-clone-1", True, True
        ),
        capacity_available_bytes=200,
        capacity_required_bytes=100,
        maintenance_window_starts=NOW + timedelta(hours=1),
        maintenance_window_ends=NOW + timedelta(hours=2),
        human_authorization_recorded=True,
    )
    return observations, declarations


def plan(observations=None, declarations=None, **kwargs):
    observed, declared = valid_evidence()
    return plan_adoption(
        observations or observed,
        declarations or declared,
        now=NOW,
        **kwargs,
    )


def test_consistent_observations_produce_only_a_conditional_plan():
    result = plan()

    assert result.status is PlanStatus.NO_GO_PLAN_ONLY
    assert result.blockers == ()
    assert len(result.steps) == 10
    assert "Provision or attest" in result.steps[3]
    assert "durable database write barrier" in result.steps[4]
    assert "SMTP delivery" in result.steps[-1]
    assert result.external_declarations_are_unverified is True
    assert result.requires_human_authorization is True


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"checkout": CheckoutObservation(SHA, False)}, "clean worktree"),
        (
            {
                "images": (
                    ImageObservation("backend", "ghcr.io/example/backend:latest",
                                     "sha256:" + "3" * 64, SHA),
                )
            },
            "immutable SHA-256 digests",
        ),
        ({"images": ()}, "image evidence is required"),
    ],
)
def test_dirty_or_incomplete_release_evidence_blocks_adoption(change, expected):
    observations, declarations = valid_evidence()
    result = plan(replace(observations, **change), declarations)
    assert any(expected in blocker for blocker in result.blockers)
    assert result.status is PlanStatus.NO_GO_PLAN_ONLY


@pytest.mark.parametrize(
    "state,manifest,marker,recovery,expected",
    [
        (MetadataState.ABSENT, None, None, False, "absent"),
        (MetadataState.INCIDENT, None, None, True, "reconciliation"),
        (MetadataState.MANAGED, None, "prior-release", False, "missing or contradicted"),
    ],
)
def test_missing_or_incident_metadata_is_never_a_first_install(
    state, manifest, marker, recovery, expected
):
    observations, declarations = valid_evidence()
    changed = replace(
        observations.metadata,
        state=state,
        manifest=manifest,
        marker_operation_id=marker,
        recovery_marker_present=recovery,
    )
    result = plan(replace(observations, metadata=changed), declarations)
    assert any(expected in blocker for blocker in result.blockers)
    assert result.status is PlanStatus.NO_GO_PLAN_ONLY


@pytest.mark.parametrize("field,value", [
    ("network_id", "x" * 64),
    ("volume_id", "other-volume"),
    ("database_oid", 99999),
    ("schema_sha256", "9" * 64),
])
def test_database_network_or_volume_identity_drift_blocks(field, value):
    observations, declarations = valid_evidence()
    changed_identity = replace(observations.identity_after, **{field: value})
    result = plan(replace(observations, identity_after=changed_identity), declarations)
    assert "Host identity changed" in " ".join(result.blockers)


def test_manifest_marker_mismatch_blocks_without_echoing_input_values():
    observations, declarations = valid_evidence()
    changed = replace(observations.metadata, marker_operation_id="different-marker")
    result = plan(replace(observations, metadata=changed), declarations)
    assert any("contradict" in blocker for blocker in result.blockers)


def test_stale_or_noncontinuous_observations_block():
    observations, declarations = valid_evidence()
    stale = replace(observations, observed_from=NOW - timedelta(minutes=10))
    changed_identity = replace(observations.identity_after, network_id="f" * 64)
    drift = replace(observations, identity_after=changed_identity)
    assert any("stale" in blocker for blocker in plan(stale, declarations).blockers)
    assert any("identity changed" in blocker for blocker in plan(drift, declarations).blockers)


def test_external_evidence_capacity_and_authorization_are_required():
    observations, declarations = valid_evidence()
    unverified = replace(
        declarations,
        external_copy=replace(declarations.external_copy, verified=False),
        clone_restore=replace(declarations.clone_restore, isolated=False),
        capacity_available_bytes=1,
        human_authorization_recorded=False,
    )
    result = plan(observations, unverified)
    assert any("External snapshot" in blocker for blocker in result.blockers)
    assert any("isolated clone" in blocker for blocker in result.blockers)
    assert any("insufficient" in blocker for blocker in result.blockers)
    assert any("human authorization" in blocker for blocker in result.blockers)


def test_external_copy_and_clone_restore_must_reference_same_snapshot():
    observations, declarations = valid_evidence()
    mismatch = replace(
        declarations,
        clone_restore=replace(declarations.clone_restore, source_sha256="3" * 64),
    )
    result = plan(observations, mismatch)
    assert any("do not match the observed target" in blocker for blocker in result.blockers)


def test_role_split_uses_static_contract_and_does_not_echo_secrets():
    observations, declarations = valid_evidence()
    changed = replace(observations.identity_after, application_role="game_admin")
    result = plan(replace(observations, identity_after=changed), declarations)
    rendered = " ".join(result.blockers)
    assert "fail the G5 split contract" in rendered
    assert "synthetic" not in rendered
    assert "postgresql+psycopg" not in rendered


def test_runtime_image_id_must_match_its_digest_attestation():
    observations, declarations = valid_evidence()
    containers = list(observations.containers)
    containers[0] = replace(containers[0], image_id="sha256:" + "f" * 64)
    result = plan(replace(observations, containers=tuple(containers)), declarations)
    assert any("backend runtime image ID" in blocker for blocker in result.blockers)


def test_future_or_invalid_maintenance_window_blocks():
    observations, declarations = valid_evidence()
    changed = replace(declarations, maintenance_window_ends=NOW)
    assert any("maintenance window" in blocker for blocker in plan(observations, changed).blockers)


def test_malformed_typed_collections_and_caddy_identity_fail_closed():
    observations, declarations = valid_evidence()
    malformed = replace(observations, checkout=None, images=None)
    assert plan(malformed, declarations).blockers

    containers = list(observations.containers)
    containers[-1] = replace(containers[-1], container_id="f" * 64)
    result = plan(replace(observations, containers=tuple(containers)), declarations)
    assert any("Caddy identity" in blocker for blocker in result.blockers)


def test_missing_observations_with_external_declarations_fail_closed_without_crashing():
    _, declarations = valid_evidence()
    result = plan_adoption(None, declarations, now=NOW)
    assert result.status is PlanStatus.NO_GO_PLAN_ONLY
    assert any("Typed host observations are missing" in blocker for blocker in result.blockers)
