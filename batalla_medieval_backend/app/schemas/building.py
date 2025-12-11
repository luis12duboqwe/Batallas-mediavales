from pydantic import BaseModel


class BuildingBase(BaseModel):
    name: str


class BuildingCreate(BuildingBase):
    level: int = 1


class BuildingRead(BuildingBase):
    id: int
    level: int

    class Config:
        orm_mode = True
