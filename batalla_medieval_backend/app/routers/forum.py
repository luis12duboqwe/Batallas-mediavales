from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import alliance as alliance_service
from ..services import community as community_service
from ..services import forum as forum_service

router = APIRouter(tags=["forum"])


def _thread_for_member(
    db: Session,
    thread_id: int,
    current_user: models.User,
) -> models.ForumThread:
    thread = db.query(models.ForumThread).filter(models.ForumThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    alliance_service.require_membership(db, thread.alliance_id, current_user.id)
    return thread


@router.get("/alliance/{alliance_id}/threads", response_model=list[schemas.ForumThreadRead])
def list_threads(
    alliance_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    alliance_service.require_membership(db, alliance_id, current_user.id)
    return forum_service.list_threads(db, alliance_id, limit=limit, offset=offset)


@router.post("/alliance/{alliance_id}/threads", response_model=schemas.ForumThreadDetail)
def create_thread(
    alliance_id: int,
    payload: schemas.ForumThreadCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    alliance_service.require_membership(db, alliance_id, current_user.id)
    return forum_service.create_thread(db, alliance_id, current_user, payload)


@router.get("/threads/{thread_id}", response_model=schemas.ForumThreadDetail)
def get_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _thread_for_member(db, thread_id, current_user)
    return forum_service.get_thread(db, thread_id)


@router.post("/threads/{thread_id}/reply", response_model=schemas.ForumPostRead)
def reply_thread(
    thread_id: int,
    payload: schemas.ForumPostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _thread_for_member(db, thread_id, current_user)
    return forum_service.create_reply(db, thread_id, current_user, payload)


@router.patch("/threads/{thread_id}/moderation", response_model=schemas.ForumThreadDetail)
def moderate_thread(
    thread_id: int,
    payload: schemas.ForumThreadModeration,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    thread = _thread_for_member(db, thread_id, current_user)
    membership = alliance_service.require_membership(db, thread.alliance_id, current_user.id)
    community_service.require_capability(membership, community_service.CAP_MODERATE_FORUM)
    return forum_service.moderate_thread(db, thread_id, payload)
