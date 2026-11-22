# BM-0093: write-after-snapshot reproduction

## Scope and safety

`tests/test_bm0093_write_barrier_postgres.py` uses only disposable PostgreSQL 15
containers (`postgres:15-alpine`) with `--network none`, no published ports,
and no persistent volumes. It never reads `DATABASE_URL`, project credentials,
or an external database. If Docker or the PostgreSQL 15 image is unavailable,
pytest reports a skip with its reason; a skip is not a passing reproduction.

The test uses `pg_dump` and `pg_restore` directly against those containers and
restores into a second disposable PostgreSQL container. It does not execute a
deployment, connect to staging/production, invoke the operational backup or
restore scripts, or prove that a real deployment rollback occurred.

## Reproduction

The first test commits marker `A`, makes a custom-format snapshot, then commits
marker `B` on the source before restoring the snapshot to the second database.
It verifies both markers are committed on the source and only `A` is present in
the restored database. This demonstrates that a snapshot taken before a later
confirmed write cannot provide RPO=0 for that write if the snapshot alone is
used for recovery. A negative-control test commits `A` before the snapshot and
verifies that it survives restoration.

The third test exercises PostgreSQL's advisory-lock primitive as a possible
barrier protocol: a shared lock represents a writer transaction and an
exclusive lock represents maintenance. It checks that an exclusive barrier
waits for the existing writer, a new participating writer waits behind the
barrier, and it proceeds only after the barrier is released. This validates
only that database primitive and ordering; no backend, HTTP, WebSocket, worker,
or multi-instance integration is implemented or certified by this test.

Run the test with the repository's existing pytest setup:

```bash
pytest -q tests/test_bm0093_write_barrier_postgres.py
```

In the existing `validation.yml` backend job, pytest discovers this test with
the full test suite. PostgreSQL CI already uses PostgreSQL 15; the reproduction
creates its own network-isolated containers rather than reusing the service
database.

## Current operational ordering observed

In `ops/deploy_remote.sh`, the existing-schema path brings up/probes the
database and runs `ops/backup_postgres.sh` (lines 247–286), then pulls release
images (line 304), and only then marks release mutation and starts the new
compose release (lines 306–308). The backup helper invokes `pg_dump` and
verifies/publishes the archive (in particular lines 50–64 of
`ops/backup_postgres.sh`). The deployment sequence does not show a required
write barrier before that snapshot. Consequently, the script ordering permits
the risk tested here if application or worker writes continue during that
interval. This inspection and the isolated database test do not establish that
a deployment was run or that concurrent production writes actually occurred.

The restore helper stops backend and worker only when restore begins
(`ops/restore_postgres.sh`, lines 74–85); that later stop does not retroactively
include post-snapshot commits in the dump. Existing G5 CI recovery drills test
the backup and restore scripts and their safety checks, but they do not
establish a pre-snapshot barrier for all application writers.

## Required barrier contract (not implemented here)

Before a recovery snapshot is taken, a protected release needs a coordinated,
fail-closed barrier with these invariants:

1. Cover every write path, including HTTP requests, WebSocket events, workers,
   scheduled jobs, and administrative tasks, across every running instance.
2. Stop admission of new writes and drain or resolve in-flight transactions;
   confirm this state before taking the snapshot.
3. Keep the barrier active through backup, release mutation, migration, health
   checks, and any rollback. Do not reopen writes until the candidate release
   or restored previous release has been verified.
4. If the barrier, snapshot, deployment, or recovery cannot be verified, remain
   closed to writes and record a recovery-required state.

An alternative catch-up/replay mechanism would need equivalent evidence that
every confirmed post-snapshot write is preserved. The advisory-lock test is
not such integration evidence: using the primitive in PostgreSQL does not
make application writers participate automatically.

## Results and limitations

Observed in the isolated runner on 2026-11-22:

- `pytest -q tests/test_bm0093_write_barrier_postgres.py`: **3 passed, 4
  warnings in 8.55 seconds**.
- PostgreSQL image: `postgres:15-alpine`,
  `sha256:6dd85ce89ef213831bb1381f41e31c252e89b98676f33e2dcc1dcb273a2083a5`.
- The fixture removed both disposable containers after the run. No remote
  environment or live database was accessed.

These results reproduce snapshot exclusion and validate the advisory-lock
ordering only. They neither close issue #174 nor certify G5, RPO/RTO, a complete
deployment rollback, or the required application-wide barrier.
