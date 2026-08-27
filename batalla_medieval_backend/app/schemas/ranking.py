from pydantic import BaseModel, ConfigDict


class PlayerRanking(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    user_id: int
    username: str
    points: int
    world_id: int


class AllianceRanking(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    alliance_id: int
    name: str
    points: int
    world_id: int
