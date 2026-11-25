"""Supervised G5 lifecycle, retaining one activation lease throughout.

No CLI, production port, automatic resume or general recovery entrypoint.
An adapter must prove continuous exclusion of *all* other writers (including
privileged channels) from preparation through commit/restore. Observations
alone are insufficient. Only a positively classified migration rejection
permits a controlled restore; any uncertainty leaves a blocking incident.
"""
from __future__ import annotations

from typing import Protocol

from ops.g5_activation_fence import arm_cutover
from ops.g5_cutover_prepare import G5Preparation, PreparationPort, PreparationRequest
from ops.g5_cutover_state import CutoverStore, Identity, Manifest, Phase, StateError


class MigrationRejected(RuntimeError):
    """Adapter attests that a known migration failed and its executor exited.

    This is NOT proof of barrier continuity. An unknown timeout, signal,
    transport error or lost acknowledgement must not use this classification.
    """


class RecoveryRequired(StateError):
    """The lifecycle failed; manual reconciliation is required."""


class LifecyclePort(PreparationPort, Protocol):
    def verify_continuity(self, identity: Identity) -> bool:
        """Attest the barrier never lapsed, all privileged writers excluded.

        Also verify current SQL/edge/Docker state. True is allowed only when
        the adapter owns the entire interval and no uncontrolled writer exists.
        """
        ...

    def migrate(self, identity: Identity) -> None:
        """Run only the isolated maintenance executor, await its exit."""
        ...

    def verify_candidate_readonly(self, identity: Identity) -> bool:
        """Verify exact candidate release/schema without reopening writers."""
        ...

    def publish_candidate(self, identity: Identity) -> None:
        """Publish durable exact release metadata without enabling any writer."""
        ...

    def restore_previous(self, identity: Identity, verified_fd: int) -> None:
        """Restore verified FD in place; never drop/recreate the fenced DB.

        Must preserve role/DB/edge/container barriers and previous metadata.
        Called only in the explicitly rejected migration path.
        """
        ...

    def verify_previous_readonly(self, identity: Identity) -> bool:
        """Verify previous release/schema/data restored; no writer admission."""
        ...

    def reopen_writers(self, identity: Identity) -> None:
        """Only after durable COMMITTED; never restore the prior snapshot."""
        ...


class G5Lifecycle:
    """Single-attempt transaction ordering; no recovery from a later process."""

    def execute(self, request: PreparationRequest, port: LifecyclePort) -> Manifest:
        if not isinstance(request, PreparationRequest):
            raise StateError("invalid G5 lifecycle request")
        store = CutoverStore(request.host_root)
        with arm_cutover(request.host_root, request.operation_id) as lease:
            manifest = G5Preparation()._prepare_armed(request, port, store, lease)
            identity = manifest.identity

            def phase(expected: Phase) -> None:
                lease()
                current = store.show()
                if current.identity != identity or current.phase is not expected:
                    raise StateError("G5 lifecycle phase or identity changed")

            def require_continuity(expected: Phase) -> None:
                phase(expected)
                if port.verify_continuity(identity) is not True:
                    raise StateError("continuous G5 writer exclusion was not established")
                phase(expected)

            def advance(expected: Phase, target: Phase) -> Manifest:
                phase(expected)
                updated = store.advance(identity, expected, target)
                phase(target)
                return updated

            def incident():
                # Never downgrade COMMITTED, even if a writer start failed.
                # If metadata/lease is uncertain, preserve evidence and do not
                # attempt to overwrite it with a potentially incorrect phase.
                lease()
                current = store.show()
                if current.identity != identity:
                    raise StateError("cannot reconcile changed cutover identity")
                if current.phase in (Phase.PREPARED, Phase.MIGRATING, Phase.VERIFIED_READONLY):
                    advance(current.phase, Phase.RECOVERY_REQUIRED)

            def restore_rejected():
                # The only allowed automatic restore path. A continuous
                # barrier, same identity, verified archive and phase are all
                # required. Keep the manifest lock while consuming the FD.
                require_continuity(Phase.MIGRATING)
                with store.verify_restore_allowed(identity, request.backup_root) as fd:
                    lease()
                    if port.verify_continuity(identity) is not True:
                        raise StateError("writer exclusion lost before restore")
                    lease()
                    port.restore_previous(identity, fd)
                    lease()
                    if port.verify_continuity(identity) is not True:
                        raise StateError("writer exclusion lost during restore")
                require_continuity(Phase.MIGRATING)
                if port.verify_previous_readonly(identity) is not True:
                    raise StateError("previous release recovery could not be verified")
                require_continuity(Phase.MIGRATING)
                # Successful data recovery is not permission to reopen.
                advance(Phase.MIGRATING, Phase.RECOVERY_REQUIRED)
                raise RecoveryRequired("migration rejected; previous data restored, writers remain closed")

            try:
                require_continuity(Phase.PREPARED)
                # Revalidate archive before authorizing migration mutations.
                with store.verify_restore_allowed(identity, request.backup_root):
                    lease()
                    if port.verify_continuity(identity) is not True:
                        raise StateError("writer exclusion lost before migration")
                advance(Phase.PREPARED, Phase.MIGRATING)
                require_continuity(Phase.MIGRATING)
                try:
                    port.migrate(identity)
                except MigrationRejected:
                    restore_rejected()
                require_continuity(Phase.MIGRATING)
                if port.verify_candidate_readonly(identity) is not True:
                    raise StateError("candidate release verification failed")
                require_continuity(Phase.MIGRATING)
                advance(Phase.MIGRATING, Phase.VERIFIED_READONLY)
                require_continuity(Phase.VERIFIED_READONLY)
                port.publish_candidate(identity)
                require_continuity(Phase.VERIFIED_READONLY)
                # Publication is not writer authorization. Persist COMMITTED
                # before any app login, Docker start or edge admission.
                result = advance(Phase.VERIFIED_READONLY, Phase.COMMITTED_WRITERS_ALLOWED)
                require_continuity(Phase.COMMITTED_WRITERS_ALLOWED)
                port.reopen_writers(identity)
                phase(Phase.COMMITTED_WRITERS_ALLOWED)
                return result
            except BaseException:
                # Includes KeyboardInterrupt/SystemExit. A SIGKILL leaves the
                # durable marker/phase and no automatic resume path.
                incident()
                raise
