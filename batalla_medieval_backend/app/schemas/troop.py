from pydantic import BaseModel


class TroopBase(BaseModel):
    unit_type: str


class TroopCreate(TroopBase):
    quantity: int


class TroopRead(TroopBase):
    id: int
    quantity: int

    class Config:
        orm_mode = True


class ResearchRequest(BaseModel):
    city_id: int
    unit_type: str
