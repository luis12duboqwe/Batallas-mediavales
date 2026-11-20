"""BM-0090: blocking inventory for safe account deletion.

This test does NOT delete accounts. Every new direct FK to users.id must be
classified before a deletion/anonymization implementation can be reviewed.
"""

from app import models  # noqa: F401 - registers all mapped SQLAlchemy tables
from app.database import Base


# Other players, administrators and historical records can reference these
# rows. Their treatment is *not* the same as owned private gameplay data.
REQUIRED_SHARED_REFERENCES = frozenset({
    "alliance_chat_messages.user_id",
    "alliance_invitations.invited_by_id",
    "alliance_invitations.invited_user_id",
    "anti_cheat_flags.user_id",
    "chat_messages.user_id",
    "forum_posts.author_id",
    "forum_threads.author_id",
    "logs.user_id",
    "messages.receiver_id",
    "messages.sender_id",
    "season_results.user_id",
    "support_cases.requester_id",
})

# Potentially separable references to a user from shared world/history rows.
# Setting these to NULL is only a *technical option*, not approved policy.
NULLABLE_REFERENCES = frozenset({
    "admin_bot_logs.user_id",
    "alliances.leader_id",
    "anti_cheat_flags.reviewer_id",
    "chat_messages.moderated_by_id",
    "chat_messages.receiver_id",
    "cities.owner_id",
    "forum_posts.moderated_by_id",
    "logs.reversed_by_id",
    "support_cases.assigned_to_id",
    "worlds.winner_id",
})

OWNED_DIRECT_REFERENCES = frozenset({
    "achievement_progress.user_id",
    "alliance_members.user_id",
    "anti_cheat_rate_buckets.user_id",
    "heroes.user_id",
    "map_bookmarks.user_id",
    "notifications.user_id",
    "player_world.user_id",
    "premium_status.user_id",
    "quest_progress.user_id",
    "user_blocks.blocked_id",
    "user_blocks.blocker_id",
    "user_items.user_id",
    "user_themes.user_id",
})


def _user_foreign_keys():
    return {
        f"{table.name}.{fk.parent.name}": fk
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
        if fk.target_fullname == "users.id"
    }


def test_all_direct_user_foreign_keys_require_eraser_impact_review():
    groups = [
        REQUIRED_SHARED_REFERENCES,
        NULLABLE_REFERENCES,
        OWNED_DIRECT_REFERENCES,
    ]
    registry = set().union(*groups)
    assert len(registry) == sum(map(len, groups)), "Duplicate deletion classification"
    actual = set(_user_foreign_keys())
    assert actual == registry, (
        f"Unreviewed account-deletion dependencies: {sorted(actual - registry)}; "
        f"obsolete inventory entries: {sorted(registry - actual)}"
    )


def test_nullable_shared_references_allow_non_destructive_detachment():
    keys = _user_foreign_keys()
    for relation in NULLABLE_REFERENCES:
        assert keys[relation].parent.nullable, (
            f"Deletion design assumes nullable reference: {relation}"
        )


def test_required_shared_references_do_not_cascade_away_other_players_data():
    keys = _user_foreign_keys()
    for relation in REQUIRED_SHARED_REFERENCES:
        assert not keys[relation].parent.nullable, (
            f"Update dependency registry: {relation} became nullable"
        )
        assert keys[relation].ondelete != "CASCADE", (
            f"Unsafe implicit account delete cascade: {relation}"
        )
