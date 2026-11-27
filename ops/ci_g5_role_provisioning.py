"""Incomplete, read-only object-policy checks for a future CI-only G5 drill.

This module intentionally has no provisioning entrypoint.  It must not be used
as evidence that a database is safe to modify or that writers are excluded.
"""
from __future__ import annotations

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
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') "
        "ORDER BY c.relname;"
    )
    try:
        result = session.query(target.database, statement)
    except Exception:
        raise ObjectPolicyError("table inventory unavailable") from None
    if not isinstance(result, str):
        raise ObjectPolicyError("table inventory unavailable")
    validate_table_names(revision, result.splitlines())
