import pytest
from fastapi import HTTPException

from app import models, schemas
from app.schemas import forum as forum_schema
from app.services import forum


def _forum_alliance(db_session, world, user):
    alliance = models.Alliance(
        name="Forum Test Alliance",
        world_id=world.id,
        leader_id=user.id,
        diplomacy="neutral",
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
    db_session.commit()
    db_session.refresh(alliance)
    return alliance


def test_thread_creation_persists_opening_post_in_same_domain_operation(db_session, user):
    world = db_session.query(models.World).first()
    alliance = _forum_alliance(db_session, world, user)

    detail = forum.create_thread(
        db_session,
        alliance.id,
        user,
        schemas.ForumThreadCreate(title="  Estrategia  ", content="  Primer plan  "),
    )

    assert detail.title == "Estrategia"
    assert detail.reply_count == 0
    assert len(detail.posts) == 1
    assert detail.posts[0].content == "Primer plan"
    assert db_session.query(models.ForumThread).count() == 1
    assert db_session.query(models.ForumPost).count() == 1


def test_locked_thread_rejects_reply_and_moderation_is_reversible(db_session, user):
    world = db_session.query(models.World).first()
    alliance = _forum_alliance(db_session, world, user)
    detail = forum.create_thread(
        db_session,
        alliance.id,
        user,
        schemas.ForumThreadCreate(title="Avisos", content="Inicio"),
    )

    moderated = forum.moderate_thread(
        db_session,
        detail.id,
        schemas.ForumThreadModeration(is_locked=True, is_pinned=True),
    )
    assert moderated.is_locked is True
    assert moderated.is_pinned is True

    with pytest.raises(HTTPException) as exc:
        forum.create_reply(
            db_session,
            detail.id,
            user,
            schemas.ForumPostCreate(content="No debe entrar"),
        )
    assert exc.value.status_code == 400
    assert db_session.query(models.ForumPost).count() == 1

    reopened = forum.moderate_thread(
        db_session,
        detail.id,
        schemas.ForumThreadModeration(is_locked=False),
    )
    assert reopened.is_locked is False

    reply = forum.create_reply(
        db_session,
        detail.id,
        user,
        schemas.ForumPostCreate(content="Respuesta válida"),
    )
    assert reply.content == "Respuesta válida"
    refreshed = forum.get_thread(db_session, detail.id)
    assert refreshed.reply_count == 1
    assert len(refreshed.posts) == 2


def test_thread_listing_is_bounded_and_stable(db_session, user):
    world = db_session.query(models.World).first()
    alliance = _forum_alliance(db_session, world, user)
    for index in range(3):
        forum.create_thread(
            db_session,
            alliance.id,
            user,
            schemas.ForumThreadCreate(title=f"Tema {index}", content="Contenido"),
        )

    first_page = forum.list_threads(db_session, alliance.id, limit=2, offset=0)
    second_page = forum.list_threads(db_session, alliance.id, limit=2, offset=2)
    assert len(first_page) == 2
    assert len(second_page) == 1
    assert {row.id for row in first_page}.isdisjoint({row.id for row in second_page})


def test_forum_schema_rejects_oversized_payloads():
    with pytest.raises(Exception):
        schemas.ForumThreadCreate(
            title="x" * (forum_schema.FORUM_TITLE_MAX_LENGTH + 1),
            content="ok",
        )
    with pytest.raises(Exception):
        schemas.ForumPostCreate(
            content="x" * (forum_schema.FORUM_POST_MAX_LENGTH + 1),
        )
