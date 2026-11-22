# G5 Nginx edge maintenance gate

## Scope and behavior

Caddy remains the public TLS edge and continues to proxy to internal Nginx.
Nginx checks the local `./.ops-state/edge-maintenance/open` marker on every
request to `/api`, `/api/`, `/socket.io`, and `/socket.io/`. The control
directory is mounted read-only in the Nginx container. The only open signal is
a readable, regular, non-symlink file named `open`; its contents are ignored.
A missing marker, unreadable file, directory in its place, or symlink is
closed. Closed requests receive `503`, `Retry-After: 60`, and
`Cache-Control: no-store`. The check is local and
does not depend on request headers, cookies, client IPs, or URL parameters.

The internal `/health` endpoint remains a `200` liveness probe in either mode.
Requests to the slashless API and Socket.IO paths are gated before their
redirects, so a closed edge does not redirect clients around the maintenance
response. An open edge retains the existing routes, rate limit, and WebSocket
upgrade proxying.

## Local operation

The Compose bind mount is `./.ops-state/edge-maintenance` on the host. A missing
directory or marker starts closed. Close admission by removing the marker:

```sh
rm -f .ops-state/edge-maintenance/open
```

Only recreate it after the responsible recovery process has established that
reopening is safe. Create it atomically on the same filesystem so Nginx sees
either the closed state or the complete regular file:

```sh
dir=.ops-state/edge-maintenance
mkdir -p "$dir"
# The deployment manager uses umask 077. Nginx workers need read/traverse
# access to this host-controlled bind-mounted directory, never write access.
chmod 0755 "$dir"
tmp="$(mktemp "$dir/.open.XXXXXX")"
chmod 0644 "$tmp"
mv -f "$tmp" "$dir/open"
```

The directory is host-controlled; the read-only mount prevents Nginx from
changing the control state. Nginx evaluates the marker for each new request, so
changing it does not reload Nginx or restart Compose services. A failed
configuration reload is not part of this control path. If Nginx is unavailable
or cannot read a valid marker, it cannot admit requests; a service restart
starts closed whenever the marker is absent or invalid. An intentionally
present marker remains an explicit open signal across a restart, so recovery
operations must remove it before rebooting/restarting the edge.

## Limits and recovery integration

This is an admission gate, not a transactional maintenance barrier (no
constituye una barrera transaccional). Requests that passed the check before it
closes may still be executing. A `503` during a WebSocket handshake prevents a
new connection, but does not terminate an already-established WebSocket; close
those sessions by stopping the backend and worker as part of maintenance and
recovery.

The gate alone does not establish that database writers are stopped or that a
durable recovery state is clear. The deployment/recovery orchestrator must
close the gate, stop backend and worker writers, verify the database and
durable recovery state, and only then recreate the marker. Until that
integration exists and is verified, this does not enable staging or production
and issue #174 remains P1.
