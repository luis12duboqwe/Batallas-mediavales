from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class QuestBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quest_id: str
    title: str
    description: str
    requirements: Dict[str, Any]
    reward: Dict[str, Any]
    is_tutorial: bool = False


class QuestRead(QuestBase):
    status: str
    progress_data: Dict[str, Any] = Field(default_factory=dict)


class QuestListResponse(BaseModel):
    quests: List[QuestRead]
    tutorial_completed: bool


class QuestClaimResponse(BaseModel):
    quest: QuestRead
    granted_reward: Dict[str, Any]
