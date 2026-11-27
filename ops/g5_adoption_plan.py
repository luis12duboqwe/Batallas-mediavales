"""Pure, non-authorizing observations and plan for a future G5 host adoption.

This module does not inspect a host or execute Docker, SQL, probes, or writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re

from ops.g5_cutover_state import Identity, Manifest, Phase
from ops.g5_migration_role_identity import RoleSplitError, validate_split
from ops.preflight import validate_image


_SHA = re.compile(r"[0-9a-f]{40}")
_HASH = re.compile(r"[0-9a-f]{64}")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
_IMAGE_DIGEST = re.compile(r".+@sha256:[0-9a-f]{64}")
_REQUIRED_SERVICES = frozenset({"backend", "frontend", "worker", "database"})
_KNOWN_SERVICES = _REQUIRED_SERVICES | frozenset({"migrate", "seed", "nginx", "caddy"})


class MetadataState(str, Enum):
    ABSENT = "absent"
    MANAGED = "managed"
    INCIDENT = "incident"


@dataclass(frozen=True)
class CheckoutObservation:
    commit_sha: str
    clean_worktree: bool


@dataclass(frozen=True)
class ImageObservation:
    service: str
    reference: str
    image_id: str
    source_sha: str


@dataclass(frozen=True)
class ContainerObservation:
    service: str
    container_id: str
    compose_project: str
    network_id: str
    running: bool
    restart_policy: str
    image_id: str | None = None
    volume_id: str | None = None


@dataclass(frozen=True)
class TargetIdentity:
    compose_project: str
    compose_sha256: str
    network_id: str
    volume_id: str
    database: str
    database_oid: int
    schema_sha256: str
    current_release_sha: str
    application_role: str
    maintenance_role: str
    caddy_container_id: str


@dataclass(frozen=True)
class MetadataObservation:
    state: MetadataState
    marker_operation_id: str | None
    manifest: Manifest | None
    recovery_marker_present: bool = False


@dataclass(frozen=True)
class EdgeObservation:
    caddy_container_id: str
    target_service: str
    tls_ready: bool


@dataclass(frozen=True)
class HostObservations:
    checkout: CheckoutObservation
    images: tuple[ImageObservation, ...]
    containers: tuple[ContainerObservation, ...]
    identity_before: TargetIdentity
    identity_after: TargetIdentity
    metadata: MetadataObservation
    edge: EdgeObservation
    observed_from: datetime
    observed_until: datetime


@dataclass(frozen=True)
class ExternalCopyDeclaration:
    evidence_id: str
    sha256: str
    database_oid: int
    verified: bool


@dataclass(frozen=True)
class CloneRestoreDeclaration:
    evidence_id: str
    source_sha256: str
    clone_id: str
    restored: bool
    isolated: bool


@dataclass(frozen=True)
class ExternalDeclarations:
    """Unverified claims supplied by an operator; never host observations."""

    external_copy: ExternalCopyDeclaration
    clone_restore: CloneRestoreDeclaration
    capacity_available_bytes: int
    capacity_required_bytes: int
    maintenance_window_starts: datetime
    maintenance_window_ends: datetime
    human_authorization_recorded: bool


class PlanStatus(str, Enum):
    NO_GO_PLAN_ONLY = "NO_GO_PLAN_ONLY"


@dataclass(frozen=True)
class AdoptionPlan:
    status: PlanStatus
    blockers: tuple[str, ...]
    steps: tuple[str, ...]
    external_declarations_are_unverified: bool
    requires_human_authorization: bool


_STEPS = (
    "Obtain explicit human authorization and confirm the approved maintenance window.",
    "Pin the exact clean checkout and backend, frontend, and worker images by digest and image ID.",
    "Reconfirm Compose, edge, network, volume, PostgreSQL OID, schema, roles, and release identity without drift.",
    "Provision or attest a dedicated non-privileged application role; test allowed and denied privileges.",
    "Close HTTP and Socket.IO admission, disable writer restarts, stop all writers, and establish a durable database write barrier.",
    "Under the barrier, durably record the prior managed release and preserve its recovery identity.",
    "Capture and verify the external snapshot while the barrier and all identity checks remain continuous.",
    "Restore the snapshot only in an isolated clone and verify schema and application data before adoption.",
    "Publish the approved immutable release only after the prior release and recovery evidence are durable.",
    "Probe public HTTPS, SMTP delivery, and bounded load; keep admission closed on any uncertainty.",
)


def _fresh(value: datetime, now: datetime, max_age_seconds: int) -> bool:
    if (not isinstance(value, datetime) or not isinstance(now, datetime)
            or value.tzinfo is None or now.tzinfo is None):
        return False
    age = (now - value).total_seconds()
    return 0 <= age <= max_age_seconds


def _role_split_is_well_formed(identity: TargetIdentity) -> bool:
    """Reuse the static split validator with synthetic, non-secret credentials."""
    app = identity.application_role
    admin = identity.maintenance_role
    database = identity.database
    if not all(isinstance(value, str) for value in (app, admin, database)):
        return False
    app_url = f"postgresql+psycopg://{app}:synthetic-app-only@database:5432/{database}"
    admin_url = f"postgresql+psycopg://{admin}:synthetic-maint-only@database:5432/{database}"
    try:
        result = validate_split({
            "POSTGRES_DB": database,
            "POSTGRES_USER": admin,
            "POSTGRES_PASSWORD": "synthetic-maint-only",
            "DB_URL": app_url,
            "G5_MIGRATION_DB_URL": admin_url,
        })
    except (RoleSplitError, TypeError, ValueError):
        return False
    return (result.application == app and result.maintenance == admin
            and result.database == database)


def plan_adoption(
    observations: HostObservations,
    declarations: ExternalDeclarations,
    *,
    now: datetime,
    max_observation_age_seconds: int = 300,
) -> AdoptionPlan:
    """Return blockers and conditional steps; never return deployment approval."""
    blockers: list[str] = []
    if type(max_observation_age_seconds) is not int or max_observation_age_seconds <= 0:
        blockers.append("Observation freshness limit is invalid.")
        max_observation_age_seconds = 0
    if not isinstance(observations, HostObservations):
        blockers.append("Typed host observations are missing.")
        observations = None
    if not isinstance(declarations, ExternalDeclarations):
        blockers.append("External declarations are missing.")
        declarations = None
    if not isinstance(now, datetime) or now.tzinfo is None:
        blockers.append("A timezone-aware planning time is required.")

    if observations is not None:
        if observations.identity_before != observations.identity_after:
            blockers.append("Host identity changed during observation.")
        if (not _fresh(observations.observed_from, now, max_observation_age_seconds)
                or not _fresh(observations.observed_until, now, max_observation_age_seconds)
                or not isinstance(observations.observed_from, datetime)
                or not isinstance(observations.observed_until, datetime)
                or observations.observed_from.tzinfo is None
                or observations.observed_until.tzinfo is None
                or observations.observed_from > observations.observed_until):
            blockers.append("Host observations are stale, future-dated, or unordered.")

        checkout = observations.checkout
        checkout_sha = (
            checkout.commit_sha
            if isinstance(checkout, CheckoutObservation) and isinstance(checkout.commit_sha, str)
            else None
        )
        if (not isinstance(checkout, CheckoutObservation)
                or not isinstance(checkout.commit_sha, str)
                or not _SHA.fullmatch(checkout.commit_sha)
                or checkout.clean_worktree is not True):
            blockers.append("Checkout is not an exact full-SHA clean worktree.")

        identity = observations.identity_after
        if not isinstance(identity, TargetIdentity):
            blockers.append("Target identity evidence is malformed.")
        else:
            if (not isinstance(identity.compose_sha256, str)
                    or not _HASH.fullmatch(identity.compose_sha256)
                    or not isinstance(identity.schema_sha256, str)
                    or not _HASH.fullmatch(identity.schema_sha256)
                    or not isinstance(identity.caddy_container_id, str)
                    or not _CONTAINER_ID.fullmatch(identity.caddy_container_id)
                    or type(identity.database_oid) is not int or identity.database_oid <= 0
                    or not isinstance(identity.network_id, str) or not identity.network_id
                    or not isinstance(identity.volume_id, str) or not identity.volume_id
                    or not isinstance(identity.compose_project, str)
                    or not isinstance(identity.database, str)):
                blockers.append("Compose, network, volume, edge, or database identity is incomplete.")
            if (isinstance(checkout, CheckoutObservation)
                    and checkout.commit_sha != identity.current_release_sha):
                blockers.append("Clean checkout SHA differs from the observed managed release.")
            if not _role_split_is_well_formed(identity):
                blockers.append("Declared application and maintenance roles fail the G5 split contract.")

        image_rows = observations.images if isinstance(observations.images, tuple) else ()
        if image_rows is not observations.images:
            blockers.append("Image inventory is not a typed immutable collection.")
        image_map: dict[str, ImageObservation] = {}
        for image in image_rows:
            if not isinstance(image, ImageObservation) or image.reference is None:
                blockers.append("Image inventory contains malformed evidence.")
                continue
            if (not isinstance(image.service, str)
                    or image.service not in {"backend", "frontend", "worker"}
                    or image.service in image_map):
                blockers.append("Backend, frontend, and worker image evidence is unknown or duplicated.")
                continue
            image_map[image.service] = image
            if image.source_sha != checkout_sha:
                blockers.append("An image is not tied to the exact observed checkout SHA.")
            if (not isinstance(image.reference, str)
                    or not _IMAGE_DIGEST.fullmatch(image.reference)):
                blockers.append("Backend, frontend, and worker images must use immutable SHA-256 digests.")
            else:
                errors: list[str] = []
                validate_image("IMAGE", image.reference, errors)
                if errors:
                    blockers.append("An image reference fails the deployment preflight contract.")
            if (not isinstance(image.image_id, str)
                    or not _IMAGE_ID.fullmatch(image.image_id)):
                blockers.append("An image lacks a full immutable image ID.")
        if set(image_map) != {"backend", "frontend", "worker"}:
            blockers.append("Exactly backend, frontend, and worker image evidence is required.")

        if isinstance(identity, TargetIdentity):
            services: dict[str, ContainerObservation] = {}
            container_ids: set[str] = set()
            container_rows = observations.containers if isinstance(observations.containers, tuple) else ()
            if container_rows is not observations.containers:
                blockers.append("Container inventory is not a typed immutable collection.")
            for container in container_rows:
                if not isinstance(container, ContainerObservation):
                    blockers.append("Container inventory contains malformed evidence.")
                    continue
                if (not isinstance(container.service, str)
                        or container.service not in _KNOWN_SERVICES
                        or container.service in services):
                    blockers.append("Compose service inventory is unknown or duplicated.")
                    continue
                services[container.service] = container
                if (not isinstance(container.container_id, str)
                        or not _CONTAINER_ID.fullmatch(container.container_id)
                        or container.compose_project != identity.compose_project
                        or container.network_id != identity.network_id
                        or type(container.running) is not bool
                        or not isinstance(container.restart_policy, str)
                        or not container.restart_policy):
                    blockers.append("A container identity does not match the observed Compose target.")
                elif container.container_id in container_ids:
                    blockers.append("Compose container IDs are duplicated.")
                else:
                    container_ids.add(container.container_id)
                if container.service == "database" and container.volume_id != identity.volume_id:
                    blockers.append("PostgreSQL volume differs from the observed volume identity.")
                if (container.service == "caddy"
                        and container.container_id != identity.caddy_container_id):
                    blockers.append("Compose Caddy identity differs from the observed edge identity.")
            if not _REQUIRED_SERVICES.issubset(services):
                blockers.append("Backend, frontend, worker, and database containers must all be observed.")
            for service in ("backend", "frontend", "worker"):
                container = services.get(service)
                image = image_map.get(service)
                if container is not None and image is not None and container.image_id != image.image_id:
                    blockers.append(f"{service} runtime image ID differs from its pinned image evidence.")

        edge = observations.edge
        if (not isinstance(edge, EdgeObservation)
                or not isinstance(identity, TargetIdentity)
                or edge.caddy_container_id != identity.caddy_container_id
                or edge.target_service != "frontend"
                or edge.tls_ready is not True):
            blockers.append("Caddy identity, frontend route, or TLS observation is inconsistent.")

        metadata = observations.metadata
        if not isinstance(metadata, MetadataObservation):
            blockers.append("Managed release metadata observation is missing.")
        elif metadata.state is MetadataState.ABSENT:
            blockers.append("Release metadata is absent; a populated host cannot be treated as a first install.")
        elif metadata.state is MetadataState.INCIDENT:
            blockers.append("Incident or recovery state requires separate human reconciliation.")
        elif metadata.state is not MetadataState.MANAGED:
            blockers.append("Release metadata state is unknown.")
        else:
            manifest = metadata.manifest
            if (not isinstance(manifest, Manifest)
                    or not isinstance(manifest.identity, Identity)
                    or metadata.marker_operation_id is None
                    or metadata.recovery_marker_present):
                blockers.append("Managed marker or manifest is missing or contradicted by recovery evidence.")
            elif (not isinstance(identity, TargetIdentity)
                    or manifest.identity.operation_id != metadata.marker_operation_id
                    or manifest.identity.compose_project != identity.compose_project
                    or manifest.identity.postgres_db != identity.database
                    or manifest.identity.candidate_sha != identity.current_release_sha
                    or manifest.phase is not Phase.COMMITTED_WRITERS_ALLOWED):
                blockers.append("Managed marker, manifest, database, project, or release identity contradicts.")

    if declarations is not None:
        copy = declarations.external_copy
        restore = declarations.clone_restore
        if (not isinstance(copy, ExternalCopyDeclaration)
                or not isinstance(copy.evidence_id, str) or not copy.evidence_id
                or not isinstance(copy.sha256, str) or not _HASH.fullmatch(copy.sha256)
                or type(copy.database_oid) is not int
                or copy.verified is not True):
            blockers.append("External snapshot verification is only declared or missing.")
        if (not isinstance(restore, CloneRestoreDeclaration)
                or not isinstance(restore.evidence_id, str) or not restore.evidence_id
                or not isinstance(restore.source_sha256, str)
                or not _HASH.fullmatch(restore.source_sha256)
                or not isinstance(restore.clone_id, str) or not restore.clone_id
                or restore.restored is not True or restore.isolated is not True):
            blockers.append("Restore evidence in an isolated clone is only declared or missing.")
        if (isinstance(copy, ExternalCopyDeclaration)
                and isinstance(restore, CloneRestoreDeclaration)):
            if (copy.sha256 != restore.source_sha256
                    or copy.database_oid != getattr(observations.identity_after, "database_oid", None)
                    or restore.clone_id == getattr(observations.identity_after, "volume_id", None)):
                blockers.append("External copy and isolated-clone evidence do not match the observed target.")
        if (type(declarations.capacity_available_bytes) is not int
                or type(declarations.capacity_required_bytes) is not int
                or declarations.capacity_required_bytes <= 0
                or declarations.capacity_available_bytes < declarations.capacity_required_bytes):
            blockers.append("Declared capacity is invalid or insufficient.")
        start, end = declarations.maintenance_window_starts, declarations.maintenance_window_ends
        if (not isinstance(start, datetime) or not isinstance(end, datetime)
                or not isinstance(now, datetime) or start.tzinfo is None or end.tzinfo is None
                or now.tzinfo is None or start <= now or end <= start):
            blockers.append("A future, ordered maintenance window is required.")
        if declarations.human_authorization_recorded is not True:
            blockers.append("Explicit human authorization is not recorded.")

    return AdoptionPlan(
        status=PlanStatus.NO_GO_PLAN_ONLY,
        blockers=tuple(dict.fromkeys(blockers)),
        steps=_STEPS,
        external_declarations_are_unverified=True,
        requires_human_authorization=True,
    )
