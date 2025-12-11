from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("/", response_model=schemas.MessageRead)
def send_message(
    payload: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    recipient = db.query(models.User).filter(models.User.id == payload.recipient_id).first()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    message = models.Message(sender_id=current_user.id, recipient_id=payload.recipient_id, content=payload.content)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("/", response_model=list[schemas.MessageRead])
def inbox(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    messages = db.query(models.Message).filter(models.Message.recipient_id == current_user.id).all()
    return messages
