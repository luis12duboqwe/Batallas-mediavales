from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import models


def list_items(db: Session) -> list[models.ShopItem]:
    return db.query(models.ShopItem).all()


def purchase_item(db: Session, user: models.User, item_id: int) -> models.UserItem:
    item = db.query(models.ShopItem).filter(models.ShopItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    owned = (
        db.query(models.UserItem)
        .filter(models.UserItem.user_id == user.id, models.UserItem.item_id == item.id)
        .first()
    )
    if owned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item already owned")

    if user.rubies_balance < item.price_rubies:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient rubies")

    user.rubies_balance -= item.price_rubies
    user_item = models.UserItem(user_id=user.id, item_id=item.id)
    db.add(user_item)
    db.commit()
    db.refresh(user)
    db.refresh(user_item)
    return user_item


def list_user_items(db: Session, user: models.User) -> list[models.UserItem]:
    return (
        db.query(models.UserItem)
        .filter(models.UserItem.user_id == user.id)
        .join(models.ShopItem)
        .all()
    )

