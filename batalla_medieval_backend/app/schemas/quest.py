from typing import Any, Dict, List

from pydantic import BaseModel


class QuestBase(BaseModel):
    quest_id: str
    title: str
    description: str
    requirements: Dict[str, Any]
    reward: Dict[str, Any]
    is_tutorial: bool = False

    class Config:
        orm_mode = True


class QuestRead(QuestBase):
    status: str
    progress_data: Dict[str, Any] = {}


class QuestListResponse(BaseModel):
    quests: List[QuestRead]
    tutorial_completed: bool


class QuestClaimResponse(BaseModel):
    quest: QuestRead
    granted_reward: Dict[str, Any]
