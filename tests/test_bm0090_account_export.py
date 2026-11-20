"""BM-0090 account-data export: authenticated scope and secret redaction."""

import json

from app import models
from app.routers.auth import create_access_token


def _headers(user):
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )
    return {"Authorization": f"Bearer {token}"}


def test_account_export_needs_current_valid_token(client, db_session, user):
    assert client.get("/auth/me/export").status_code == 401
    assert client.get(
        "/auth/me/export", headers={"Authorization": "Bearer malformed"}
    ).status_code == 401
    original_headers = _headers(user)
    login = client.get("/auth/me/export", headers=original_headers)
    assert login.status_code == 200
    assert login.json()["account"]["id"] == user.id

    user.auth_version += 1
    db_session.commit()
    assert client.get("/auth/me/export", headers=original_headers).status_code == 401
    assert client.get("/auth/me/export", headers=_headers(user)).status_code == 200


def test_account_export_scopes_game_data_and_omits_credentials(client, db_session, user, city):
    user.hashed_password = "secret-hash-must-not-export"
    user.password_reset_token = "reset-secret-must-not-export"
    user.verification_token = "verify-secret-must-not-export"
    user.last_login_ip = "203.0.113.5"

    stranger = models.User(
        username="other-player",
        email="other@example.com",
        hashed_password="stranger-hash-must-not-export",
        is_verified=True,
    )
    db_session.add(stranger)
    db_session.flush()
    another_world = models.World(name="OtherWorld", speed_modifier=1, resource_modifier=1)
    db_session.add(another_world)
    db_session.flush()
    other_city = models.City(
        name="HiddenOpponentCity", owner_id=stranger.id,
        world_id=city.world_id, x=30, y=31,
    )
    own_other_world = models.City(
        name="MySecondWorld", owner_id=user.id,
        world_id=another_world.id, x=0, y=0,
    )
    db_session.add_all([other_city, own_other_world])
    db_session.flush()
    hero = models.Hero(user_id=user.id, city_id=own_other_world.id,
                       world_id=another_world.id, name="MyHero")
    other_hero = models.Hero(user_id=stranger.id, city_id=other_city.id,
                             world_id=city.world_id, name="EnemyHero")
    db_session.add_all([hero, other_hero])
    db_session.flush()
    db_session.add_all([
        models.Building(city_id=city.id, name="town_hall", level=3),
        models.Building(city_id=other_city.id, name="barracks", level=99),
        models.Adventure(hero_id=hero.id, duration=50),
        models.Adventure(hero_id=other_hero.id, duration=75),
        models.Notification(user_id=user.id, title="My notification", body="Private A", type="info"),
        models.Notification(user_id=stranger.id, title="Foreign notification",
                            body="Secret from B", type="info"),
        models.Message(sender_id=user.id, receiver_id=stranger.id,
                       subject="My authored message", content="My message"),
        models.Message(sender_id=stranger.id, receiver_id=user.id,
                       subject="Received message", content="I received this"),
        models.Message(sender_id=stranger.id, receiver_id=stranger.id,
                       subject="Hidden message", content="not visible to tester"),
        models.SupportCase(requester_id=user.id, subject="My ticket", description="Help me"),
        models.SupportCase(requester_id=stranger.id, subject="Foreign ticket",
                           description="secret support issue"),
        models.ChatMessage(user_id=user.id, world_id=city.world_id,
                           channel="global", content="My chat content"),
        models.ChatMessage(user_id=stranger.id, world_id=city.world_id,
                           channel="global", content="Foreign chat content"),
    ])
    db_session.commit()

    reply = client.get("/auth/me/export", headers=_headers(user))
    assert reply.status_code == 200
    assert reply.headers["cache-control"] == "private, no-store"
    assert reply.headers["pragma"] == "no-cache"
    assert reply.headers["content-type"].startswith("application/json")
    assert "attachment" in reply.headers["content-disposition"]
    payload = reply.json()
    assert payload["schema_version"] == 1
    assert payload["account"]["username"] == user.username
    assert payload["account"]["last_login_ip"] == "203.0.113.5"
    assert {row["name"] for row in payload["cities"]} == {"Capital", "MySecondWorld"}
    assert [row["name"] for row in payload["buildings"]] == ["town_hall"]
    assert [row["name"] for row in payload["heroes"]] == ["MyHero"]
    assert len(payload["adventures"]) == 1
    assert [row["title"] for row in payload["notifications"]] == ["My notification"]
    assert {row["subject"] for row in payload["messages"]} == {
        "My authored message", "Received message",
    }
    assert [row["subject"] for row in payload["support_cases"]] == ["My ticket"]
    assert [row["content"] for row in payload["chat_messages_authored"]] == ["My chat content"]

    serialized = json.dumps(payload)
    for secret in [
        user.hashed_password, user.password_reset_token, user.verification_token,
        stranger.email, stranger.hashed_password, "HiddenOpponentCity", "EnemyHero",
        "Foreign notification", "Secret from B", "Hidden message",
        "not visible to tester", "Foreign ticket", "Foreign chat content",
    ]:
        assert secret not in serialized
    for banned_field in ["hashed_password", "verification_token", "password_reset_token",
                         "auth_version", "moderation_reason"]:
        assert banned_field not in serialized


def test_export_isolation_for_accounts_without_cities(client, db_session, user, city):
    second = models.User(
        username="no-cities", email="nocities@example.com",
        hashed_password="placeholder", is_verified=True,
    )
    db_session.add(second)
    db_session.commit()
    result = client.get("/auth/me/export", headers=_headers(second))
    assert result.status_code == 200
    payload = result.json()
    assert payload["account"]["id"] == second.id
    assert payload["cities"] == []
    assert payload["buildings"] == []
    assert payload["troops"] == []
    assert payload["heroes"] == []
    assert payload["messages"] == []
    assert "Capital" not in json.dumps(payload)
