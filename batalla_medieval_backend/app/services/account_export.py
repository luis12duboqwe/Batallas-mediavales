"""Explicit, read-only allowlist for account data export (BM-0090).

Never serialize ORM models blindly: they contain password hashes, reset tokens,
internal moderation fields, and references to other players.
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now


def _fields(record, names):
    return {name: getattr(record, name) for name in names}


def _owned_rows(db: Session, model, owner_column, user_id: int, fields):
    return [
        _fields(item, fields)
        for item in (
            db.query(model)
            .filter(getattr(model, owner_column) == user_id)
            .order_by(model.id)
            .all()
        )
    ]


def _related_rows(db: Session, model, fk_column, ids, fields):
    if not ids:
        return []
    return [
        _fields(item, fields)
        for item in (
            db.query(model)
            .filter(getattr(model, fk_column).in_(ids))
            .order_by(model.id)
            .all()
        )
    ]


def build_account_export(db: Session, user: models.User) -> dict:
    """Export the authenticated player's own account and gameplay data.

    Incoming messages are included because their recipient may read them; we
    deliberately export no counterpart emails or other users' account fields.
    """
    cities = _owned_rows(
        db, models.City, "owner_id", user.id,
        ("id", "world_id", "name", "x", "y", "settlement_type",
         "wood", "stone", "iron", "gold", "loyalty", "population_max",
         "researched_units", "last_production"),
    )
    city_ids = [city["id"] for city in cities]
    heroes = _owned_rows(
        db, models.Hero, "user_id", user.id,
        ("id", "world_id", "city_id", "name", "level", "xp", "health",
         "status", "attack_points", "defense_points", "production_points"),
    )
    hero_ids = [hero["id"] for hero in heroes]

    # Message access is restricted to the sender/receiver pair, even when
    # another player's content happens to have the same world identifier.
    messages = [
        _fields(message, ("id", "world_id", "sender_id", "receiver_id",
                          "subject", "content", "read", "timestamp"))
        for message in (
            db.query(models.Message)
            .filter(or_(models.Message.sender_id == user.id,
                        models.Message.receiver_id == user.id))
            .order_by(models.Message.id)
            .all()
        )
    ]

    owned_items = (
        db.query(models.UserItem)
        .filter(models.UserItem.user_id == user.id)
        .order_by(models.UserItem.item_id)
        .all()
    )

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "account": _fields(user, (
            "id", "username", "email", "created_at", "last_active_at",
            "language", "email_notifications", "is_verified", "is_frozen",
            "last_login_at", "last_login_ip", "world_id",
            "rubies_balance", "rename_tokens", "tutorial_step",
            "tutorial_reward_claimed", "premium_theme_unlocked",
            "attacker_points", "defender_points",
        )),
        "world_memberships": _owned_rows(
            db, models.PlayerWorld, "user_id", user.id,
            ("id", "world_id", "starting_city_id", "expansion_points", "joined_at"),
        ),
        "cities": cities,
        "buildings": _related_rows(
            db, models.Building, "city_id", city_ids,
            ("id", "city_id", "name", "level"),
        ),
        "troops": _related_rows(
            db, models.Troop, "city_id", city_ids,
            ("id", "city_id", "unit_type", "quantity"),
        ),
        "building_queues": _related_rows(
            db, models.BuildingQueue, "city_id", city_ids,
            ("id", "city_id", "building_type", "target_level", "finish_time", "paid_cost"),
        ),
        "troop_queues": _related_rows(
            db, models.TroopQueue, "city_id", city_ids,
            ("id", "city_id", "troop_type", "amount", "finish_time", "paid_cost"),
        ),
        "research_queues": _related_rows(
            db, models.ResearchQueue, "city_id", city_ids,
            ("id", "city_id", "tech_name", "finish_time", "paid_cost"),
        ),
        "market_offers": _related_rows(
            db, models.MarketOffer, "city_id", city_ids,
            ("id", "city_id", "world_id", "offer_type", "offer_amount",
             "request_type", "request_amount", "is_alliance_only", "created_at"),
        ),
        "heroes": heroes,
        "hero_items": _related_rows(
            db, models.HeroItem, "hero_id", hero_ids,
            ("id", "hero_id", "template_id", "is_equipped"),
        ),
        "adventures": _related_rows(
            db, models.Adventure, "hero_id", hero_ids,
            ("id", "hero_id", "difficulty", "duration", "status",
             "rules_version", "result", "created_at", "started_at", "completed_at"),
        ),
        "achievement_progress": _owned_rows(
            db, models.AchievementProgress, "user_id", user.id,
            ("id", "achievement_id", "world_id", "current_progress", "status"),
        ),
        "quest_progress": _owned_rows(
            db, models.QuestProgress, "user_id", user.id,
            ("id", "quest_id", "status", "progress_data"),
        ),
        "notifications": _owned_rows(
            db, models.Notification, "user_id", user.id,
            ("id", "title", "body", "type", "created_at", "read"),
        ),
        "messages": messages,
        # Only records owned/authored by this account. In particular, an
        # opponent blocking this player is NOT part of the export.
        "alliance_memberships": _owned_rows(
            db, models.AllianceMember, "user_id", user.id,
            ("id", "alliance_id", "rank"),
        ),
        "alliance_invitations_received": _owned_rows(
            db, models.AllianceInvitation, "invited_user_id", user.id,
            ("id", "alliance_id", "invited_by_id", "status",
             "created_at", "responded_at"),
        ),
        "alliance_invitations_sent": _owned_rows(
            db, models.AllianceInvitation, "invited_by_id", user.id,
            ("id", "alliance_id", "invited_user_id", "status",
             "created_at", "responded_at"),
        ),
        "alliance_chat_messages_authored": _owned_rows(
            db, models.AllianceChatMessage, "user_id", user.id,
            ("id", "alliance_id", "message", "created_at"),
        ),
        "map_bookmarks": _owned_rows(
            db, models.MapBookmark, "user_id", user.id,
            ("id", "name", "x", "y"),
        ),
        "premium_status": _owned_rows(
            db, models.PremiumStatus, "user_id", user.id,
            ("rubies_balance", "second_build_queue", "second_troop_queue",
             "rename_city_unlocked", "rename_player_unlocked", "extra_themes",
             "profile_banner", "instant_building_cancel",
             "increased_message_storage", "map_bookmarks",
             "selected_theme", "selected_banner"),
        ),
        "theme_ownerships": _owned_rows(
            db, models.ThemeOwnership, "user_id", user.id,
            ("id", "theme_id", "source", "created_at"),
        ),
        "season_results": _owned_rows(
            db, models.SeasonResult, "user_id", user.id,
            ("id", "season_id", "alliance_id", "rank", "points", "rewards"),
        ),
        "user_blocks_created": _owned_rows(
            db, models.UserBlock, "blocker_id", user.id,
            ("id", "blocked_id", "world_id", "created_at"),
        ),
        "chat_messages_authored": _owned_rows(
            db, models.ChatMessage, "user_id", user.id,
            ("id", "world_id", "alliance_id", "channel", "receiver_id",
             "content", "timestamp", "is_hidden"),
        ),
        "forum_threads_authored": _owned_rows(
            db, models.ForumThread, "author_id", user.id,
            ("id", "alliance_id", "title", "created_at", "updated_at"),
        ),
        "forum_posts_authored": _owned_rows(
            db, models.ForumPost, "author_id", user.id,
            ("id", "thread_id", "content", "created_at", "updated_at", "is_hidden"),
        ),
        "support_cases": _owned_rows(
            db, models.SupportCase, "requester_id", user.id,
            ("id", "world_id", "subject", "description", "status",
             "created_at", "updated_at", "resolved_at", "closed_at"),
        ),
        "shop_items_owned": [
            _fields(item, ("item_id", "acquired_at")) for item in owned_items
        ],
    }
