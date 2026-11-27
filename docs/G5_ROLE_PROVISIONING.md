# G5 — laboratorio de aprovisionamiento de rol

**NO-GO.** `ops/ci_g5_role_provisioning.py` is an isolated GitHub-hosted CI
laboratory, not a host provisioner or authorization for a cutover. It uses
synthetic credentials and a private PostgreSQL 15 fixture; it must never be
used against real data or a shared Docker daemon.

The script requires `CI=true`, `GITHUB_ACTIONS=true` and
`RUNNER_ENVIRONMENT=github-hosted`, the exact historical commit
`eafc5bbd5fdc9caad698db48cbb8ad80df942f0e` in the local Git history, and
local `postgres:15-alpine` and `python:3.11-slim` images. The Python base must
have an inspectable immutable repository digest. Run on a disposable runner:

```sh
python -m ops.ci_g5_role_provisioning
```

The fixture builds the previous and candidate backend images from exact
worktrees, seeds revision 0019, checks identity and stores a private custom
format dump, then creates the application role. It checks catalog ownership,
object kinds and ACLs, default privileges and attached sequences, observes
the privileged inventory, and uses the persistent fence before the actual
0020 migration and seed. Unexpected state is rejected rather than repaired.
The inventory and fence are observations, not proof of continuous exclusion
of privileged writers. On failure the fixture is preserved for reconciliation;
on success the isolated fixture is removed.

The laboratory policy grants individually listed table privileges and
`USAGE, SELECT` on attached sequences; it excludes `alembic_version`, revokes
public schema `CREATE` and cross-database `CONNECT`, and does not grant
ownership, DDL, role administration or maintenance privileges. The current
policy still gives all four DML operations to many gameplay tables; **it is
not a demonstrated minimum-privilege policy**. Neither an archive listing
nor a hash establishes a successful restore. Historical HTTP probes exercise
gameplay, support and privacy routes and authorization between fixture users;
they do not establish candidate worker behavior or comprehensive coverage.

The name inventory distinguishes the migration ledger (`alembic_version`)
from runtime tables, including the administrative, support and anti-cheat
tables. Unknown or missing table names are rejected, and the fixture checks
the catalog against its experimental grants. Runtime call sites establish at
least the following operations:

| Table | Observed operations and evidence |
| --- | --- |
| `support_cases` | SELECT, INSERT, UPDATE: `services/support.py`, `routers/account_data.py`, `services/account_export.py` |
| `logs` | SELECT, INSERT, UPDATE: `services/anticheat.py`, `services/admin.py`, `services/achievement.py`; DELETE through the user ORM cascade in `models/user.py` |
| `anti_cheat_rate_buckets` | SELECT, INSERT, UPDATE: `services/anticheat.py` |
| `anti_cheat_flags` | SELECT, INSERT, UPDATE: `services/anticheat.py`, `routers/anticheat.py` |
| `admin_bot_logs` | SELECT, INSERT: `services/admin_bot.py`, `routers/admin_bot.py` |
| `wonder_funding` (0020) | SELECT, INSERT, UPDATE: `services/wonder_funding.py` |
| `wonder_contributions` (0020) | SELECT, INSERT: `services/wonder_funding.py` |

These are observed operations, **not an exhaustive minimum privilege
policy**. Cascades and other code paths require further review and real
runtime testing. The application uses one shared SQL identity, so its SQL
privileges cannot distinguish an administrator's request from an ordinary
player's request. Application-level authorization remains essential.
The scheduler also uses PostgreSQL advisory locks (`app/scheduler.py`) and
the worker invokes gameplay writes; successful simple SQL checks alone do not
establish that the shared runtime role can perform the real workload.

Outstanding work includes a complete per-table ORM and worker privilege audit,
candidate worker/HTTP tests, broader negative controls, and independent restore
verification. Catalog observations alone cannot prove continuous exclusion of
privileged writers. The stock PG15 permission-checked `PUBLIC UPDATE` on
`pg_settings` must not be mistaken for an arbitrary grant. No workflow or
deployment integration is included.

## Sandbox result

The laboratory ran locally with synthetic CI guard variables and candidate
checkout `1e022819f9bce3381751fa10512b36b7cdcbc544`, exiting 0 after the
historical write, archive listing, real 0020 migration and seed, grant checks
and persistent fence. This was not an official GitHub Actions run. A subsequent
local run also exercised historical gameplay, support and privacy HTTP routes.
Neither run tested worker behavior or backup restoration. The later changes
moving the temporary workspace to `/tmp` and adding positive owner-detail
checks were not included in those runs.
