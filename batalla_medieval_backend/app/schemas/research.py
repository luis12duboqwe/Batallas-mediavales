from pydantic import BaseModel

class ResearchBase(BaseModel):
    tech_name: str
    level: int

class ResearchCreate(ResearchBase):
    pass

class ResearchRead(ResearchBase):
    id: int
    city_id: int

    class Config:
        orm_mode = True
