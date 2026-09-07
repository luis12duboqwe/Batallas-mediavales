from app import models, schemas
from app.routers.auth import create_access_token


def _headers(user: models.User) -> dict[str, str]:
    return {
        "Authorization": "Bearer "
        + create_access_token(
            {
                "sub": user.username,
                "type": "access",
                "ver": user.auth_version,
            }
        )
    }


def _user(db_session, username: str, *, role: str | None = None, is_admin: bool | None = None):
    enabled = (role is not None) if is_admin is None else is_admin
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
        is_admin=enabled,
        admin_role=role,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_support_cases_are_owner_isolated_and_support_managed(client, db_session):
    player_a = _user(db_session, "bm73_case_a")
    player_b = _user(db_session, "bm73_case_b")
    support = _user(db_session, "bm73_case_support", role="support")

    case_a = client.post(
        "/support/cases",
        headers=_headers(player_a),
        json={"subject": "Case A", "description": "Private request A"},
    )
    case_b = client.post(
        "/support/cases",
        headers=_headers(player_b),
        json={"subject": "Case B", "description": "Private request B"},
    )
    assert case_a.status_code == 200, case_a.text
    assert case_b.status_code == 200, case_b.text

    mine = client.get("/support/cases", headers=_headers(player_a))
    assert mine.status_code == 200, mine.text
    assert [row["id"] for row in mine.json()] == [case_a.json()["id"]]

    foreign = client.get(
        f"/support/cases/{case_b.json()['id']}", headers=_headers(player_a)
    )
    assert foreign.status_code == 404, foreign.text

    admin_list = client.get("/support/admin/cases", headers=_headers(support))
    assert admin_list.status_code == 200, admin_list.text
    assert {row["id"] for row in admin_list.json()} >= {
        case_a.json()["id"],
        case_b.json()["id"],
    }

    updated = client.patch(
        f"/support/admin/cases/{case_a.json()['id']}",
        headers=_headers(support),
        json={
            "status": "resolved",
            "resolution": "Verified and resolved",
            "reason": "Support investigation completed",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "resolved"
    assert updated.json()["resolution"] == "Verified and resolved"


def test_global_chat_moderation_hides_and_equivalent_role_can_revert(
    client, db_session, user, city
):
    moderator = _user(db_session, "bm73_chat_mod", role="moderator")
    support = _user(db_session, "bm73_chat_support", role="support")
    user.world_id = city.world_id
    if (
        db_session.query(models.PlayerWorld)
        .filter_by(user_id=user.id, world_id=city.world_id)
        .one_or_none()
        is None
    ):
        db_session.add(models.PlayerWorld(user_id=user.id, world_id=city.world_id))
    message = models.ChatMessage(
        user_id=user.id,
        world_id=city.world_id,
        channel="global",
        content="visible before moderation",
    )
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)

    visible = client.get("/chat/history/global", headers=_headers(user))
    assert visible.status_code == 200, visible.text
    assert any(row["id"] == message.id for row in visible.json())

    forbidden = client.patch(
        f"/admin/moderation/chat/{message.id}",
        headers=_headers(support),
        json={"hidden": True, "reason": "support must not moderate"},
    )
    assert forbidden.status_code == 403, forbidden.text

    hidden = client.patch(
        f"/admin/moderation/chat/{message.id}",
        headers=_headers(moderator),
        json={"hidden": True, "reason": "Community policy violation"},
    )
    assert hidden.status_code == 200, hidden.text
    audit_id = hidden.json()["id"]
    assert hidden.json()["reversible"] is True

    history = client.get("/chat/history/global", headers=_headers(user))
    assert history.status_code == 200, history.text
    assert all(row["id"] != message.id for row in history.json())

    inspection = client.get(
        f"/admin/moderation/chat/{message.id}", headers=_headers(moderator)
    )
    assert inspection.status_code == 200, inspection.text
    assert inspection.json()["content"] == "visible before moderation"
    assert inspection.json()["is_hidden"] is True

    restored = client.post(
        f"/admin/logs/{audit_id}/revert",
        headers=_headers(moderator),
        json={"reason": "Moderation decision overturned"},
    )
    assert restored.status_code == 200, restored.text

    visible_again = client.get("/chat/history/global", headers=_headers(user))
    assert visible_again.status_code == 200, visible_again.text
    assert any(row["id"] == message.id for row in visible_again.json())


def test_forum_post_moderation_hides_without_deleting(client, db_session, user, city):
    moderator = _user(db_session, "bm73_forum_mod", role="moderator")
    alliance = models.Alliance(
        name="BM73 Moderation Alliance",
        description="",
        diplomacy="neutral",
        leader_id=user.id,
        world_id=city.world_id,
    )
    db_session.add(alliance)
    db_session.flush()
    db_session.add(
        models.AllianceMember(
            alliance_id=alliance.id,
            user_id=user.id,
            rank=schemas.RANK_LEADER,
        )
    )
    thread = models.ForumThread(
        alliance_id=alliance.id,
        author_id=user.id,
        title="Moderation target",
    )
    db_session.add(thread)
    db_session.flush()
    post = models.ForumPost(
        thread_id=thread.id,
        author_id=user.id,
        content="forum content to hide",
    )
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)

    hidden = client.patch(
        f"/admin/moderation/forum/{post.id}",
        headers=_headers(moderator),
        json={"hidden": True, "reason": "Forum policy violation"},
    )
    assert hidden.status_code == 200, hidden.text

    detail = client.get(f"/forum/threads/{thread.id}", headers=_headers(user))
    assert detail.status_code == 200, detail.text
    assert detail.json()["posts"] == []
    assert db_session.query(models.ForumPost).filter_by(id=post.id).one() is not None

    restored = client.post(
        f"/admin/logs/{hidden.json()['id']}/revert",
        headers=_headers(moderator),
        json={"reason": "Restore after appeal"},
    )
    assert restored.status_code == 200, restored.text
    detail_after = client.get(f"/forum/threads/{thread.id}", headers=_headers(user))
    assert detail_after.status_code == 200, detail_after.text
    assert [row["id"] for row in detail_after.json()["posts"]] == [post.id]


def test_admin_roles_do_not_escalate_world_management(client, db_session):
    operator = _user(db_session, "bm73_world_operator", role="operator")
    admin = _user(db_session, "bm73_world_admin", role="admin")
    fake_admin_role = _user(
        db_session,
        "bm73_fake_admin_role",
        role="admin",
        is_admin=False,
    )

    denied_operator = client.get(
        "/worlds/admin/catalogue", headers=_headers(operator)
    )
    denied_fake = client.get(
        "/worlds/admin/catalogue", headers=_headers(fake_admin_role)
    )
    allowed = client.get("/worlds/admin/catalogue", headers=_headers(admin))
    assert denied_operator.status_code == 403, denied_operator.text
    assert denied_fake.status_code == 403, denied_fake.text
    assert allowed.status_code == 200, allowed.text
