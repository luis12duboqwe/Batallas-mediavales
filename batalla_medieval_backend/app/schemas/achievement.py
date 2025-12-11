from pydantic import BaseModel


class AchievementBase(BaseModel):
    title: str
    description: str
    category: str
    requirement_type: str
    requirement_value: int
    reward_type: str
    reward_value: str


class AchievementRead(AchievementBase):
    id: int

    class Config:
        orm_mode = True


class AchievementProgressRead(BaseModel):
    status: str
    current_progress: int

    class Config:
        orm_mode = True


class AchievementWithProgress(BaseModel):
    achievement: AchievementRead
    progress: AchievementProgressRead

    class Config:
        orm_mode = True
