from pydantic import BaseModel, ConfigDict


class ResearchBase(BaseModel):
    tech_name: str
    level: int


class ResearchCreate(ResearchBase):
    pass


class ResearchRead(ResearchBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    city_id: int
