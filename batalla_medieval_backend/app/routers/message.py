from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user

router = APIRouter(prefix="/message", tags=["message"])


@router.post("/send", response_model=schemas.MessageRead)
def send_message(
    payload: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    receiver = db.query(models.User).filter(models.User.id == payload.receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found")

    message = models.Message(
        sender_id=current_user.id,
        receiver_id=payload.receiver_id,
        subject=payload.subject,
        content=payload.content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("/inbox", response_model=list[schemas.MessageRead])
def inbox(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    messages = (
        db.query(models.Message)
        .filter(models.Message.receiver_id == current_user.id)
        .order_by(models.Message.timestamp.desc())
        .all()
    )
    return messages


@router.get("/sent", response_model=list[schemas.MessageRead])
def sent_messages(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    messages = (
        db.query(models.Message)
        .filter(models.Message.sender_id == current_user.id)
        .order_by(models.Message.timestamp.desc())
        .all()
    )
    return messages


@router.get("/{message_id}", response_model=schemas.MessageRead)
def read_message(
    message_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    if current_user.id not in {message.sender_id, message.receiver_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this message")

    if not message.read and message.receiver_id == current_user.id:
        message.read = True
        db.commit()
        db.refresh(message)

    return message


@router.delete("/{message_id}")
def delete_message(
    message_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    if current_user.id not in {message.sender_id, message.receiver_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this message")

    db.delete(message)
    db.commit()
    return {"detail": "Message deleted"}
