from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class ForumPostBase(BaseModel):
    content: str


class ForumPostCreate(ForumPostBase):
    pass


class ForumPostRead(ForumPostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    author_id: int
    author_name: str
    created_at: datetime


class ForumThreadBase(BaseModel):
    title: str


class ForumThreadCreate(ForumThreadBase):
    content: str


class ForumThreadRead(ForumThreadBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alliance_id: int
    author_id: int
    author_name: str
    is_pinned: bool
    is_locked: bool
    created_at: datetime
    updated_at: datetime
    reply_count: int = 0


class ForumThreadDetail(ForumThreadRead):
    posts: List[ForumPostRead] = Field(default_factory=list)
