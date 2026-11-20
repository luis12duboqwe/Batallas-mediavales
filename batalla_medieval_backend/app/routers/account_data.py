"""Authenticated account-data export; no broad ORM serialization."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..services.account_export import build_account_export
from .auth import get_current_user

# Dedicated privacy cases reuse the established support moderation workflow.
# This is a human review request, NEVER an automated account deletion.
PRIVACY_SUBJECTS = {
    "erasure": "[PRIVACY] Solicitud de eliminación de cuenta",
    "rectification": "[PRIVACY] Solicitud de corrección de datos",
    "retention": "[PRIVACY] Consulta sobre retención de datos",
    "other": "[PRIVACY] Consulta sobre privacidad",
}
ACTIVE_STATUSES = ("open", "in_progress")


class PrivacyRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["erasure", "rectification", "retention", "other"]
    details: str = Field(default="", max_length=1000)

    @field_validator("details", mode="before")
    @classmethod
    def strip_details(cls, value):
        return value.strip() if isinstance(value, str) else value


class PrivacyRequestRead(BaseModel):
    id: int
    kind: Literal["erasure", "rectification", "retention", "other"]
    status: Literal["open", "in_progress", "resolved", "closed"]
    created_at: datetime
    updated_at: datetime
    resolution: str | None = None


def _to_privacy_request(case: models.SupportCase) -> PrivacyRequestRead:
    kind = next(key for key, subject in PRIVACY_SUBJECTS.items() if case.subject == subject)
    return PrivacyRequestRead(
        id=case.id, kind=kind, status=case.status,
        created_at=case.created_at, updated_at=case.updated_at,
        resolution=case.resolution,
    )



router = APIRouter(prefix="/auth", tags=["Account data"])


@router.get("/me/export")
def export_my_account(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    payload = build_account_export(db, current_user)
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "Content-Disposition": 'attachment; filename="medievol-datos-cuenta.json"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/me/privacy-requests", response_model=list[PrivacyRequestRead])
def my_privacy_requests(
    response: Response,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "private, no-store"
    cases = (
        db.query(models.SupportCase)
        .filter(
            models.SupportCase.requester_id == current_user.id,
            models.SupportCase.subject.in_(tuple(PRIVACY_SUBJECTS.values())),
        )
        .order_by(models.SupportCase.created_at.desc(), models.SupportCase.id.desc())
        .all()
    )
    return [_to_privacy_request(case) for case in cases]


@router.post("/me/privacy-requests", response_model=PrivacyRequestRead)
def create_privacy_request(
    payload: PrivacyRequestCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "private, no-store"
    # Serialize concurrent requests for the same account in PostgreSQL. In
    # SQLite this lock is advisory; the endpoint has no destructive effects.
    db.query(models.User).filter(models.User.id == current_user.id).with_for_update().one()
    subject = PRIVACY_SUBJECTS[payload.kind]
    existing = (
        db.query(models.SupportCase)
        .filter(
            models.SupportCase.requester_id == current_user.id,
            models.SupportCase.subject == subject,
            models.SupportCase.status.in_(ACTIVE_STATUSES),
        )
        .order_by(models.SupportCase.id.desc())
        .first()
    )
    if existing:
        return _to_privacy_request(existing)
    description = (
        "El titular solicita revisión manual de privacidad. "
        "No se autoriza ni se ejecuta borrado de datos por esta solicitud."
    )
    if payload.details:
        description += "\nDetalles aportados: " + payload.details
    case = models.SupportCase(
        requester_id=current_user.id,
        world_id=None,
        subject=subject,
        description=description,
        status="open",
        priority="normal",
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return _to_privacy_request(case)
