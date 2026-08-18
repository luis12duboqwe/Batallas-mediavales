from pydantic import BaseModel, ConfigDict


class TroopBase(BaseModel):
    unit_type: str


class TroopCreate(TroopBase):
    quantity: int


class TroopRead(TroopBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quantity: int


class ResearchRequest(BaseModel):
    city_id: int
    unit_type: str
