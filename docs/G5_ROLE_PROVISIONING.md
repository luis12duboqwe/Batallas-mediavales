# G5 role provisioning — incomplete

**NO-GO.** No role provisioner or runnable CI rehearsal has been implemented.
`ops/ci_g5_role_provisioning.py` only records a preliminary table-name policy
and provides a read-only name comparison. It does not grant, revoke, migrate,
back up, fence, or validate database privileges. It must not be used to
authorize a cutover or to claim continuous exclusion of writers.

The name inventory distinguishes the migration ledger (`alembic_version`)
from runtime tables, including the administrative, support and anti-cheat
tables. Unknown or missing table names are rejected. This is only a list of
names; it does not prescribe or verify grants. Runtime call sites establish
at least the following operations:

| Table | Observed operations and evidence |
| --- | --- |
| `support_cases` | SELECT, INSERT, UPDATE: `services/support.py`, `routers/account_data.py`, `services/account_export.py` |
| `logs` | SELECT, INSERT, UPDATE: `services/anticheat.py`, `services/admin.py`, `services/achievement.py`; DELETE through the user ORM cascade in `models/user.py` |
| `anti_cheat_rate_buckets` | SELECT, INSERT, UPDATE: `services/anticheat.py` |
| `anti_cheat_flags` | SELECT, INSERT, UPDATE: `services/anticheat.py`, `routers/anticheat.py` |
| `admin_bot_logs` | SELECT, INSERT: `services/admin_bot.py`, `routers/admin_bot.py` |

These are observed operations, **not an exhaustive minimum privilege
policy**. Cascades and other code paths require further review and real
runtime testing. The application uses one shared SQL identity, so its SQL
privileges cannot distinguish an administrator's request from an ordinary
player's request. Application-level authorization remains essential.

Outstanding work includes exact-SHA images and an existing populated 0019
database, identity and verified backup, a strict catalog/ownership/ACL audit
(including `pg_default_acl` and sequence ownership), privilege provisioning
and retry checks, privileged inventory before and after the persistent fence,
real 0020 migration and seed, runtime and denial checks, data preservation,
and isolated resource cleanup. Catalog observations alone cannot prove
continuous exclusion of privileged writers. The stock PG15 permission-checked
`PUBLIC UPDATE` on `pg_settings` must not be mistaken for an arbitrary grant.
