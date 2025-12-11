from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship

from ..database import Base


class UserItem(Base):
    __tablename__ = "user_items"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    item_id = Column(Integer, ForeignKey("shop_items.id"), primary_key=True)
    acquired_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="items")
    item = relationship("ShopItem", back_populates="owners")

