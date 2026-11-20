"""Authenticated account-data export; no broad ORM serialization."""

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..services.account_export import build_account_export
from .auth import get_current_user

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
