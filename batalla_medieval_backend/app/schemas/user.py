from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr

from .world import WorldRead


class UserBase(BaseModel):
    username: str
    email: EmailStr
    email_notifications: bool = False
    language: str = "en"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    email_notifications: Optional[bool] = None
    language: Optional[str] = None


class UserRead(UserBase):
    id: int
    created_at: datetime
    last_active_at: datetime
    protection_ends_at: Optional[datetime] = None
    is_admin: bool = False
    rubies_balance: int
    is_frozen: bool = False
    freeze_reason: Optional[str] = None
    rename_tokens: int = 0
    premium_theme_unlocked: bool = False
    world_id: Optional[int] = None

    class Config:
        orm_mode = True


class UserPublic(BaseModel):
    id: int
    username: str

    class Config:
        orm_mode = True


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    language: str
    worlds: List[WorldRead] = []


class TokenData(BaseModel):
    username: Optional[str] = None
