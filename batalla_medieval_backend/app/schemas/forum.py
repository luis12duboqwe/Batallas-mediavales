from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class ForumPostBase(BaseModel):
    content: str

class ForumPostCreate(ForumPostBase):
    pass

class ForumPostRead(ForumPostBase):
    id: int
    thread_id: int
    author_id: int
    author_name: str
    created_at: datetime
    
    class Config:
        orm_mode = True

class ForumThreadBase(BaseModel):
    title: str

class ForumThreadCreate(ForumThreadBase):
    content: str # First post content

class ForumThreadRead(ForumThreadBase):
    id: int
    alliance_id: int
    author_id: int
    author_name: str
    is_pinned: bool
    is_locked: bool
    created_at: datetime
    updated_at: datetime
    reply_count: int = 0
    
    class Config:
        orm_mode = True

class ForumThreadDetail(ForumThreadRead):
    posts: List[ForumPostRead] = []
