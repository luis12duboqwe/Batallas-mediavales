from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import admin_permissions, moderation

router = APIRouter(prefix="/admin/moderation", tags=["admin-moderation"])


class ModerationUpdate(BaseModel):
    hidden: bool
    reason: str
    support_case_id: int | None = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Moderation reason is required")
        return normalized


class ModerationTargetRead(BaseModel):
    kind: str
    id: int
    content: str
    is_hidden: bool
    moderation_reason: str | None = None
    moderated_by_id: int | None = None
    moderated_at: datetime | None = None


def _serialize(kind: str, target) -> ModerationTargetRead:
    return ModerationTargetRead(
        kind=kind,
        id=target.id,
        content=target.content,
        is_hidden=bool(target.is_hidden),
        moderation_reason=target.moderation_reason,
        moderated_by_id=target.moderated_by_id,
        moderated_at=target.moderated_at,
    )


@router.get("/chat/{message_id}", response_model=ModerationTargetRead)
def get_chat_message_for_moderation(
    message_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("content.moderate")
    ),
):
    return _serialize("chat_message", moderation.get_target(db, "chat_message", message_id))


@router.patch("/chat/{message_id}", response_model=schemas.LogRead)
def moderate_chat_message(
    message_id: int,
    payload: ModerationUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("content.moderate")
    ),
):
    return moderation.set_hidden(
        db,
        kind="chat_message",
        target_id=message_id,
        hidden=payload.hidden,
        reason=payload.reason,
        admin_user=current_admin,
        support_case_id=payload.support_case_id,
    )


@router.get("/forum/{post_id}", response_model=ModerationTargetRead)
def get_forum_post_for_moderation(
    post_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("content.moderate")
    ),
):
    return _serialize("forum_post", moderation.get_target(db, "forum_post", post_id))


@router.patch("/forum/{post_id}", response_model=schemas.LogRead)
def moderate_forum_post(
    post_id: int,
    payload: ModerationUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("content.moderate")
    ),
):
    return moderation.set_hidden(
        db,
        kind="forum_post",
        target_id=post_id,
        hidden=payload.hidden,
        reason=payload.reason,
        admin_user=current_admin,
        support_case_id=payload.support_case_id,
    )
