"""BM-0090: blocking inventory for safe account deletion.

This test does NOT delete accounts. Every new direct FK to users.id must be
classified before a deletion/anonymization implementation can be reviewed.
"""

from types import SimpleNamespace

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


def _is_sql_delete_cascade(fk):
    return str(fk.ondelete or "").strip().upper() == "CASCADE"


def test_sql_cascade_detection_handles_missing_mixed_case_and_whitespace():
    for action in ("CASCADE", "cascade", "Cascade", " cAsCaDe "):
        assert _is_sql_delete_cascade(SimpleNamespace(ondelete=action))
    for action in (None, "", "SET NULL", "SET DEFAULT", "RESTRICT"):
        assert not _is_sql_delete_cascade(SimpleNamespace(ondelete=action))


def test_nullable_shared_references_allow_non_destructive_detachment():
    keys = _user_foreign_keys()
    for relation in NULLABLE_REFERENCES:
        assert keys[relation].parent.nullable, (
            f"Deletion design assumes nullable reference: {relation}"
        )
        assert not _is_sql_delete_cascade(keys[relation]), (
            f"Unsafe SQL cascade through nullable shared reference: {relation}"
        )


def test_required_shared_references_do_not_cascade_away_other_players_data():
    keys = _user_foreign_keys()
    for relation in REQUIRED_SHARED_REFERENCES:
        assert not keys[relation].parent.nullable, (
            f"Update dependency registry: {relation} became nullable"
        )
        assert not _is_sql_delete_cascade(keys[relation]), (
            f"Unsafe SQL cascade in shared identity reference: {relation}"
        )


# Existing ORM delete/delete-orphan cascades are *not safe* account erasure
# semantics. Snapshotting them ensures every changed edge receives a review.
# In particular, User.messages_sent/received, User.cities, and
# City.attacker_reports/defender_reports can affect another player's records.
EXISTING_ORM_DELETE_CASCADES = frozenset({
    "User.heroes",
    "User.cities",
    "User.premium_status",
    "User.bookmarks",
    "User.alliances",
    "User.alliance_invitations",
    "User.alliance_invitations_sent",
    "User.alliance_chat_messages",
    "User.messages_sent",
    "User.messages_received",
    "User.logs",
    "User.achievement_progress",
    "User.theme_ownerships",
    "User.items",
    "User.notifications",
    "User.quest_progress",
    "User.world_memberships",
    "City.buildings",
    "City.troops",
    "City.building_queue",
    "City.troop_queue",
    "City.research_queue",
    "City.reports",
    "City.attacker_reports",
    "City.defender_reports",
    "City.market_offers",
    "City.research",
    "World.cities",
    "World.alliances",
    "World.movements",
    "World.reports",
    "World.players",
    "Hero.items",
    "Alliance.members",
    "Alliance.invitations",
    "Alliance.chat_messages",
    "ForumThread.posts",
})


def test_orm_delete_cascade_edges_are_inventoried_before_account_erasure():
    actual = {
        f"{model.__name__}.{relationship.key}"
        for model in (
            models.User, models.City, models.World, models.Hero,
            models.Alliance, models.ForumThread,
        )
        for relationship in model.__mapper__.relationships
        if "delete" in relationship.cascade or "delete-orphan" in relationship.cascade
    }
    assert actual == EXISTING_ORM_DELETE_CASCADES, (
        f"Unreviewed ORM delete cascades: {sorted(actual - EXISTING_ORM_DELETE_CASCADES)}; "
        f"removed/changed edges: {sorted(EXISTING_ORM_DELETE_CASCADES - actual)}"
    )
    # These existing relationships all use cascade="all, delete-orphan".
    # Changing the delete-orphan option must trigger another impact review.
    for model in (
        models.User, models.City, models.World, models.Hero,
        models.Alliance, models.ForumThread,
    ):
        for relationship in model.__mapper__.relationships:
            if f"{model.__name__}.{relationship.key}" in EXISTING_ORM_DELETE_CASCADES:
                assert "delete" in relationship.cascade
                assert "delete-orphan" in relationship.cascade


# Audit ALL direct FKs to city/hero rows because these are reachable from
# User via ORM cascades. Includes both combat and espionage reports, queues,
# ownership, movement, and cross-world membership starting cities.
INDIRECT_CITY_HERO_REFERENCES = {
    "adventures.hero_id": "heroes.id",
    "building_queue.city_id": "cities.id",
    "buildings.city_id": "cities.id",
    "hero_items.hero_id": "heroes.id",
    "heroes.city_id": "cities.id",
    "market_offers.city_id": "cities.id",
    "movements.hero_id": "heroes.id",
    "movements.origin_city_id": "cities.id",
    "movements.target_city_id": "cities.id",
    "oases.owner_city_id": "cities.id",
    "player_world.starting_city_id": "cities.id",
    "reports.attacker_city_id": "cities.id",
    "reports.city_id": "cities.id",
    "reports.defender_city_id": "cities.id",
    "research.city_id": "cities.id",
    "research_queue.city_id": "cities.id",
    "spy_reports.attacker_city_id": "cities.id",
    "spy_reports.city_id": "cities.id",
    "spy_reports.defender_city_id": "cities.id",
    "troop_queue.city_id": "cities.id",
    "troops.city_id": "cities.id",
}


def test_entire_city_hero_dependency_graph_is_classified_without_sql_cascades():
    all_fks = {
        f"{table.name}.{fk.parent.name}": fk
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
        if fk.target_fullname in ("cities.id", "heroes.id")
    }
    assert set(all_fks) == set(INDIRECT_CITY_HERO_REFERENCES), (
        f"Unreviewed indirect account deletion dependencies: "
        f"{sorted(set(all_fks) - set(INDIRECT_CITY_HERO_REFERENCES))}; "
        f"obsolete inventory: "
        f"{sorted(set(INDIRECT_CITY_HERO_REFERENCES) - set(all_fks))}"
    )
    for relation, target in INDIRECT_CITY_HERO_REFERENCES.items():
        fk = all_fks[relation]
        assert fk.target_fullname == target, (
            f"Changed target of account erasure dependency: {relation}"
        )
        assert not _is_sql_delete_cascade(fk), (
            f"Unsafe indirect SQL cascade during account erasure: {relation}"
        )
