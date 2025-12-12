from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float
from sqlalchemy.orm import relationship, Mapped, mapped_column

from ..database import Base

class ItemTemplate(Base):
    __tablename__ = "item_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    slot: Mapped[str] = mapped_column(String, nullable=False)  # head, body, feet, weapon, horse, artifact
    rarity: Mapped[str] = mapped_column(String, default="common") # common, rare, epic, legendary
    
    # Bonuses
    bonus_type: Mapped[str] = mapped_column(String, nullable=False) # e.g., "attack_infantry", "production_wood", "speed"
    bonus_value: Mapped[float] = mapped_column(Float, default=0.0) # e.g., 0.10 for 10%

    hero_items = relationship("HeroItem", back_populates="template")


class HeroItem(Base):
    __tablename__ = "hero_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hero_id: Mapped[int] = mapped_column(Integer, ForeignKey("heroes.id"), nullable=False)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("item_templates.id"), nullable=False)
    is_equipped: Mapped[bool] = mapped_column(Boolean, default=False)

    hero = relationship("Hero", back_populates="items")
    template = relationship("ItemTemplate", back_populates="hero_items")
