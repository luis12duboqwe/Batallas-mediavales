from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

FORUM_TITLE_MAX_LENGTH = 160
FORUM_POST_MAX_LENGTH = 5000


class ForumPostBase(BaseModel):
    content: str = Field(min_length=1, max_length=FORUM_POST_MAX_LENGTH)


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
    title: str = Field(min_length=1, max_length=FORUM_TITLE_MAX_LENGTH)


class ForumThreadCreate(ForumThreadBase):
    content: str = Field(min_length=1, max_length=FORUM_POST_MAX_LENGTH)


class ForumThreadModeration(BaseModel):
    is_locked: Optional[bool] = None
    is_pinned: Optional[bool] = None


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
