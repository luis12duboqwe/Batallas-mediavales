from pydantic import BaseModel, ConfigDict


class PlayerRanking(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    points: int
    attacker_points: int = 0
    defender_points: int = 0
    world_id: int


class AllianceRanking(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alliance_id: int
    name: str
    points: int
    world_id: int
