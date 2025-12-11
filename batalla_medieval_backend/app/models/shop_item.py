from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class ShopItem(Base):
    __tablename__ = "shop_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=False)
    type = Column(String, nullable=False)
    price_rubies = Column(Integer, nullable=False)
    rarity = Column(String, nullable=False)
    preview_url = Column(String, nullable=True)

    owners = relationship("UserItem", back_populates="item", cascade="all, delete-orphan")

