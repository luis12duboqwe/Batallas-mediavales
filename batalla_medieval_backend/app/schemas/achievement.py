from pydantic import BaseModel, ConfigDict


class AchievementBase(BaseModel):
    title: str
    description: str
    category: str
    requirement_type: str
    requirement_value: int


class AchievementRead(AchievementBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    honor_only: bool = True


class AchievementProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    world_id: int
    status: str
    current_progress: int


class AchievementWithProgress(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    achievement: AchievementRead
    progress: AchievementProgressRead
