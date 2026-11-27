"""Disposable GitHub CI-only role-provisioning laboratory, not a deploy tool.

The policy is deliberately limited to the reviewed 0019/0020 fixture and
does not authorize provisioning a real database or prove universal fencing.
It requires local postgres:15-alpine and python:3.11-slim images; the latter
must have an unambiguous immutable repository digest. It does not pull images.
Backend builds can require dependency downloads, as in the release helper.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from uuid import uuid4

from ops.g5_pg15_writer_fence import Pg15FenceTarget


PREVIOUS = "0019_privacy_active_unique"
CANDIDATE = "0020_wonder_funding"

# These sets describe names only, not a reviewed SQL privilege policy.
GAME_TABLES = frozenset({
    "achievement_progress", "achievements", "adventures", "alliance_chat_messages",
    "alliance_invitations", "alliance_members", "alliances", "building_queue",
    "buildings", "chat_messages", "cities", "diplomacy", "forum_posts",
    "forum_threads", "hero_items", "heroes", "item_templates", "map_bookmarks",
    "market_offers", "messages", "movements", "notifications", "oases",
    "player_world", "premium_status", "quest_progress", "quests", "reports",
    "research", "research_queue", "season_results", "seasons", "shop_items",
    "spy_reports", "themes", "troop_queue", "troops", "user_blocks",
    "user_items", "user_themes", "users", "wiki_articles", "world_events", "worlds",
})
INTERNAL_TABLES = frozenset({
    "admin_bot_logs", "alembic_version", "anti_cheat_flags",
    "anti_cheat_rate_buckets", "logs", "support_cases",
})
NEW_TABLES = frozenset({"wonder_contributions", "wonder_funding"})

# Runtime code also uses tables previously mistaken for maintenance-only data.
# These are observed operations, not a complete privilege specification: ORM
# cascades and other call paths can require additional operations.
OBSERVED_INTERNAL_OPERATIONS = {
    "support_cases": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "logs": frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"}),
    "anti_cheat_rate_buckets": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "anti_cheat_flags": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "admin_bot_logs": frozenset({"SELECT", "INSERT"}),
}
OBSERVED_WONDER_OPERATIONS = {
    "wonder_funding": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "wonder_contributions": frozenset({"SELECT", "INSERT"}),
}


class ObjectPolicyError(RuntimeError):
    """Unrecognized or unsafe catalog evidence."""


def expected_tables(revision: str) -> frozenset[str]:
    if revision == PREVIOUS:
        return GAME_TABLES | INTERNAL_TABLES
    if revision == CANDIDATE:
        return GAME_TABLES | INTERNAL_TABLES | NEW_TABLES
    raise ObjectPolicyError("unrecognized schema revision")


def allowed_tables(revision: str) -> frozenset[str]:
    """Names used by runtime code; not permission to grant any privileges."""
    return expected_tables(revision) - {"alembic_version"}


def validate_table_names(revision: str, names) -> None:
    """Reject missing, duplicate or unrecognized ordinary table names.

    The caller must independently verify relation kinds, ownership, ACLs,
    sequences, default privileges and all other topology. This check is not
    a substitute for the privileged inventory or an exclusion fence.
    """
    expected = expected_tables(revision)
    if (not isinstance(names, (list, tuple))
            or any(not isinstance(name, str) for name in names)
            or len(names) != len(set(names)) or set(names) != expected):
        raise ObjectPolicyError("table inventory does not match the reviewed revision")


def inspect_tables(target: Pg15FenceTarget, session, revision: str) -> None:
    """Read table names in a fresh read-only PG15 maintenance session.

    This preliminary check neither checks nor changes any grants.
    """
    if not isinstance(target, Pg15FenceTarget):
        raise ObjectPolicyError("invalid inventory target")
    expected_tables(revision)
    statement = (
        "SELECT c.relname || '|' || c.relkind::text FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') "
        "ORDER BY c.relname;"
    )
    try:
        result = session.query(target.database, statement)
    except Exception:
        raise ObjectPolicyError("table inventory unavailable") from None
    if not isinstance(result, str):
        raise ObjectPolicyError("table inventory unavailable")
    rows = result.splitlines()
    parsed = [row.split("|") for row in rows]
    if any(len(row) != 2 or row[1] != "r" for row in parsed):
        raise ObjectPolicyError("unexpected relation kind")
    validate_table_names(revision, [row[0] for row in parsed])


def table_privileges(revision: str) -> dict[str, frozenset[str]]:
    """Conservative experimental fixture grants, not a complete runtime policy.

    The historical game surface has not been exhaustively audited. The
    mutable-table CRUD grants below are an upper bound, not a least-privilege
    certification; runtime paths outside the exercised probes may fail.
    """
    expected_tables(revision)
    read_only = {
        "achievements", "item_templates", "quests", "shop_items", "themes",
    }
    grants = {name: frozenset({"SELECT"}) for name in read_only}
    grants.update({name: frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})
                   for name in GAME_TABLES - read_only - {"wiki_articles"}})
    grants["wiki_articles"] = frozenset({"SELECT", "INSERT", "UPDATE"})
    grants.update(OBSERVED_INTERNAL_OPERATIONS)
    if revision == CANDIDATE:
        grants.update(OBSERVED_WONDER_OPERATIONS)
    if set(grants) != allowed_tables(revision):
        raise ObjectPolicyError("incomplete table privilege policy")
    return grants


def _require_fixture_target(target):
    if target != Pg15FenceTarget("game_migration_ci", "game_app", "postgres"):
        raise ObjectPolicyError("invalid disposable fixture identity")


def inspect_objects(target, session, revision, *, granted_revision=None):
    """Reject unknown topology and foreign or excessive ACLs, including columns."""
    _require_fixture_target(target)
    if granted_revision not in (None, PREVIOUS, CANDIDATE):
        raise ObjectPolicyError("invalid expected grant state")
    if granted_revision == CANDIDATE and revision != CANDIDATE:
        raise ObjectPolicyError("invalid expected grant transition")
    inspect_tables(target, session, revision)
    policy = table_privileges(revision)
    prior = table_privileges(granted_revision) if granted_revision else {}
    sql = """
    SELECT json_build_object(
      'schemas', (SELECT COALESCE(json_agg(nspname ORDER BY nspname),'[]'::json)
        FROM pg_namespace WHERE left(nspname, 3) <> 'pg_'
        AND nspname <> 'information_schema'),
      'defaults', (SELECT count(*) FROM pg_default_acl),
      'routines', (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public'),
      'required_sequences', (SELECT COALESCE(json_agg(DISTINCT s.relname),'[]'::json)
        FROM pg_class s JOIN pg_namespace n ON n.oid=s.relnamespace
        WHERE n.nspname='public' AND s.relkind='S' AND (
          EXISTS (SELECT 1 FROM pg_depend d JOIN pg_attrdef ad ON ad.oid=d.objid
            JOIN pg_depend own ON own.objid=s.oid AND own.classid='pg_class'::regclass
              AND own.refclassid='pg_class'::regclass AND own.deptype IN ('a','i')
              AND own.refobjid=ad.adrelid AND own.refobjsubid=ad.adnum
            WHERE d.classid='pg_attrdef'::regclass AND d.refclassid='pg_class'::regclass
              AND d.refobjid=s.oid AND d.deptype='n')
          OR EXISTS (SELECT 1 FROM pg_depend d JOIN pg_attribute a
            ON a.attrelid=d.refobjid AND a.attnum=d.refobjsubid
            WHERE d.classid='pg_class'::regclass AND d.objid=s.oid
              AND d.refclassid='pg_class'::regclass AND d.deptype='i'
              AND a.attidentity IN ('a','d')))),
      'foreign_sequence_defaults', (SELECT count(*) FROM pg_attrdef ad
        JOIN pg_depend d ON d.classid='pg_attrdef'::regclass AND d.objid=ad.oid
          AND d.refclassid='pg_class'::regclass AND d.deptype='n'
        JOIN pg_class s ON s.oid=d.refobjid AND s.relkind='S'
        WHERE NOT EXISTS (SELECT 1 FROM pg_depend own
          WHERE own.classid='pg_class'::regclass AND own.objid=s.oid
            AND own.refclassid='pg_class'::regclass AND own.deptype IN ('a','i')
            AND own.refobjid=ad.adrelid AND own.refobjsubid=ad.adnum)),
      'schema_app_acl', (SELECT COALESCE(json_agg(a.privilege_type),'[]'::json)
        FROM pg_namespace n CROSS JOIN LATERAL
          aclexplode(COALESCE(n.nspacl, acldefault('n', n.nspowner))) a
        WHERE n.nspname='public'
          AND a.grantee=(SELECT oid FROM pg_roles WHERE rolname='game_app')),
      'schema_ok', (SELECT nspowner = (SELECT oid FROM pg_roles WHERE rolname='pg_database_owner')
        AND NOT EXISTS (SELECT 1 FROM aclexplode(COALESCE(nspacl, acldefault('n', nspowner))) a
          WHERE a.grantee NOT IN (0, nspowner, (SELECT oid FROM pg_roles WHERE rolname='game_app'))
             OR (a.grantee<>nspowner AND a.is_grantable)
             OR (a.grantee=0 AND a.privilege_type <> 'USAGE')
             OR (a.grantee=(SELECT oid FROM pg_roles WHERE rolname='game_app')
                 AND a.privilege_type <> 'USAGE'))
        FROM pg_namespace WHERE nspname='public'),
      'objects', (SELECT COALESCE(json_agg(json_build_object(
        'name', c.relname, 'kind', c.relkind, 'owner', r.rolname,
        'column_acl', EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=c.oid
                               AND a.attacl IS NOT NULL),
        'attached', (SELECT COALESCE(json_agg(t.relname ORDER BY t.relname),'[]'::json)
          FROM pg_depend d JOIN pg_class t ON t.oid=d.refobjid
          JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid
          WHERE d.classid='pg_class'::regclass AND d.objid=c.oid
            AND d.refclassid='pg_class'::regclass AND d.deptype IN ('a','i')),
        'acl', (SELECT COALESCE(json_agg(json_build_array(
          CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE gr.rolname END,
          x.privilege_type, x.is_grantable, grantor.rolname)), '[]'::json)
          FROM aclexplode(COALESCE(c.relacl, acldefault(
            CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,
            c.relowner))) x LEFT JOIN pg_roles gr ON gr.oid=x.grantee
          LEFT JOIN pg_roles grantor ON grantor.oid=x.grantor)
        ) ORDER BY c.relname),'[]'::json)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_roles r ON r.oid=c.relowner
        WHERE n.nspname='public' AND c.relkind NOT IN ('i','I','t'))
    )::text;
    """
    try:
        value = json.loads(session.query(target.database, sql))
        if (value["schemas"] != ["public"] or value["defaults"] != 0
                or value["routines"] != 0 or value["foreign_sequence_defaults"] != 0
                or value["schema_ok"] is not True):
            raise ObjectPolicyError("unexpected schema or default privileges")
        if sorted(value["schema_app_acl"]) != (["USAGE"] if granted_revision else []):
            raise ObjectPolicyError("schema grant state drift")
        objects = value["objects"]
        names = set()
        sequences = []
        for obj in objects:
            name, kind = obj["name"], obj["kind"]
            if name in names or obj["owner"] != target.maintenance_role or obj["column_acl"]:
                raise ObjectPolicyError("unexpected object ownership or column ACL")
            names.add(name)
            if kind == "r" and name in expected_tables(revision):
                allowed = policy.get(name, frozenset())
                expected = prior.get(name, frozenset())
            elif kind == "S" and len(obj["attached"]) == 1 and obj["attached"][0] in policy:
                allowed = frozenset({"USAGE", "SELECT"})
                expected = allowed if obj["attached"][0] in prior else frozenset()
                sequences.append(name)
            else:
                raise ObjectPolicyError("unexpected object or sequence attachment")
            actual = set()
            owner = set()
            seen = set()
            for grantee, privilege, grantable, grantor in obj["acl"]:
                if ((grantee, privilege) in seen or grantor != target.maintenance_role
                        or type(grantable) is not bool):
                    raise ObjectPolicyError("unexpected duplicate or grantor")
                seen.add((grantee, privilege))
                if grantee == target.maintenance_role:
                    if grantable:
                        raise ObjectPolicyError("unexpected owner grant option")
                    owner.add(privilege)
                    continue
                if grantee != target.application_role or grantable or privilege not in allowed:
                    raise ObjectPolicyError("unexpected object grant")
                actual.add(privilege)
            owner_expected = {"USAGE", "SELECT", "UPDATE"} if kind == "S" else {
                    "SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER",
                }
            if owner != owner_expected:
                raise ObjectPolicyError("owner grant state drift")
            if actual != expected:
                raise ObjectPolicyError("object grant state drift")
        if not expected_tables(revision).issubset(names):
            raise ObjectPolicyError("missing objects")
        if set(sequences) != set(value["required_sequences"]):
            raise ObjectPolicyError("sequence ownership or default dependency mismatch")
        return sorted(sequences)
    except ObjectPolicyError:
        raise
    except Exception:
        raise ObjectPolicyError("object inventory unavailable or malformed") from None


def provision(target, admin, inventory, revision, *, granted_revision=None, fenced=False):
    """Apply only individually named grants after a fresh fail-closed inspection."""
    from ops.ci_g5_actual_migration import Admin
    from ops.ci_g5_privileged_inventory import IsolatedAdmin
    from ops.ci_g5_release_transition import _container, _docker_json, _image

    _require_fixture_target(target)
    if (os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or type(admin) is not Admin or type(inventory) is not IsolatedAdmin
            or admin.container != inventory.container or type(fenced) is not bool):
        raise ObjectPolicyError("invalid disposable fixture executor")
    container = _container(admin.container)
    labels = container.get("Config", {}).get("Labels") or {}
    project = labels.get("medievol.g5.edge-fixture")
    networks = container.get("NetworkSettings", {}).get("Networks")
    if (not isinstance(project, str) or not re.fullmatch(r"bm-g5-edge-[0-9a-f]{32}", project)
            or not isinstance(networks, dict) or set(networks) != {project}
            or container.get("Image") != _image("postgres:15-alpine").get("Id")
            or container.get("HostConfig", {}).get("PortBindings")):
        raise ObjectPolicyError("database container identity mismatch")
    network = _docker_json("network", "inspect", project)
    if (network.get("Internal") is not True
            or (network.get("Labels") or {}).get("medievol.g5.edge-fixture") != project):
        raise ObjectPolicyError("database network identity mismatch")
    _inventory(target, inventory, fenced)
    sequences = inspect_objects(target, inventory, revision, granted_revision=granted_revision)
    if any(not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name) for name in sequences):
        raise ObjectPolicyError("unsafe sequence name")
    if granted_revision is None:
        admin.sql(f'GRANT USAGE ON SCHEMA public TO "{target.application_role}";', target.database)
    prior = table_privileges(granted_revision) if granted_revision else {}
    for name, privileges in sorted(table_privileges(revision).items()):
        if name in prior:
            continue
        admin.sql(f'GRANT {", ".join(sorted(privileges))} ON TABLE "{name}" '
                  f'TO "{target.application_role}";', target.database)
    for name in sequences:
        # Existing grants were verified exactly above; regranting is harmless.
        admin.sql(f'GRANT USAGE, SELECT ON SEQUENCE "{name}" '
                  f'TO "{target.application_role}";', target.database)
    inspect_objects(target, inventory, revision, granted_revision=revision)


def _inventory(target, session, fenced):
    from ops.g5_pg15_privileged_inventory import inspect_privileged_inventory

    observation = inspect_privileged_inventory(target, session, fenced=fenced)
    if observation.blockers:
        raise ObjectPolicyError("privileged inventory rejected the fixture")


def _sql_denial_probes(database):
    """Check selected stock PG15 denials; not a complete privilege audit."""
    from ops.ci_g5_actual_migration import app_command, expect_refused
    from ops.ci_g5_edge_admission import probe

    for statement, reason in (
        ("CREATE ROLE forbidden_ci NOLOGIN;", "permission denied to create role"),
        ("ALTER SYSTEM SET log_statement = 'none';",
         'permission denied to set parameter "log_statement"'),
        ("SELECT pg_catalog.pg_read_file('postgresql.conf');",
         "permission denied for function pg_read_file"),
        ("SELECT rolpassword FROM pg_catalog.pg_authid;",
         "permission denied for table pg_authid"),
    ):
        expect_refused(database, statement, reason)
    command = app_command(database, "SELECT 1;")
    command[command.index("-d") + 1] = "postgres"
    code, _, stderr = probe(command)
    if code == 0 or 'permission denied for database "postgres"' not in stderr:
        raise ObjectPolicyError("cross-database denial was not established")


_REGISTER_CLIENT = r'''
import httpx

with httpx.Client(base_url="http://127.0.0.1:8000", timeout=20, trust_env=False) as client:
    for name in ("g5_role_player", "g5_role_other", "g5_role_admin"):
        response = client.post("/auth/register", json={
            "username": name, "email": name + "@example.com",
            "password": "G5-Role-Fixture-Password-2026!"})
        if response.status_code != 200:
            raise RuntimeError("registration failed with status " + str(response.status_code))
print("registered")
'''


_HTTP_CLIENT = r'''
import json
import sys
import httpx

world = int(sys.argv[1])
password = "G5-Role-Fixture-Password-2026!"
with httpx.Client(base_url="http://127.0.0.1:8000", timeout=20, trust_env=False) as client:
    def request(method, path, expected, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code != expected:
            raise RuntimeError("HTTP probe failed: " + method + " " + path
                               + " expected " + str(expected) + " got "
                               + str(response.status_code))
        return response.json()

    tokens = []
    for name in ("g5_role_player", "g5_role_other", "g5_role_admin"):
        result = request("POST", "/auth/token", 200,
                         data={"username": name, "password": password})
        token = result.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("login did not issue a token")
        tokens.append({"Authorization": "Bearer " + token})
    player, other, admin = tokens
    membership = request("POST", "/worlds/" + str(world) + "/join", 200, headers=player)
    city = membership.get("starting_city_id")
    if type(city) is not int or city <= 0:
        raise RuntimeError("starting city missing")
    params = {"world_id": world, "city_id": city}
    quotes = request("GET", "/building/available", 200, params=params, headers=player)
    if not any(item.get("name") == "warehouse" and item.get("can_upgrade") is True
               for item in quotes):
        raise RuntimeError("warehouse upgrade unavailable")
    queued = request("POST", "/building/upgrade", 200, params={"world_id": world},
                     json={"city_id": city, "building_type": "warehouse"}, headers=player)
    queue = queued.get("id")
    if type(queue) is not int or queue <= 0:
        raise RuntimeError("queue id missing")
    request("GET", "/building/available", 404, params=params, headers=other)
    request("POST", "/building/upgrade", 404, params={"world_id": world},
            json={"city_id": city, "building_type": "warehouse"}, headers=other)
    case = request("POST", "/support/cases", 200, headers=player, json={
        "subject": "Fixture support request", "description": "Disposable support request",
        "world_id": world})
    case_id = case.get("id")
    if type(case_id) is not int or case_id <= 0:
        raise RuntimeError("support case id missing")
    privacy = request("POST", "/auth/me/privacy-requests", 200, headers=player,
                      json={"kind": "retention", "details": "Disposable privacy request"})
    privacy_id = privacy.get("id")
    if type(privacy_id) is not int or privacy_id <= 0 or privacy_id == case_id:
        raise RuntimeError("privacy case id missing")
    for own_id in (case_id, privacy_id):
        detail = request("GET", "/support/cases/" + str(own_id), 200, headers=player)
        if not isinstance(detail, dict) or detail.get("id") != own_id:
            raise RuntimeError("owner cannot read support case")
    request("GET", "/support/cases/" + str(case_id), 404, headers=other)
    request("GET", "/support/cases/" + str(privacy_id), 404, headers=other)
    if any(item.get("id") in (case_id, privacy_id) for item in
           request("GET", "/auth/me/privacy-requests", 200, headers=other)):
        raise RuntimeError("other user saw privacy request")
    request("GET", "/support/admin/cases", 403, headers=player)
    cases = request("GET", "/support/admin/cases", 200, headers=admin)
    if not {case_id, privacy_id}.issubset({item.get("id") for item in cases}):
        raise RuntimeError("admin cannot see fixture cases")
print(json.dumps({"city": city, "queue": queue, "case": case_id, "privacy": privacy_id}))
'''


def _http_probes(project, image, app_url, world, admin):
    """Run historical HTTP requests inside a disposable, unexposed backend."""
    from ops.ci_g5_actual_migration import DATABASE
    from ops.ci_g5_edge_admission import probe, run
    from ops.ci_g5_integrated_runtime import binary, wait_until
    from ops.ci_g5_release_transition import _container, _create_container, _TEST_SECRET

    backend = _create_container(
        project, project, "role-backend", image, restart="no",
        environment=("APP_ENV=test", "DATABASE_URL=" + app_url,
                     "SECRET_KEY=" + _TEST_SECRET),
    )
    try:
        row = _container(backend)
        if (row.get("Image") != image
                or row.get("HostConfig", {}).get("PortBindings") not in (None, {})
                or row.get("HostConfig", {}).get("PublishAllPorts") is not False
                or row.get("Config", {}).get("Labels", {}).get("medievol.g5.edge-fixture") != project):
            raise ObjectPolicyError("backend container isolation mismatch")
        run(["start", backend])
        wait_until(lambda: probe(["exec", backend, "python", "-c",
            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"
        ])[0] == 0, "historical backend unavailable")
        if binary(["exec", "-i", backend, "python", "-"], input=_REGISTER_CLIENT.encode()).strip() != b"registered":
            raise ObjectPolicyError("HTTP fixture registration failed")
        # Bootstrap verification and the fixture admin, not authorization decisions.
        admin.sql("UPDATE users SET is_verified=true, verification_token=NULL, "
                  "is_admin=(username='g5_role_admin'), "
                  "admin_role=CASE WHEN username='g5_role_admin' THEN 'admin' ELSE NULL END "
                  "WHERE username IN ('g5_role_player','g5_role_other','g5_role_admin');", DATABASE)
        raw = binary(["exec", "-i", backend, "python", "-", str(world)],
                     input=_HTTP_CLIENT.encode())
        try:
            evidence = json.loads(raw)
            if (not isinstance(evidence, dict) or set(evidence) != {"city", "queue", "case", "privacy"}
                    or any(type(value) is not int or value <= 0 for value in evidence.values())):
                raise ValueError
        except (ValueError, TypeError):
            raise ObjectPolicyError("invalid HTTP probe evidence") from None
        city, queue, case, privacy = (evidence[key] for key in ("city", "queue", "case", "privacy"))
        if admin.sql(
            f"SELECT count(*) FROM building_queue q JOIN cities c ON c.id=q.city_id "
            f"JOIN users u ON u.id=c.owner_id WHERE q.id={queue} AND c.id={city} "
            f"AND c.world_id={world} AND u.username='g5_role_player';", DATABASE
        ) != "1" or admin.sql(
            f"SELECT count(*) FROM support_cases s JOIN users u ON u.id=s.requester_id "
            f"WHERE s.id IN ({case},{privacy}) AND u.username='g5_role_player';", DATABASE
        ) != "2":
            raise ObjectPolicyError("HTTP writes not persisted")
    finally:
        run(["stop", "-t", "10", backend])
        if _container(backend).get("State", {}).get("Running") is not False:
            raise ObjectPolicyError("backend did not stop")
        run(["rm", backend])


def _drill():
    from ops.ci_g5_actual_migration import (
        ADMIN, ADMIN_PASSWORD, APP, APP_PASSWORD, DATABASE, Admin,
        app_command, expect_refused,
    )
    from ops.ci_g5_edge_admission import cleanup_fixture, run
    from ops.ci_g5_integrated_runtime import binary, ready_db, wait_until
    from ops.ci_g5_privileged_inventory import IsolatedAdmin
    from ops.ci_g5_actual_reopen import original_database
    from ops.ci_g5_release_transition import (
        PREVIOUS_SHA, _base_image_reference, _build_image, _container_ip, _ensure_commit,
        _git, _git_exists, _image, _remove_fixture_image, _worktree, release_pair,
    )
    from ops.g5_migration_role_identity import validate_split
    from ops.g5_pg15_writer_fence import Pg15PersistentFence

    repo = Path(__file__).resolve().parents[1]
    project = "bm-g5-edge-" + uuid4().hex
    root = Path(tempfile.mkdtemp(prefix="bm-g5-role-", dir="/tmp"))
    tags = []
    succeeded = False
    try:
        candidate_sha = _git(repo, "rev-parse", "HEAD")
        if (not re.fullmatch(r"[0-9a-f]{40}", candidate_sha)
                or not _git_exists(repo, "cat-file", "-e", PREVIOUS_SHA + "^{commit}")
                or not _git_exists(repo, "cat-file", "-e",
                    f"{candidate_sha}:batalla_medieval_backend/alembic/versions/0020_wonder_funding_rules.py")
                or _git_exists(repo, "cat-file", "-e",
                    f"{PREVIOUS_SHA}:batalla_medieval_backend/alembic/versions/0020_wonder_funding_rules.py")):
            raise ObjectPolicyError("required immutable release sources unavailable")
        # Never fetch a remote source as part of this laboratory.
        _ensure_commit(repo, PREVIOUS_SHA)
        try:
            base = _base_image_reference()
            _image("postgres:15-alpine")
        except Exception:
            raise ObjectPolicyError("required local base images or digest unavailable") from None
        images = []
        for label, sha in (("previous", PREVIOUS_SHA), ("candidate", candidate_sha)):
            tag = f"medievol-g5-role-{label}:{project}"
            tags.append((tag, sha))
            with _worktree(repo, root, sha) as tree:
                image, _, _ = _build_image(repo, sha, tag,
                                           tree / "batalla_medieval_backend", base)
            images.append(image)
        release_pair(PREVIOUS_SHA, candidate_sha, *images)
        label = "medievol.g5.edge-fixture=" + project
        run(["network", "create", "--internal", "--label", label, project])
        database = run(["run", "-d", "--network", project, "--network-alias", "database",
                        "--label", label, "-e", "POSTGRES_PASSWORD=" + ADMIN_PASSWORD,
                        "postgres:15-alpine"]).strip()
        wait_until(lambda: ready_db(database), "isolated database not ready")
        admin, inventory = Admin(database), IsolatedAdmin(database)
        admin.sql(f"CREATE DATABASE {DATABASE};")
        admin.sql("REVOKE CONNECT ON DATABASE postgres, template1 FROM PUBLIC;")
        migration_url = f"postgresql+psycopg://{ADMIN}:{ADMIN_PASSWORD}@database:5432/{DATABASE}"
        app_url = f"postgresql+psycopg://{APP}:{APP_PASSWORD}@database:5432/{DATABASE}"
        split = validate_split({"POSTGRES_DB": DATABASE, "POSTGRES_USER": ADMIN,
                                "POSTGRES_PASSWORD": ADMIN_PASSWORD, "DB_URL": app_url,
                                "G5_MIGRATION_DB_URL": migration_url})
        if (split.database, split.application, split.maintenance) != (DATABASE, APP, ADMIN):
            raise ObjectPolicyError("role identity mismatch")
        # Docker DNS is not required: pin the fixture's private address as
        # the release-transition laboratory does.
        address = _container_ip(database, project)
        maintenance_url = f"postgresql+psycopg://{ADMIN}:{ADMIN_PASSWORD}@{address}:5432/{DATABASE}"
        app_url = f"postgresql+psycopg://{APP}:{APP_PASSWORD}@{address}:5432/{DATABASE}"

        def backend(image, *args):
            return run(["run", "--rm", "--network", project, "--label", label,
                        "-e", "APP_ENV=test", "-e", "DATABASE_URL=" + maintenance_url,
                        image, *args])

        backend(images[0], "alembic", "-c", "/app/alembic.ini", "upgrade", PREVIOUS)
        backend(images[0], "python", "-m", "app.seed")
        if admin.sql("SELECT version_num FROM alembic_version;", DATABASE) != PREVIOUS:
            raise ObjectPolicyError("historical revision mismatch")
        if admin.sql("SELECT count(*) FROM cities;", DATABASE) == "0":
            raise ObjectPolicyError("historical fixture is empty")
        if admin.sql("SELECT count(*) FROM pg_roles WHERE rolname='game_app';") != "0":
            raise ObjectPolicyError("application role collision")
        before_identity = admin.sql(
            "SELECT d.oid || '|' || d.datdba || '|' || r.oid || '|' || "
            "current_setting('server_version_num') FROM pg_database d "
            "JOIN pg_roles r ON r.rolname=current_user WHERE d.datname='game_migration_ci' "
            "AND current_user='postgres' AND r.rolsuper AND d.datdba=r.oid "
            "AND current_setting('server_version_num')::int BETWEEN 150000 AND 159999;"
        )
        if not re.fullmatch(r"[0-9]+\|[0-9]+\|[0-9]+\|15[0-9]{4}", before_identity):
            raise ObjectPolicyError("historical database identity unavailable")

        # Snapshot the populated historical database before any role creation
        # or privilege changes. The disposable fixture has no running app writers.
        backup = binary(["exec", database, "pg_dump", "-U", ADMIN, "-d", DATABASE, "-Fc"])
        if not backup.startswith(b"PGDMP"):
            raise ObjectPolicyError("backup is invalid")
        archive = binary(["exec", "-i", database, "pg_restore", "--list"], input=backup)
        if b"alembic_version" not in archive or b"worlds" not in archive:
            raise ObjectPolicyError("backup verification failed")
        backup_path = root / "historical.dump"
        with backup_path.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(backup)
            stream.flush()
            os.fsync(stream.fileno())
        if backup_path.read_bytes() != backup:
            raise ObjectPolicyError("backup persistence verification failed")

        admin.sql(f"CREATE ROLE {APP} LOGIN PASSWORD '{APP_PASSWORD}';")
        original = original_database(admin)
        if (f"{original.database_oid}|{original.maintenance_role_oid}|"
                f"{original.maintenance_role_oid}|{original.server_version_num}") != before_identity:
            raise ObjectPolicyError("database identity changed after backup")
        admin.sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC;", DATABASE)
        target = Pg15FenceTarget(DATABASE, APP, ADMIN)
        _inventory(target, inventory, False)
        provision(target, admin, inventory, PREVIOUS)
        # Explicit retries accept only the complete known state.
        provision(target, admin, inventory, PREVIOUS, granted_revision=PREVIOUS)

        def rejected(create, remove, check, database_name=DATABASE):
            admin.sql(create, database_name)
            try:
                try:
                    check()
                except ObjectPolicyError:
                    pass
                else:
                    raise ObjectPolicyError("adversarial state was not rejected")
            finally:
                admin.sql(remove, database_name)

        rejected("CREATE TABLE public.unexpected_ci (id int);",
                 "DROP TABLE public.unexpected_ci;",
                 lambda: inspect_objects(target, inventory, PREVIOUS, granted_revision=PREVIOUS))
        rejected("CREATE SEQUENCE public.unexpected_ci_seq;",
                 "DROP SEQUENCE public.unexpected_ci_seq;",
                 lambda: inspect_objects(target, inventory, PREVIOUS, granted_revision=PREVIOUS))
        rejected("ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO game_app;",
                 "ALTER DEFAULT PRIVILEGES REVOKE SELECT ON TABLES FROM game_app;",
                 lambda: inspect_objects(target, inventory, PREVIOUS, granted_revision=PREVIOUS))
        rejected("GRANT TRUNCATE ON worlds TO game_app;",
                 "REVOKE TRUNCATE ON worlds FROM game_app;",
                 lambda: inspect_objects(target, inventory, PREVIOUS, granted_revision=PREVIOUS))
        rejected("GRANT SELECT ON worlds TO PUBLIC;",
                 "REVOKE SELECT ON worlds FROM PUBLIC;",
                 lambda: inspect_objects(target, inventory, PREVIOUS, granted_revision=PREVIOUS))
        rejected("REVOKE UPDATE ON worlds FROM game_app;",
                 "GRANT UPDATE ON worlds TO game_app;",
                 lambda: inspect_objects(target, inventory, PREVIOUS, granted_revision=PREVIOUS))
        rejected("ALTER ROLE game_app SUPERUSER;", "ALTER ROLE game_app NOSUPERUSER;",
                 lambda: _inventory(target, inventory, False), "postgres")
        rejected("CREATE ROLE rogue_ci NOLOGIN;", "DROP ROLE rogue_ci;",
                 lambda: _inventory(target, inventory, False), "postgres")
        inspect_objects(target, inventory, PREVIOUS, granted_revision=PREVIOUS)
        world_id = admin.sql("SELECT id FROM worlds WHERE name='Mundo 1';", DATABASE)
        if not world_id.isdecimal() or int(world_id) <= 0:
            raise ObjectPolicyError("historical world unavailable")
        _http_probes(project, images[0], app_url, int(world_id), admin)
        world = run(app_command(database, """
            INSERT INTO worlds(name, speed_modifier, resource_modifier, map_size,
              special_rules, created_at, is_active, lifecycle_status, lifecycle_changed_at)
            VALUES ('Role laboratory world', 1, 1, 100, '', now(), true, 'open', now())
            RETURNING id;
        """)).strip()
        if not world.isdecimal():
            raise ObjectPolicyError("runtime gameplay write failed")
        run(app_command(database, "SELECT count(*) FROM support_cases;"))
        run(app_command(database, "SELECT count(*) FROM user_blocks;"))
        expect_refused(database, "UPDATE alembic_version SET version_num='bad';", "permission denied")
        expect_refused(database, "CREATE TABLE public.forbidden_ci (id int);", "permission denied")
        _sql_denial_probes(database)

        _inventory(target, inventory, False)
        gate = Pg15PersistentFence(target, admin)
        gate.engage()
        gate.assert_closed()
        identity = admin.sql(
            "SELECT d.oid || '|' || a.oid || '|' || m.oid FROM pg_database d "
            "CROSS JOIN pg_roles a CROSS JOIN pg_roles m "
            "WHERE d.datname='game_migration_ci' AND a.rolname='game_app' AND m.rolname='postgres';"
        )
        if identity != f"{original.database_oid}|{original.app_role_oid}|{original.maintenance_role_oid}":
            raise ObjectPolicyError("fenced database identity changed")
        _inventory(target, inventory, True)
        inspect_objects(target, inventory, PREVIOUS, granted_revision=PREVIOUS)
        expect_refused(database, "SELECT 1;", "not permitted to log in")

        gate.assert_closed()
        backend(images[1], "alembic", "-c", "/app/alembic.ini", "upgrade", CANDIDATE)
        backend(images[1], "python", "-m", "app.seed")
        gate.assert_closed()
        if (admin.sql("SELECT version_num FROM alembic_version;", DATABASE) != CANDIDATE
                or admin.sql(f"SELECT name || '|' || wonder_rules_version FROM worlds WHERE id={world};",
                             DATABASE) != "Role laboratory world|legacy-v1"):
            raise ObjectPolicyError("migration preservation verification failed")
        _inventory(target, inventory, True)
        provision(target, admin, inventory, CANDIDATE, granted_revision=PREVIOUS, fenced=True)
        gate.assert_closed()
        _inventory(target, inventory, True)
        if admin.sql(
            "SELECT d.oid || '|' || a.oid || '|' || m.oid FROM pg_database d "
            "CROSS JOIN pg_roles a CROSS JOIN pg_roles m "
            "WHERE d.datname='game_migration_ci' AND a.rolname='game_app' AND m.rolname='postgres';"
        ) != identity:
            raise ObjectPolicyError("migrated database identity changed")
        expect_refused(database, "SELECT * FROM wonder_funding;", "not permitted to log in")
        gate.assert_closed()
        print("G5 role laboratory: historical HTTP gameplay, support, privacy and authorization, "
              "archive listing, 0020 seed, grants and fence verified")
        print("Limitations: mutable-table grants are not least-privilege certified; "
              "no backup restore, wiki or unprobed HTTP routes, or worker were exercised.")
        succeeded = True
    finally:
        if succeeded:
            cleanup_fixture(project)
            for tag, sha in tags:
                _remove_fixture_image(tag, sha)
            shutil.rmtree(root)
        else:
            print(f"G5 fixture preserved for reconciliation: project={project}; root={root}",
                  file=sys.stderr)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if (args or os.environ.get("CI") != "true"
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        print("G5 role laboratory requires GitHub-hosted CI and no arguments", file=sys.stderr)
        return 2
    try:
        _drill()
    except Exception as exc:
        print(f"G5 role laboratory failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
