from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import forum as forum_service
from ..services import alliance as alliance_service

router = APIRouter(tags=["forum"])

@router.get("/alliance/{alliance_id}/threads", response_model=list[schemas.ForumThreadRead])
def list_threads(
    alliance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    alliance_service.require_membership(db, alliance_id, current_user.id)
    return forum_service.list_threads(db, alliance_id)

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
    # Need to check if user belongs to the alliance of the thread
    thread = db.query(models.ForumThread).filter(models.ForumThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
        
    alliance_service.require_membership(db, thread.alliance_id, current_user.id)
    return forum_service.get_thread(db, thread_id)

@router.post("/threads/{thread_id}/reply", response_model=schemas.ForumPostRead)
def reply_thread(
    thread_id: int,
    payload: schemas.ForumPostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    thread = db.query(models.ForumThread).filter(models.ForumThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
        
    alliance_service.require_membership(db, thread.alliance_id, current_user.id)
    return forum_service.create_reply(db, thread_id, current_user, payload)
