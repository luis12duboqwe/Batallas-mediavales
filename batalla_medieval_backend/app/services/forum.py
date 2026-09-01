from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..utils import utc_now
from . import world_lifecycle

MAX_THREADS_PAGE = 100


def _normalize(value: str, *, field: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} cannot be empty",
        )
    return normalized


def list_threads(
    db: Session,
    alliance_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[schemas.ForumThreadRead]:
    safe_limit = max(1, min(int(limit), MAX_THREADS_PAGE))
    safe_offset = max(0, int(offset))
    threads = (
        db.query(models.ForumThread)
        .filter(models.ForumThread.alliance_id == alliance_id)
        .order_by(
            models.ForumThread.is_pinned.desc(),
            models.ForumThread.updated_at.desc(),
            models.ForumThread.id.desc(),
        )
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )

    result: list[schemas.ForumThreadRead] = []
    for thread in threads:
        total_posts = (
            db.query(models.ForumPost)
            .filter(models.ForumPost.thread_id == thread.id)
            .count()
        )
        result.append(
            schemas.ForumThreadRead(
                id=thread.id,
                alliance_id=thread.alliance_id,
                author_id=thread.author_id,
                author_name=thread.author.username,
                title=thread.title,
                is_pinned=bool(thread.is_pinned),
                is_locked=bool(thread.is_locked),
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                reply_count=max(total_posts - 1, 0),
            )
        )
    return result


def get_thread(db: Session, thread_id: int):
    thread = db.query(models.ForumThread).filter(models.ForumThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    posts = (
        db.query(models.ForumPost)
        .filter(models.ForumPost.thread_id == thread_id)
        .order_by(models.ForumPost.created_at.asc(), models.ForumPost.id.asc())
        .all()
    )

    post_reads = [
        schemas.ForumPostRead(
            id=post.id,
            thread_id=post.thread_id,
            author_id=post.author_id,
            author_name=post.author.username,
            content=post.content,
            created_at=post.created_at,
        )
        for post in posts
    ]

    return schemas.ForumThreadDetail(
        id=thread.id,
        alliance_id=thread.alliance_id,
        author_id=thread.author_id,
        author_name=thread.author.username,
        title=thread.title,
        is_pinned=bool(thread.is_pinned),
        is_locked=bool(thread.is_locked),
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        reply_count=max(len(posts) - 1, 0),
        posts=post_reads,
    )


def create_thread(
    db: Session,
    alliance_id: int,
    user: models.User,
    payload: schemas.ForumThreadCreate,
):
    """Create thread and opening post in one transaction."""

    try:
        alliance = db.query(models.Alliance).filter(models.Alliance.id == alliance_id).one_or_none()
        if alliance is None:
            raise HTTPException(status_code=404, detail="Alliance not found")
        world_lifecycle.require_world_open_http(db, alliance.world_id)
        now = utc_now()
        thread = models.ForumThread(
            alliance_id=alliance_id,
            author_id=user.id,
            title=_normalize(payload.title, field="Title"),
            updated_at=now,
        )
        db.add(thread)
        db.flush()

        post = models.ForumPost(
            thread_id=thread.id,
            author_id=user.id,
            content=_normalize(payload.content, field="Content"),
            created_at=now,
        )
        db.add(post)
        db.commit()
        db.refresh(thread)
        return get_thread(db, thread.id)
    except Exception:
        db.rollback()
        raise


def create_reply(
    db: Session,
    thread_id: int,
    user: models.User,
    payload: schemas.ForumPostCreate,
):
    try:
        thread = (
            db.query(models.ForumThread)
            .filter(models.ForumThread.id == thread_id)
            .with_for_update()
            .one_or_none()
        )
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        alliance = db.query(models.Alliance).filter(models.Alliance.id == thread.alliance_id).one()
        world_lifecycle.require_world_open_http(db, alliance.world_id)
        if thread.is_locked:
            raise HTTPException(status_code=400, detail="Thread is locked")

        now = utc_now()
        post = models.ForumPost(
            thread_id=thread.id,
            author_id=user.id,
            content=_normalize(payload.content, field="Content"),
            created_at=now,
        )
        db.add(post)
        thread.updated_at = now
        db.add(thread)
        db.commit()
        db.refresh(post)

        return schemas.ForumPostRead(
            id=post.id,
            thread_id=post.thread_id,
            author_id=post.author_id,
            author_name=user.username,
            content=post.content,
            created_at=post.created_at,
        )
    except Exception:
        db.rollback()
        raise


def moderate_thread(
    db: Session,
    thread_id: int,
    payload: schemas.ForumThreadModeration,
) -> schemas.ForumThreadDetail:
    try:
        thread = (
            db.query(models.ForumThread)
            .filter(models.ForumThread.id == thread_id)
            .with_for_update()
            .one_or_none()
        )
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        alliance = db.query(models.Alliance).filter(models.Alliance.id == thread.alliance_id).one()
        world_lifecycle.require_world_open_http(db, alliance.world_id)
        if payload.is_locked is None and payload.is_pinned is None:
            raise HTTPException(status_code=400, detail="No moderation change supplied")
        if payload.is_locked is not None:
            thread.is_locked = bool(payload.is_locked)
        if payload.is_pinned is not None:
            thread.is_pinned = bool(payload.is_pinned)
        thread.updated_at = utc_now()
        db.add(thread)
        db.commit()
        return get_thread(db, thread.id)
    except Exception:
        db.rollback()
        raise
