# G5 edge provenance rehearsal

## Status and scope

This is a disposable, controlled-startup rehearsal for the edge path
`Caddy → Nginx → backend/frontend`. Its result is always **NO-GO** for staging
or production. It does not activate G5, change a live route, open Caddy's admin
API, inspect a legacy Nginx process, or establish that a previous host process
loaded any particular configuration.

The implementation is limited to this rehearsal, its provenance checks, tests,
and this document. It does not change deployment files or workflows.

## Evidence from controlled startup

`ops/ci_g5_edge_provenance.py` is intended for a trusted push or manual
dispatch on this repository's GitHub-hosted runner. It rejects pull-request
events and non-hosted runners. Run it from a trusted CI step with:

```sh
python ops/ci_g5_edge_provenance.py
```

It creates a uniquely labelled Docker bridge network marked `internal`, with
no published ports. The public proxy images are pulled by immutable OCI index
digest. Backend and frontend images are built from the checked-out source,
then run and recorded by Docker image ID; the source revision and source-tree
hashes are included in the output.

The rehearsal derives proxy configs from the checked-out Caddyfile and Nginx
config, applies only the internal listener/host changes needed for the isolated
network, and hashes the resulting bytes. The separately generated frontend
config is also hashed. All config bind mounts are read-only; includes/imports
are rejected. Caddy is started with `admin off` and without `--watch`. Nginx
and Caddy run as container PID 1 with exact arguments; all containers use a
read-only root filesystem, non-root UID, dropped capabilities, no restart
policy, and memory/CPU/PID limits. The only writable locations are explicit
ephemeral `tmpfs` mounts. No container publishes a host port.

Before probes, the runner records and verifies container IDs, image IDs,
PID-1 arguments and UID, read-only mounts, network ID and aliases, and the
internal bridge settings. It then verifies the HTTP health path, the real
FastAPI `/api/health` route, the real built frontend, and a real Engine.IO
WebSocket handshake through Caddy and Nginx to the application's Socket.IO
server. The Socket.IO test intentionally uses an invalid token and expects the
application's authentication rejection; it does not manufacture a success or
require a production/database credential.

Adversarial checks reject a changed route/config digest and a replacement
Caddy container, even if it uses the same image and mounts. The fixture is
stopped and removed by its unique label, and cleanup verifies its containers
and network are gone. The JSON report records content/runtime identities and
limitations; successful probes are not treated as proof of the loaded
configuration.

## Retrospective host observation is a different evidence class

An image tag, a later file hash, `docker inspect` after the fact, an HTTP
response, or a WebSocket response cannot by itself prove which configuration
an already-running legacy process loaded. `nginx -T` is not used. No Nginx
introspection endpoint or Caddy admin API is enabled. `legacy_host_observation`
labels such facts as inconclusive and explicitly sets both
`proves_loaded_configuration` and `proves_absence_of_bypass` to false.

The controlled-startup report demonstrates only the exact disposable launch
that it observed. Its probes cover selected paths; they cannot establish the
absence of alternate listeners, network paths, or bypasses.

## Trust and operational limits

Access to the Docker socket is effectively root-equivalent on the runner. The
checks reduce the fixture's container privileges but cannot constrain a
malicious or compromised Docker daemon or runner. Run only on an isolated,
disposable GitHub-hosted runner under trusted repository control; do not make
the fixture available to untrusted pull-request code, self-hosted agents, or
production hosts. The CI environment checks are guardrails, not cryptographic
proof of runner identity.

The proxy image digests pin the registry content used by this rehearsal. The
application image IDs pin the built artifacts for this run, not the
reproducibility or provenance of every upstream package/base-image input.
There is no signing or external attestation in scope.

This evidence does not certify the legacy VPS, route activation, write drain,
production readiness, or absence of bypass. It cannot authorize activation;
the outcome remains **NO-GO**.
