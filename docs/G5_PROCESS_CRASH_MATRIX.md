# G5 / BM-0093 — Process-death boundary matrix (#174)

**Scope: automated process-death regression; NO-GO for production.**

The tests use an actual separate Python process and SIGKILL, with a synthetic
port that writes a durable event journal and archive. They do not kill a
production process, run Docker or access a database. They exercise the real
activation lease, manifest store and lifecycle coordinator.

| Last side effect before death | Last persisted phase | Required behavior |
|---|---|---|
| Close admission, fence database, stop writers, or snapshot | No manifest | Activation marker blocks fresh lifecycle; do not infer completed preparation |
| PREPARED observation | PREPARED | No automatic migration or retry |
| Migration, candidate verification | MIGRATING | No automatic retry or restore |
| Candidate publication | VERIFIED_READONLY | Publication is not permission to reopen |
| Restore, previous-release verification | MIGRATING | Restore may have run; do not repeat automatically |
| Reopen | COMMITTED_WRITERS_ALLOWED | Never restore the prior snapshot; reconcile actual writer state |

The journal records modeled side effects before acknowledgement, so an
interrupted call cannot be assumed never to have executed. Every case checks
the exact last manifest phase, persistent marker, kernel lease release,
absence of subsequent callbacks and refusal of a fresh lifecycle attempt.
The postcommit case also checks that the stale snapshot is refused.

Run: `pytest -q -o addopts= tests/test_g5_cutover_process_crash.py`.
The full backend validation includes these tests.

## Residual gates

This test does not simulate host power loss or certify real external fences,
storage flush behavior on power failure, privileged writer exclusion, a
crashed Docker/SQL child still executing, or the state of a partially reopened
real service. The low-level manifest APIs are not a certified recovery
entrypoint. No automatic resume is authorized. A future recovery adapter
must reconcile identities, executor liveness and durable barrier continuity,
then demonstrate failure handling in real isolated PostgreSQL/Docker and
staging. #174 remains open and RPO=0 is not certified.
