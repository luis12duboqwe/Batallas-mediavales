from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import premium as premium_service

router = APIRouter(prefix="/premium", tags=["premium"])


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


@router.get("/status", response_model=schemas.PremiumStatusRead)
def get_status(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return premium_service.get_or_create_status(db, current_user)


@router.post("/buy", response_model=schemas.PremiumStatusRead)
def buy_feature(
    payload: schemas.PremiumPurchase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        return premium_service.buy_feature(db, current_user, payload.feature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/use")
def use_feature(
    payload: schemas.PremiumUseAction,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        result = premium_service.use_premium_action(
            db,
            current_user,
            payload.action,
            city_id=payload.city_id,
            queue_id=payload.queue_id,
            new_value=payload.new_value,
            bookmark=payload.bookmark.dict() if payload.bookmark else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if isinstance(result, models.City):
        return {"city": schemas.CityRead.from_orm(result)}
    if isinstance(result, models.User):
        return {"user": result.username}
    if isinstance(result, models.MapBookmark):
        return {"bookmark": schemas.MapBookmarkRead.from_orm(result)}
    return {"status": schemas.PremiumStatusRead.from_orm(result)}


@router.post("/grant", response_model=schemas.PremiumStatusRead)
def grant_rubies(
    payload: schemas.GrantRubies,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        return premium_service.grant_rubies(db, user, payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
