from pydantic import BaseModel, ConfigDict


class AchievementBase(BaseModel):
    title: str
    description: str
    category: str
    requirement_type: str
    requirement_value: int
    reward_type: str
    reward_value: str


class AchievementRead(AchievementBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class AchievementProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    current_progress: int


class AchievementWithProgress(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    achievement: AchievementRead
    progress: AchievementProgressRead
