# G5 adoption observer (observation only)

`ops.g5_adoption_observer` collects independently observed, read-only host
evidence. Because this repository cannot authenticate the routes loaded by
Nginx workers, it returns `PartialHostInventory` from `observe_partial`;
`observe` raises `ObservationBlocked` with those partial observations instead
of manufacturing the planner's `HostInventory`. It has no production CLI,
does not enable the G5 deployment adapter, and cannot authorize backup,
restore, writer reopening, or publication of metadata. The planner remains
`NO_GO_PLAN_ONLY`; point-in-time observations are not a continuous barrier.

## Calling the collector

The entry points are `observe_partial(ObserverRequest, runner=..., clock=...)`
and `observe(ObserverRequest, runner=..., clock=...)`.
The request supplies the checkout, env file, Compose files, and project name.
The runner accepts an argv sequence plus timeout and output limits and returns
stdout. The default runner is restricted to GitHub Actions, a local Unix Docker
socket, and a unique fixture project; it uses argv without a shell, no stdin,
a 20-second per-command timeout, bounded output, and process-group cleanup on
timeouts. Tests replace it with a deterministic in-memory fixture; command
errors and stderr are never copied into observer errors. This default runner
is not a general-purpose host collector.

Each collection independently checks the full Git SHA and clean worktree,
resolved Compose configuration, all project containers (including stopped
one-shots and orphans), Compose labels, container/image IDs and image source
revision, actual network membership, mounts and published ports, and the
PostgreSQL volume. Container `ps` IDs must exactly match full inspect IDs;
actual network member IDs, aliases, and unique addresses must exactly match
the inspected containers. Service hashes are compared with `docker compose
config --hash`. Effective backend/worker URLs and migration/seed URLs must
match their respective roles; runtime entrypoint, command, environment,
privilege settings, ports, mounts, images, and PG connection roles are checked
against the effective Compose configuration. Compose and runtime identities
are collected twice. Missing fields, unknown services, extra
network/route/port/mounts, duplicates, backend/worker divergence, command
failures, or drift block the observation.

PostgreSQL evidence is from the live PG15 instance: the maintenance connection
reports its authenticated role, database OID, `system_identifier`, and server
version in the PostgreSQL 15 range and must be a superuser maintenance
connection. Backend and worker each open fresh, read-only SQLAlchemy
connections using their actual runtime `DATABASE_URL`; the returned
`current_user`, `session_user`, database OID, and server IP must match the
statically validated role split and inspected database container. No URL,
password, complete environment, SQL dump, or user-table data is returned or
logged.
`schema_sha256` hashes only the source-side `pg_dump --schema-only
--no-owner --no-privileges` output. PostgreSQL's randomized, paired
`\restrict`/`\unrestrict` guard token is normalized to a fixed marker before
hashing; all other dump bytes are retained. The guard pair must be complete
and match. This is a source catalog export fingerprint; it is not a data
checksum and is not interchangeable with a restored catalog's deparsed schema
fingerprint.

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
When `.release.env` is present, its private values are compared in memory
against observed database roles/settings and effective application image
references; values are never returned or logged. A leftover `.release.env.next`
or `.release.env.previous` is fail-closed: the current `ops/deploy_remote.sh`
removes `.release.env.previous` on successful completion, so a surviving
transient is not treated as an ordinary completed release. Malformed, unknown,
non-terminal, or racing metadata blocks collection. A missing `.release-sha`
is reported as absent only when no legacy/G5 state suggests an existing
installation; it is never inferred from the checkout or container labels.

## Tests and later CI integration

Run the Docker-free command fixture and focused tests with:

```text
python -m pytest -q -o addopts= tests/test_g5_adoption_observer.py
```

`ComposeFixtureRunner` returns synthetic command responses and never starts a
container, opens a socket, or contacts a host. Its inventory-assembly test is
not successful runtime evidence. `tests/test_g5_adoption_observer_ci.py` runs a
separate live rehearsal only when GitHub Actions, CI, and the local Docker
socket are present. It creates a unique disposable Compose project with
PostgreSQL 15, separate database roles, no published ports, and an isolated
temporary checkout-independent configuration. It checks two observed
checkout/Compose/cluster snapshots, disconnects its own worker from the
fixture network, and requires the next observation to reject that mutation.
Cleanup discovers resources only through the fixture's unique ownership label
and verifies that label before removal. Test-built app images intentionally
lack registry digest provenance, so their absence is an explicit partial
evidence blocker, not a successful image-provenance assertion.

The fixture enables Caddy's admin endpoint only inside its private, temporary
container network so the collector can inspect Caddy's active configuration.
It publishes no ports and makes no TLS claim. Nginx's loaded worker routes are
still unauthenticated, so even a clean live rehearsal remains partial and can
never produce a complete `HostInventory`. The workflow was not edited; the
live test runs as part of the existing backend pytest job when that job is
authorized. The observed `action_required` Actions run exposed zero jobs and
therefore supplied no CI log or successful Actions result. No point-in-time
observation establishes continuous writer exclusion or authorizes backup,
restore, writer reopening, or metadata publication.
