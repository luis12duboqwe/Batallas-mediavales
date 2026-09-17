from app import models
from app.routers.auth import create_access_token
from app.services import balance
from app.services import quest as quest_service


def _headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )
    return {"Authorization": f"Bearer {token}"}


def test_legacy_quest_list_uses_authoritative_tutorial_completion(client, user):
    headers = _headers(user)
    tutorial = client.get("/tutorial/status", headers=headers)
    legacy = client.get("/quest/list", headers=headers)

    assert tutorial.status_code == 200
    assert legacy.status_code == 200
    assert legacy.json()["quests"] == []
    assert legacy.json()["tutorial_completed"] is tutorial.json()["completed"]


def test_legacy_quest_claims_are_retired_without_mutating_history(
    client,
    db_session,
    user,
):
    quest = models.Quest(
        quest_id="gatherer",
        title="Historical quest",
        description="Must remain inert",
        requirements={"type": "resources_collected", "amount": 1},
        reward={"rename_tokens": 5, "premium_theme": True},
        is_tutorial=False,
    )
    db_session.add(quest)
    db_session.flush()
    progress = models.QuestProgress(
        user_id=user.id,
        quest_id=quest.id,
        status="completed",
        progress_data={"collected": 9999},
    )
    db_session.add(progress)
    db_session.commit()

    before_tokens = user.rename_tokens
    before_theme = user.premium_theme_unlocked

    response = client.post("/quest/claim/gatherer", headers=_headers(user))

    assert response.status_code == 410
    db_session.expire_all()
    persisted_user = db_session.query(models.User).filter_by(id=user.id).one()
    persisted_progress = (
        db_session.query(models.QuestProgress)
        .filter_by(user_id=user.id, quest_id=quest.id)
        .one()
    )
    assert persisted_user.rename_tokens == before_tokens
    assert persisted_user.premium_theme_unlocked == before_theme
    assert persisted_progress.status == "completed"


def test_legacy_quest_event_hooks_are_noop(db_session, user):
    before_quests = db_session.query(models.Quest).count()
    before_progress = db_session.query(models.QuestProgress).count()

    quest_service.handle_event(
        db_session,
        user,
        "resources_collected",
        {"wood": 10000, "stone": 10000, "iron": 10000, "gold": 10000},
    )

    assert db_session.query(models.Quest).count() == before_quests
    assert db_session.query(models.QuestProgress).count() == before_progress


def test_help_articles_come_from_live_balance_catalog(client):
    response = client.get("/wiki/search", params={"q": "Economía"})

    assert response.status_code == 200
    articles = response.json()
    economy = next(article for article in articles if article["title"] == "Economía y producción")
    assert f"Versión de balance: `{balance.BALANCE_VERSION}`" in economy["content_markdown"]
    assert str(balance.BUILDING_COST_GROWTH) in economy["content_markdown"]
