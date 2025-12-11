from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import shop as shop_service

router = APIRouter(prefix="/shop", tags=["shop"])


@router.get("/items", response_model=list[schemas.ShopItemRead])
def list_items(db: Session = Depends(get_db)):
    return shop_service.list_items(db)


@router.post("/buy/{item_id}", response_model=schemas.PurchaseResponse)
def buy_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    user_item = shop_service.purchase_item(db, current_user, item_id)
    return schemas.PurchaseResponse(
        item=user_item.item,
        acquired_at=user_item.acquired_at,
        remaining_rubies=current_user.rubies_balance,
    )


@router.get("/my_items", response_model=list[schemas.UserItemRead])
def my_items(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return shop_service.list_user_items(db, current_user)

