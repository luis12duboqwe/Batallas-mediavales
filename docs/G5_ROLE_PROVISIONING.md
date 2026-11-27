# G5 role provisioning — incomplete

**NO-GO.** No role provisioner or runnable CI rehearsal has been implemented.
`ops/ci_g5_role_provisioning.py` only records a preliminary table-name policy
and provides a read-only name comparison. It does not grant, revoke, migrate,
back up, fence, or validate database privileges. It must not be used to
authorize a cutover or to claim continuous exclusion of writers.

The explicit fixture list excludes `alembic_version`, administrative logs,
support and anti-cheat tables. Unknown or missing table names are rejected.
The list is preliminary: excluding internal tables may break application
features that use them. A complete drill must prove its chosen policy against
actual runtime behavior rather than assume this list is sufficient.

Outstanding work includes exact-SHA images and an existing populated 0019
database, identity and verified backup, a strict catalog/ownership/ACL audit
(including `pg_default_acl` and sequence ownership), privilege provisioning
and retry checks, privileged inventory before and after the persistent fence,
real 0020 migration and seed, runtime and denial checks, data preservation,
and isolated resource cleanup. Catalog observations alone cannot prove
continuous exclusion of privileged writers. The stock PG15 permission-checked
`PUBLIC UPDATE` on `pg_settings` must not be mistaken for an arbitrary grant.
