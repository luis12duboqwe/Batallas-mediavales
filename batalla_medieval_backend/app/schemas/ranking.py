from pydantic import BaseModel


class PlayerRanking(BaseModel):
    user_id: int
    username: str
    points: int
    attacker_points: int = 0
    defender_points: int = 0
    world_id: int

    class Config:
        orm_mode = True


class AllianceRanking(BaseModel):
    alliance_id: int
    name: str
    points: int
    world_id: int

    class Config:
        orm_mode = True
