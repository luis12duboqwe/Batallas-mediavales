"""Pure, non-authorizing observations and plan for a future G5 host adoption."""
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
_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}")
_VOLUME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_IMAGE_DIGEST = re.compile(r".+@sha256:[0-9a-f]{64}")
_REQUIRED_SERVICES = frozenset({"backend", "frontend", "worker", "database", "nginx", "caddy"})
_KNOWN_SERVICES = _REQUIRED_SERVICES | frozenset({"migrate", "seed"})
_EXPECTED_ROUTES = {"/": "frontend", "/api/": "backend", "/socket.io/": "backend"}


class MetadataState(str, Enum):
    ABSENT = "absent"
    LEGACY_UNMANAGED = "legacy_unmanaged"
    LEGACY_MANAGED = "legacy_managed"
    G5_MANAGED = "g5_managed"
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
    postgres_system_identifier: str


@dataclass(frozen=True)
class MetadataObservation:
    state: MetadataState
    legacy_release_sha: str | None = None
    marker_operation_id: str | None = None
    manifest: Manifest | None = None
    recovery_marker_present: bool = False


@dataclass(frozen=True)
class ProxyRoute:
    path: str
    target_service: str
    target_container_id: str


@dataclass(frozen=True)
class EdgeObservation:
    caddy_container_id: str
    caddy_target_service: str
    caddy_target_container_id: str
    caddy_routes: tuple[ProxyRoute, ...]
    nginx_container_id: str
    nginx_routes: tuple[ProxyRoute, ...]
    tls_ready: bool


@dataclass(frozen=True)
class HostInventory:
    """One independently collected, complete snapshot of host adoption evidence."""

    checkout: CheckoutObservation
    identity: TargetIdentity
    images: tuple[ImageObservation, ...]
    containers: tuple[ContainerObservation, ...]
    metadata: MetadataObservation
    edge: EdgeObservation


@dataclass(frozen=True)
class HostObservations:
    before: HostInventory
    after: HostInventory
    observed_from: datetime
    observed_until: datetime


@dataclass(frozen=True)
class ExternalCopyDeclaration:
    evidence_id: str
    sha256: str
    database_oid: int
    schema_sha256: str
    source_release_sha: str
    source_identity: TargetIdentity
    data_sha256: str
    captured_at: datetime
    observed_at: datetime
    verified: bool


@dataclass(frozen=True)
class CloneRestoreDeclaration:
    evidence_id: str
    source_sha256: str
    restored_schema_sha256: str
    restored_database_oid: int
    restored_data_sha256: str
    clone_postgres_system_identifier: str
    clone_id: str
    clone_network_id: str
    clone_volume_id: str
    observed_at: datetime
    restored: bool
    isolated: bool


@dataclass(frozen=True)
class ExternalDeclarations:
    """Unverified claims supplied by an operator; never host observations."""

    external_copy: ExternalCopyDeclaration
    clone_restore: CloneRestoreDeclaration
    capacity_available_bytes: int
    capacity_required_bytes: int
    capacity_observed_at: datetime
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
    "Confirm the observed Caddy-to-Nginx and Nginx-to-backend/frontend routes, including API and Socket.IO, with no bypass route.",
    "Provision or attest a dedicated non-privileged application role; test allowed and denied privileges.",
    "Close HTTP and Socket.IO admission, disable writer restarts, stop all writers, and establish a durable database write barrier.",
    "Capture and verify the external snapshot while the barrier and all host identities remain continuous.",
    "Restore that snapshot only in a distinct isolated logical-restore cluster and verify schema and application data.",
    "After verified rollback evidence exists, durably record the prior release identity before candidate publication.",
    "Publish the approved immutable candidate while admission remains controlled; verify candidate health before any public probe.",
    "Only under separately authorized, controlled admission, probe HTTPS, SMTP delivery, and bounded load; remain NO-GO for activation.",
)


def _aware(value: object) -> bool:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return False
    try:
        return value.utcoffset() is not None
    except Exception:
        return False


def _fresh(value: object, now: object, max_age_seconds: int) -> bool:
    if not _aware(value) or not _aware(now):
        return False
    try:
        age = (now - value).total_seconds()
    except Exception:
        return False
    return 0 <= age <= max_age_seconds


def _before(left: object, right: object) -> bool:
    if not _aware(left) or not _aware(right):
        return False
    try:
        return left < right
    except Exception:
        return False


def _not_after(left: object, right: object) -> bool:
    if not _aware(left) or not _aware(right):
        return False
    try:
        return left <= right
    except Exception:
        return False


def _role_split_is_well_formed(identity: TargetIdentity) -> bool:
    """Reuse the static split validator with synthetic, non-secret credentials."""
    app, admin, database = identity.application_role, identity.maintenance_role, identity.database
    if not all(isinstance(value, str) for value in (app, admin, database)):
        return False
    try:
        result = validate_split({
            "POSTGRES_DB": database,
            "POSTGRES_USER": admin,
            "POSTGRES_PASSWORD": "synthetic-maint-only",
            "DB_URL": f"postgresql+psycopg://{app}:synthetic-app-only@database:5432/{database}",
            "G5_MIGRATION_DB_URL": (
                f"postgresql+psycopg://{admin}:synthetic-maint-only@database:5432/{database}"
            ),
        })
    except (RoleSplitError, TypeError, ValueError):
        return False
    return result.application == app and result.maintenance == admin and result.database == database


def _valid_system_identifier(value: object) -> bool:
    return (isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,19}", value) is not None
            and int(value) <= 2**64 - 1)


def _valid_identity(identity: object) -> bool:
    return (
        isinstance(identity, TargetIdentity)
        and isinstance(identity.compose_project, str)
        and _PROJECT.fullmatch(identity.compose_project) is not None
        and isinstance(identity.compose_sha256, str)
        and _HASH.fullmatch(identity.compose_sha256) is not None
        and isinstance(identity.network_id, str)
        and _CONTAINER_ID.fullmatch(identity.network_id) is not None
        and isinstance(identity.volume_id, str)
        and _VOLUME.fullmatch(identity.volume_id) is not None
        and isinstance(identity.database, str)
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", identity.database) is not None
        and type(identity.database_oid) is int
        and 0 < identity.database_oid <= 2**32 - 1
        and _valid_system_identifier(identity.postgres_system_identifier)
        and isinstance(identity.schema_sha256, str)
        and _HASH.fullmatch(identity.schema_sha256) is not None
        and isinstance(identity.current_release_sha, str)
        and _SHA.fullmatch(identity.current_release_sha) is not None
        and isinstance(identity.caddy_container_id, str)
        and _CONTAINER_ID.fullmatch(identity.caddy_container_id) is not None
    )


def _metadata_consistent(metadata: object, identity: TargetIdentity) -> list[str]:
    blockers: list[str] = []
    if not isinstance(identity, TargetIdentity):
        return ["Release metadata cannot be matched to a malformed target identity."]
    if not isinstance(metadata, MetadataObservation):
        return ["Release metadata observation is missing or malformed."]
    if type(metadata.recovery_marker_present) is not bool:
        return ["Recovery marker observation is malformed."]
    g5_artifacts = (
        metadata.marker_operation_id is not None
        or metadata.manifest is not None
        or metadata.recovery_marker_present
    )
    any_metadata = g5_artifacts or metadata.legacy_release_sha is not None
    if metadata.state is MetadataState.ABSENT:
        blockers.append(
            "Absent metadata contradicts an existing marker, manifest, or recovery artifact."
            if any_metadata else
            "Release metadata is absent; a populated host cannot be treated as a first install."
        )
    elif metadata.state is MetadataState.LEGACY_UNMANAGED:
        if any_metadata:
            blockers.append("Legacy-unmanaged metadata contradicts a marker, receipt, or release claim.")
        blockers.append("Legacy host has no managed release identity; adoption bootstrap is not established.")
    elif metadata.state is MetadataState.LEGACY_MANAGED:
        if g5_artifacts:
            blockers.append("Legacy-managed metadata contradicts G5 marker, manifest, or recovery evidence.")
        if (not isinstance(metadata.legacy_release_sha, str)
                or not _SHA.fullmatch(metadata.legacy_release_sha)
                or metadata.legacy_release_sha != identity.current_release_sha):
            blockers.append("Legacy managed release metadata does not match the observed release.")
    elif metadata.state is MetadataState.G5_MANAGED:
        manifest = metadata.manifest
        if (not isinstance(manifest, Manifest)
                or not isinstance(manifest.identity, Identity)
                or not isinstance(metadata.marker_operation_id, str)
                or metadata.recovery_marker_present
                or metadata.legacy_release_sha is not None):
            blockers.append("G5 terminal receipt or activation marker is missing or contradicted.")
        elif (
            manifest.identity.operation_id != metadata.marker_operation_id
            or manifest.identity.compose_project != identity.compose_project
            or manifest.identity.postgres_db != identity.database
            or manifest.identity.candidate_sha != identity.current_release_sha
            or manifest.phase is not Phase.COMMITTED_WRITERS_ALLOWED
        ):
            blockers.append("G5 terminal receipt, marker, database, project, or release identity contradicts.")
    elif metadata.state is MetadataState.INCIDENT:
        blockers.append("Incident or recovery state requires separate human reconciliation.")
    else:
        blockers.append("Release metadata state is unknown.")
    return blockers


def _inventory_blockers(inventory: object) -> list[str]:
    blockers: list[str] = []
    if not isinstance(inventory, HostInventory):
        return ["Host inventory is missing or malformed."]
    checkout, identity = inventory.checkout, inventory.identity
    if (not isinstance(checkout, CheckoutObservation)
            or not isinstance(checkout.commit_sha, str)
            or _SHA.fullmatch(checkout.commit_sha) is None
            or checkout.clean_worktree is not True):
        blockers.append("Checkout is not an exact full-SHA clean worktree.")
    checkout_valid = (
        isinstance(checkout, CheckoutObservation)
        and isinstance(checkout.commit_sha, str)
        and _SHA.fullmatch(checkout.commit_sha) is not None
        and checkout.clean_worktree is True
    )
    if not _valid_identity(identity):
        blockers.append("Compose, network, volume, database, or release identity is incomplete.")
    elif checkout_valid and checkout.commit_sha != identity.current_release_sha:
        blockers.append("Clean checkout SHA differs from the observed managed release.")
    elif _valid_identity(identity) and not _role_split_is_well_formed(identity):
        blockers.append("Declared application and maintenance roles fail the G5 split contract.")

    images = inventory.images if isinstance(inventory.images, tuple) else ()
    if images is not inventory.images:
        blockers.append("Image inventory is not a typed immutable collection.")
    image_map: dict[str, ImageObservation] = {}
    for image in images:
        if not isinstance(image, ImageObservation):
            blockers.append("Image inventory contains malformed evidence.")
            continue
        if (not isinstance(image.service, str)
                or image.service not in {"backend", "frontend", "worker"}
                or image.service in image_map):
            blockers.append("Backend, frontend, and worker image evidence is unknown or duplicated.")
            continue
        image_map[image.service] = image
        if image.source_sha != getattr(checkout, "commit_sha", None):
            blockers.append("An image is not tied to the exact observed checkout SHA.")
        if (not isinstance(image.reference, str)
                or _IMAGE_DIGEST.fullmatch(image.reference) is None):
            blockers.append("Backend, frontend, and worker images must use immutable SHA-256 digests.")
        else:
            errors: list[str] = []
            validate_image("IMAGE", image.reference, errors)
            if errors:
                blockers.append("An image reference fails the deployment preflight contract.")
        if not isinstance(image.image_id, str) or _IMAGE_ID.fullmatch(image.image_id) is None:
            blockers.append("An image lacks a full immutable image ID.")
    if set(image_map) != {"backend", "frontend", "worker"}:
        blockers.append("Exactly backend, frontend, and worker image evidence is required.")
    if all(key in image_map for key in ("backend", "worker")):
        if (image_map["backend"].image_id != image_map["worker"].image_id
                or image_map["backend"].reference != image_map["worker"].reference):
            blockers.append("Backend and worker must use the same immutable backend image ID and digest.")

    containers = inventory.containers if isinstance(inventory.containers, tuple) else ()
    if containers is not inventory.containers:
        blockers.append("Container inventory is not a typed immutable collection.")
    service_map: dict[str, ContainerObservation] = {}
    ids: set[str] = set()
    for container in containers:
        if not isinstance(container, ContainerObservation):
            blockers.append("Container inventory contains malformed evidence.")
            continue
        service = container.service
        if (not isinstance(service, str) or service not in _KNOWN_SERVICES
                or service in service_map):
            blockers.append("Compose service inventory is unknown or duplicated.")
            continue
        service_map[service] = container
        if (not isinstance(container.container_id, str)
                or _CONTAINER_ID.fullmatch(container.container_id) is None
                or not isinstance(identity, TargetIdentity)
                or container.compose_project != identity.compose_project
                or container.network_id != identity.network_id
                or type(container.running) is not bool
                or not isinstance(container.restart_policy, str)
                or container.restart_policy not in {"no", "always", "unless-stopped", "on-failure"}):
            blockers.append("A container identity does not match the observed Compose target.")
        elif container.container_id in ids:
            blockers.append("Compose container IDs are duplicated.")
        else:
            ids.add(container.container_id)
        if service in _REQUIRED_SERVICES and container.running is not True:
            blockers.append(f"{service} is not running in the observed prior release.")
        if service == "database" and container.volume_id != getattr(identity, "volume_id", None):
            blockers.append("PostgreSQL volume differs from the observed volume identity.")
        if service in {"migrate", "seed"} and (
            container.running is not False or container.restart_policy != "no"
        ):
            blockers.append(f"{service} must be stopped with restart policy no.")
        if service in {"backend", "worker", "frontend"}:
            image = image_map.get(service)
            if image is not None and container.image_id != image.image_id:
                blockers.append(f"{service} runtime image ID differs from its pinned image evidence.")
    if not _REQUIRED_SERVICES.issubset(service_map):
        blockers.append("Backend, frontend, worker, database, Nginx, and Caddy must all be observed.")
    if isinstance(identity, TargetIdentity):
        caddy = service_map.get("caddy")
        nginx = service_map.get("nginx")
        if caddy is None or caddy.container_id != identity.caddy_container_id:
            blockers.append("Compose Caddy identity differs from the observed edge identity.")
        if nginx is None:
            blockers.append("Nginx container evidence is missing.")
        _edge_blockers(inventory.edge, service_map, identity, blockers)
    blockers.extend(_metadata_consistent(inventory.metadata, identity))
    return blockers


def _edge_blockers(
    edge: object,
    services: dict[str, ContainerObservation],
    identity: TargetIdentity,
    blockers: list[str],
) -> None:
    if not isinstance(edge, EdgeObservation):
        blockers.append("Caddy and Nginx route evidence is missing.")
        return
    caddy, nginx = services.get("caddy"), services.get("nginx")
    if (caddy is None or nginx is None
            or edge.caddy_container_id != caddy.container_id
            or edge.caddy_container_id != identity.caddy_container_id
            or edge.caddy_target_service != "nginx"
            or edge.caddy_target_container_id != nginx.container_id
            or edge.nginx_container_id != nginx.container_id):
        blockers.append("Caddy-to-Nginx target identity or route is inconsistent.")
    caddy_routes = edge.caddy_routes if isinstance(edge.caddy_routes, tuple) else ()
    if caddy_routes is not edge.caddy_routes:
        blockers.append("Caddy routes are not a typed immutable collection.")
    if (len(caddy_routes) != 1
            or not isinstance(caddy_routes[0], ProxyRoute)
            or caddy_routes[0].path != "/"
            or caddy_routes[0].target_service != "nginx"
            or nginx is None
            or caddy_routes[0].target_container_id != nginx.container_id):
        blockers.append("Caddy has a missing, bypassing, or mismatched route to Nginx.")
    routes = edge.nginx_routes if isinstance(edge.nginx_routes, tuple) else ()
    if routes is not edge.nginx_routes:
        blockers.append("Nginx routes are not a typed immutable collection.")
    route_map: dict[str, ProxyRoute] = {}
    for route in routes:
        if not isinstance(route, ProxyRoute):
            blockers.append("Nginx route inventory is malformed or duplicated.")
            continue
        if not isinstance(route.path, str) or route.path in route_map:
            blockers.append("Nginx route inventory is malformed or duplicated.")
            continue
        route_map[route.path] = route
    if set(route_map) != set(_EXPECTED_ROUTES):
        blockers.append("Nginx route inventory is incomplete or contains a bypass route.")
    for path, target in _EXPECTED_ROUTES.items():
        route = route_map.get(path)
        container = services.get(target)
        if (route is None or container is None
                or route.target_service != target
                or route.target_container_id != container.container_id):
            blockers.append(f"Nginx {path} route does not match its observed {target} container.")
    if edge.tls_ready is not True:
        blockers.append("Caddy TLS readiness is not established.")


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
    if not _aware(now):
        blockers.append("A timezone-aware planning time is required.")
    if not isinstance(observations, HostObservations):
        blockers.append("Typed host observations are missing.")
        observations = None
    if not isinstance(declarations, ExternalDeclarations):
        blockers.append("External declarations are missing.")
        declarations = None

    if observations is not None:
        if not _aware(observations.observed_from) or not _aware(observations.observed_until):
            blockers.append("Observation timestamps must include a valid timezone offset.")
        elif not _not_after(observations.observed_from, observations.observed_until):
            blockers.append("Host observation interval is unordered.")
        if (not _fresh(observations.observed_from, now, max_observation_age_seconds)
                or not _fresh(observations.observed_until, now, max_observation_age_seconds)):
            blockers.append("Host observations are stale or future-dated.")
        before_blockers = _inventory_blockers(observations.before)
        after_blockers = _inventory_blockers(observations.after)
        if observations.before != observations.after:
            blockers.append("Checkout, images, containers, edge, metadata, or target identity changed during observation.")
        blockers.extend(after_blockers)
        # A before snapshot must itself be valid, rather than merely matching an invalid after snapshot.
        blockers.extend(before_blockers)
        if (not _aware(observations.observed_from)
                or not _aware(observations.observed_until)
                or not _aware(now)
                or not isinstance(observations.before, HostInventory)
                or not isinstance(observations.before.identity, TargetIdentity)
                or not isinstance(observations.after, HostInventory)
                or not isinstance(observations.after.identity, TargetIdentity)):
            target_identity = None
        else:
            target_identity = observations.after.identity
    else:
        target_identity = None

    if declarations is not None:
        copy, restore = declarations.external_copy, declarations.clone_restore
        if not isinstance(copy, ExternalCopyDeclaration):
            blockers.append("External copy evidence is missing or malformed.")
        elif (
            not isinstance(copy.evidence_id, str) or not copy.evidence_id
            or not isinstance(copy.sha256, str) or _HASH.fullmatch(copy.sha256) is None
            or type(copy.database_oid) is not int or copy.database_oid <= 0
            or not isinstance(copy.schema_sha256, str) or _HASH.fullmatch(copy.schema_sha256) is None
            or not isinstance(copy.source_release_sha, str) or _SHA.fullmatch(copy.source_release_sha) is None
            or not _valid_identity(copy.source_identity)
            or not isinstance(copy.data_sha256, str) or _HASH.fullmatch(copy.data_sha256) is None
            or copy.verified is not True
        ):
            blockers.append("External snapshot verification is only declared or incomplete.")
        if not isinstance(restore, CloneRestoreDeclaration):
            blockers.append("Isolated-clone restore evidence is missing or malformed.")
        elif (
            not isinstance(restore.evidence_id, str) or not restore.evidence_id
            or not isinstance(restore.source_sha256, str) or _HASH.fullmatch(restore.source_sha256) is None
            or not isinstance(restore.restored_schema_sha256, str)
            or _HASH.fullmatch(restore.restored_schema_sha256) is None
            or type(restore.restored_database_oid) is not int
            or not 0 < restore.restored_database_oid <= 2**32 - 1
            or not isinstance(restore.restored_data_sha256, str)
            or _HASH.fullmatch(restore.restored_data_sha256) is None
            or not _valid_system_identifier(restore.clone_postgres_system_identifier)
            or not isinstance(restore.clone_id, str) or not restore.clone_id
            or not isinstance(restore.clone_network_id, str)
            or _CONTAINER_ID.fullmatch(restore.clone_network_id) is None
            or not isinstance(restore.clone_volume_id, str)
            or _VOLUME.fullmatch(restore.clone_volume_id) is None
            or restore.restored is not True or restore.isolated is not True
        ):
            blockers.append("Restore evidence in an isolated clone is only declared or incomplete.")

        if isinstance(copy, ExternalCopyDeclaration):
            if (not _fresh(copy.observed_at, now, max_observation_age_seconds)
                    or not _fresh(copy.captured_at, now, max_observation_age_seconds)
                    or not _not_after(copy.captured_at, copy.observed_at)):
                blockers.append("External snapshot evidence is stale or has an invalid timestamp.")
        if isinstance(restore, CloneRestoreDeclaration):
            if not _fresh(restore.observed_at, now, max_observation_age_seconds):
                blockers.append("Clone-restore evidence is stale or has an invalid timestamp.")
        if (isinstance(copy, ExternalCopyDeclaration)
                and isinstance(restore, CloneRestoreDeclaration)
                and target_identity is not None):
            if (
                copy.sha256 != restore.source_sha256
                or copy.schema_sha256 != restore.restored_schema_sha256
                or copy.database_oid != target_identity.database_oid
                or copy.source_identity != target_identity
                or copy.data_sha256 != restore.restored_data_sha256
                or not _not_after(copy.observed_at, restore.observed_at)
                or restore.clone_postgres_system_identifier == target_identity.postgres_system_identifier
                or copy.schema_sha256 != target_identity.schema_sha256
                or copy.source_release_sha != target_identity.current_release_sha
                or restore.clone_network_id == target_identity.network_id
                or restore.clone_volume_id == target_identity.volume_id
            ):
                blockers.append("External copy or clone evidence differs from the observed source identity.")
        if (type(declarations.capacity_available_bytes) is not int
                or type(declarations.capacity_required_bytes) is not int
                or declarations.capacity_required_bytes <= 0
                or declarations.capacity_available_bytes < declarations.capacity_required_bytes):
            blockers.append("Declared capacity is invalid or insufficient.")
        if not _fresh(declarations.capacity_observed_at, now, max_observation_age_seconds):
            blockers.append("Capacity evidence is stale or has an invalid timestamp.")
        start, end = declarations.maintenance_window_starts, declarations.maintenance_window_ends
        if (not _aware(start) or not _aware(end) or not _aware(now)
                or not _before(now, start) or not _before(start, end)):
            blockers.append("A future, ordered maintenance window with valid offsets is required.")
        if declarations.human_authorization_recorded is not True:
            blockers.append("Explicit human authorization is not recorded.")

    return AdoptionPlan(
        status=PlanStatus.NO_GO_PLAN_ONLY,
        blockers=tuple(dict.fromkeys(blockers)),
        steps=_STEPS,
        external_declarations_are_unverified=True,
        requires_human_authorization=True,
    )
