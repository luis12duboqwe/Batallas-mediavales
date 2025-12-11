from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.admin import require_admin
from ..routers.auth import get_current_user
from ..services import theme as theme_service

router = APIRouter(prefix="/theme", tags=["themes"])


@router.get("/", response_model=List[schemas.ThemeRead])
def list_all_themes(db: Session = Depends(get_db)):
    return theme_service.list_themes(db)


@router.post("/", response_model=schemas.ThemeRead)
def create_new_theme(
    payload: schemas.ThemeCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    return theme_service.create_theme(db, payload)


@router.get("/{theme_id}", response_model=schemas.ThemeRead)
def get_theme(theme_id: int, db: Session = Depends(get_db)):
    theme = theme_service.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.put("/{theme_id}", response_model=schemas.ThemeRead)
def update_theme(
    theme_id: int,
    payload: schemas.ThemeUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    try:
        return theme_service.update_theme(db, theme_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{theme_id}")
def delete_theme(
    theme_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    try:
        theme_service.delete_theme(db, theme_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"detail": "Theme deleted"}


@router.post("/grant", response_model=schemas.ThemeOwnershipRead)
def grant_theme(
    payload: schemas.ThemeOwnershipCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    try:
        return theme_service.grant_theme_to_user(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/select/{theme_id}", response_model=schemas.ThemeApplied)
def select_theme(
    theme_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        theme_data = theme_service.select_theme(db, current_user, theme_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return theme_data


@router.get("/current", response_model=schemas.ThemeApplied)
def get_current_theme(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    try:
        return theme_service.get_current_theme(db, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
