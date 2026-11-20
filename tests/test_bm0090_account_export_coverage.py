"""BM-0090: additive account export fields must remain owner-scoped."""

import json

from app import models
from app.routers.auth import create_access_token


def headers(user):
    return {
        "Authorization": "Bearer " + create_access_token({
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        })
    }


def test_extended_account_export_preserves_owner_scope_in_shared_world(
    client, db_session, user
):
    world = db_session.query(models.World).one()
    other = models.User(
        username="export_other", email="export_other@example.com",
        hashed_password="other-secret-hash", is_verified=True,
    )
    theme = models.Theme(
        name="Shared Cosmetic", primary_color="#000",
        secondary_color="#fff", background_url="/bg", icon_pack_url="/icon",
    )
    season = models.Season(
        season_id="bm90_export_season", world_id=str(world.id), name="Export Test",
    )
    db_session.add_all([other, theme, season])
    db_session.flush()
    alliance = models.Alliance(
        name="Shared Alliance", world_id=world.id, leader_id=user.id,
    )
    rival_alliance = models.Alliance(
        name="Other Alliance", world_id=world.id, leader_id=other.id,
    )
    db_session.add_all([alliance, rival_alliance])
    db_session.flush()
    db_session.add_all([
        models.AllianceMember(alliance_id=alliance.id, user_id=user.id, rank=3),
        models.AllianceMember(alliance_id=alliance.id, user_id=other.id, rank=1),
        models.AllianceInvitation(
            alliance_id=alliance.id, invited_user_id=other.id,
            invited_by_id=user.id, status="pending",
        ),
        models.AllianceInvitation(
            alliance_id=rival_alliance.id, invited_user_id=user.id,
            invited_by_id=other.id, status="accepted",
        ),
        models.AllianceChatMessage(
            alliance_id=alliance.id, user_id=user.id,
            message="My authored alliance text",
        ),
        models.AllianceChatMessage(
            alliance_id=alliance.id, user_id=other.id,
            message="Other player private alliance text",
        ),
        models.MapBookmark(
            user_id=user.id, name="My private marker", x=1, y=2,
        ),
        models.MapBookmark(
            user_id=other.id, name="Opponent secret marker", x=7, y=8,
        ),
        models.PremiumStatus(
            user_id=user.id, rubies_balance=23, second_build_queue=True,
            selected_banner="My banner",
        ),
        models.PremiumStatus(
            user_id=other.id, rubies_balance=999,
            selected_banner="Opponent banner secret",
        ),
        models.ThemeOwnership(
            user_id=user.id, theme_id=theme.id, source="quest",
        ),
        models.ThemeOwnership(
            user_id=other.id, theme_id=theme.id, source="other_secret_source",
        ),
        models.SeasonResult(
            season_id=season.id, user_id=user.id,
            rank=3, points=100, rewards='["my_reward"]',
        ),
        models.SeasonResult(
            season_id=season.id, user_id=other.id,
            rank=1, points=999, rewards='["opponent_reward"]',
        ),
        models.UserBlock(
            blocker_id=user.id, blocked_id=other.id, world_id=world.id,
        ),
        models.UserBlock(
            blocker_id=other.id, blocked_id=user.id, world_id=world.id,
        ),
    ])
    db_session.commit()

    response = client.get("/auth/me/export", headers=headers(user))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["schema_version"] == 1
    assert data["account"]["id"] == user.id
    assert len(data["alliance_memberships"]) == 1
    assert data["alliance_memberships"][0]["rank"] == 3
    assert len(data["alliance_invitations_sent"]) == 1
    assert data["alliance_invitations_sent"][0]["invited_user_id"] == other.id
    assert len(data["alliance_invitations_received"]) == 1
    assert data["alliance_invitations_received"][0]["invited_by_id"] == other.id
    assert len(data["alliance_chat_messages_authored"]) == 1
    assert data["alliance_chat_messages_authored"][0]["message"] == "My authored alliance text"
    assert [item["name"] for item in data["map_bookmarks"]] == ["My private marker"]
    assert len(data["premium_status"]) == 1
    assert data["premium_status"][0]["rubies_balance"] == 23
    assert data["premium_status"][0]["second_build_queue"] is True
    assert data["premium_status"][0]["selected_banner"] == "My banner"
    assert len(data["theme_ownerships"]) == 1
    assert data["theme_ownerships"][0]["source"] == "quest"
    assert len(data["season_results"]) == 1
    assert data["season_results"][0]["rank"] == 3
    assert data["season_results"][0]["rewards"] == '["my_reward"]'
    assert len(data["user_blocks_created"]) == 1
    assert data["user_blocks_created"][0]["blocked_id"] == other.id

    serialized = json.dumps(data)
    for secret in (
        other.email, other.hashed_password, "Other player private alliance text",
        "Opponent secret marker", "Opponent banner secret",
        "other_secret_source", "opponent_reward",
    ):
        assert secret not in serialized

    opponent_export = client.get("/auth/me/export", headers=headers(other))
    assert opponent_export.status_code == 200
    theirs = opponent_export.json()
    assert theirs["account"]["id"] == other.id
    assert theirs["alliance_memberships"][0]["rank"] == 1
    assert theirs["map_bookmarks"][0]["name"] == "Opponent secret marker"
    assert theirs["premium_status"][0]["selected_banner"] == "Opponent banner secret"
    assert "My authored alliance text" not in json.dumps(theirs)


def test_extended_account_export_empty_when_user_has_no_owned_records(client, user):
    response = client.get("/auth/me/export", headers=headers(user))
    assert response.status_code == 200
    data = response.json()
    for name in (
        "alliance_memberships", "alliance_invitations_received",
        "alliance_invitations_sent", "alliance_chat_messages_authored",
        "map_bookmarks", "premium_status", "theme_ownerships",
        "season_results", "user_blocks_created",
    ):
        assert data[name] == [], name
