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
checkout `1e022819f9bce3381751fa10512b36b7cdcbc544` with uncommitted laboratory
changes. The final local run exited 0 with script SHA-256
`46a7f28bc160bf8f8a52bfde79770934e4e2005b36b1ff2a0c4141ca5a84bc1b`
before and after execution. It exercised historical gameplay, support and
privacy HTTP routes, archive listing, real 0020 migration and seed, grant
checks and persistent fence. This was not an official GitHub Actions run and
did not test worker behavior or backup restoration.

## Ampliación de mantenimiento

Se reutiliza el recibo Snapshot de #206 (archivo 0600, fsync, identidad y hash verificados antes y después). Los grants nombrados se aplican en una única transacción y se observa inventario antes/después. Se prueban las dos imágenes históricas/candidata con cuentas distintas, HTTP de juego/soporte/privacidad y worker real: completar la cola de almacén bajo el rol runtime y verificar persistencia SQL. La candidata se abre únicamente en el runner desechable, en una sola transacción SQL para restaurar límite y LOGIN, y se vuelve a cerrar en finally; se verifica que las escrituras históricas sobreviven. CI obligatoria de imágenes y revisión independiente pendientes. No se afirma mínimo privilegio exhaustivo ni se restaura una base real. La restauración independiente se ensaya en #221, fuera de este scope.

### Permiso de bloqueo del catálogo de héroe (revisión P2)

La consulta de equipamiento usa FOR UPDATE sobre HeroItem JOIN ItemTemplate en ambas imágenes. El ensayo otorga SELECT, UPDATE sobre item_templates (sin INSERT/DELETE) como límite experimental compatible con las versiones inmutables. No es una autorización para producción; la política final deberá reducir ese permiso, por ejemplo limitando el bloqueo a HeroItem en el código y verificando la transición histórica. Se añaden pruebas HTTP reales en ambas versiones: creación de héroe, dos objetos sintéticos del mismo slot, equipar, sustituir, rechazar ID inválido, desequipar y comprobar estado SQL. Revisados los catálogos de quests, logros, temas, tienda y aventuras: quests están retiradas y temas/tienda no se registran como routers activos; no se amplían sus grants por código inactivo. Falta nueva CI y revisión independiente.
