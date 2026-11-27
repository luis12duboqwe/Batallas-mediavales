# G5 adoption observer (observation only)

`ops.g5_adoption_observer` converts independently collected, read-only host
evidence into the existing `HostInventory` and `HostObservations` types from
`ops.g5_adoption_plan`. It has no production CLI, does not enable the G5
deployment adapter, and cannot authorize backup, restore, writer reopening, or
publication of metadata. The planner remains `NO_GO_PLAN_ONLY`; a pair of
point-in-time observations is not a continuous barrier.

## Calling the collector

The public entry point is `observe(ObserverRequest, runner=..., clock=...)`.
The request supplies the checkout, env file, Compose files, and project name.
The runner accepts an argv sequence plus timeout and output limits and returns
stdout. The default runner calls `subprocess.run` with `shell=False`, no stdin,
a 20-second per-command timeout, and bounded accepted output. Tests replace it
with a deterministic in-memory fixture; command errors and stderr are never
copied into observer errors.

Each collection independently checks the full Git SHA and clean worktree,
resolved Compose configuration, all project containers (including stopped
one-shots and orphans), Compose labels, container/image IDs and image source
revision, actual network membership, mounts and published ports, and the
PostgreSQL volume. Compose configuration and runtime identities are collected
twice. Any missing field, unknown service, extra network/route/port/mount,
duplicate, backend/worker image difference, command failure, or drift blocks
the observation.

PostgreSQL evidence is from the live PG15 instance: the maintenance connection
reports its authenticated role, database OID, `system_identifier`, and server
version. The backend container opens a separate read-only SQLAlchemy connection
using its actual runtime `DATABASE_URL`; the returned `current_user` and
`session_user` must match the statically validated split. No URL, password,
complete environment, SQL dump, or user-table data is returned or logged.
`schema_sha256` hashes only the source-side `pg_dump --schema-only
--no-owner --no-privileges` output. This is a source catalog fingerprint; it
is not a data checksum and is not interchangeable with a restored catalog's
deparsed schema fingerprint.

The deterministic `compose_sha256` hashes canonicalized `docker compose
config --format json` output and selected Compose provenance labels. The
resolved config includes environment values and can therefore include
passwords, tokens, and other sensitive values. Only the digest is stored in
the inventory, but it can still be sensitive to dictionary guessing; treat it
as restricted attestation, do not publish it, and do not assume hashing
anonymizes configuration. The collector does not print the digest or raw
resolved configuration.

The Docker named-volume name, Compose labels, driver, and actual database
mount are used as PostgreSQL volume identity. Docker does not provide a
content-independent UUID for a local named volume; this name is not proof of
the volume's data contents.

## Proxy and metadata limits

Caddy evidence is read from its admin API's loaded configuration, not from the
desired Caddyfile. The collector recognizes only one loaded reverse-proxy
route to `nginx:80`. It leaves `tls_ready=False`: a config observation is not
a TLS handshake.

Nginx does not expose a standard read-only API for its in-memory loaded
configuration. `nginx -T` only parses the files currently on disk and is not
accepted as proof of what worker processes loaded. A JSON endpoint that says
`source: "loaded-runtime"` or returns a hash is also not trusted unless the
hash and route table are verifiably bound to the active workers. No such
mechanism exists in this repository. Therefore the collector always returns
an explicit blocker after observing Caddy; it does not fabricate an
`EdgeObservation` from an Nginx file or self-attesting endpoint. The live
Caddy route parser is tested, but the full synthetic Compose fixture replaces
the proxy collector and is only an inventory-assembly test, not successful
runtime evidence.

Release metadata is read without creating `.ops-state` or `deploy.lock`.
When present, the existing safe `deploy.lock` is opened read-only and held
with a non-blocking shared lock; a busy, missing, unsafe, or replaced lock
blocks non-absent metadata. Existing G5 state is classified through
`g5_incident_inspect.inspect_incident` and rechecked under shared read locks.
`.release.env` is checked only for safe file metadata and is never read.
Malformed, unknown, non-terminal, or racing metadata blocks collection. A
missing `.release-sha` is reported as absent only when no legacy/G5 state
suggests an existing installation; it is never inferred from the checkout or
container labels.

## Tests and later CI integration

Run the executable, Docker-free command fixture and focused tests with:

```text
python -m pytest -q -o addopts= tests/test_g5_adoption_observer.py
```

`ComposeFixtureRunner` returns synthetic command responses and never starts a
container, opens a socket, or contacts a host. Its inventory-assembly test
injects a synthetic edge observation and is not a successful runtime
observation or real environment rehearsal. The default collector must block
until trusted loaded-Nginx introspection can be implemented and independently
verified.

Later CI integration must run only on a GitHub-hosted runner and create
disposable, project-owned Compose resources with no published ports. The CI
fixture must use PostgreSQL 15, distinct effective app/maintenance identities,
immutable images, and independently observe the currently loaded Caddy and
Nginx route tables. It must clean up only those disposable resources. The
workflow was intentionally not changed here; a successful CI observation
still would not establish continuous writer exclusion or authorize a
backup/restore/reopen step.
