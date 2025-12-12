from pydantic import BaseModel

class ItemTemplateBase(BaseModel):
    name: str
    description: str
    slot: str
    rarity: str
    bonus_type: str
    bonus_value: float

class ItemTemplateRead(ItemTemplateBase):
    id: int
    class Config:
        orm_mode = True

class HeroItemBase(BaseModel):
    hero_id: int
    template_id: int

class HeroItemRead(HeroItemBase):
    id: int
    is_equipped: bool
    template: ItemTemplateRead
    class Config:
        orm_mode = True
