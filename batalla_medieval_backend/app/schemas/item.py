from pydantic import BaseModel, ConfigDict


class ItemTemplateBase(BaseModel):
    name: str
    description: str
    slot: str
    rarity: str
    bonus_type: str
    bonus_value: float


class ItemTemplateRead(ItemTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class HeroItemBase(BaseModel):
    hero_id: int
    template_id: int


class HeroItemRead(HeroItemBase):
    id: int
    is_equipped: bool
    name: str
    description: str
    slot: str
    rarity: str
    bonus_type: str
    bonus_value: float
