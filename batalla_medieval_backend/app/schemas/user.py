from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr

from .world import WorldRead


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int
    created_at: datetime
    protection_ends_at: Optional[datetime] = None
    is_admin: bool = False
    is_frozen: bool = False
    freeze_reason: Optional[str] = None
    rename_tokens: int = 0
    premium_theme_unlocked: bool = False
    world_id: Optional[int] = None

    class Config:
        orm_mode = True


class Token(BaseModel):
    access_token: str
    token_type: str
    worlds: List[WorldRead] = []


class TokenData(BaseModel):
    username: Optional[str] = None
