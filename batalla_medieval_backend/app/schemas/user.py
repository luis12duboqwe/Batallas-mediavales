from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from .world import WorldRead


MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
COMMON_PASSWORDS = {
    "1234567890",
    "password123",
    "qwerty12345",
    "letmein123",
}


def _validate_password(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(value) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")
    if not any(character.isalpha() for character in value):
        raise ValueError("Password must contain at least one letter")
    if not any(character.isdigit() for character in value):
        raise ValueError("Password must contain at least one number")
    if value.lower() in COMMON_PASSWORDS:
        raise ValueError("Password is too common")
    return value


class UserBase(BaseModel):
    username: str
    email: EmailStr
    email_notifications: bool = False
    language: str = "en"


class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    email_notifications: Optional[bool] = None
    language: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: Optional[str]) -> Optional[str]:
        return _validate_password(value) if value is not None else value


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

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


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class Token(BaseModel):
    access_token: str
    token_type: str
    language: str
    worlds: List[WorldRead] = []


class TokenData(BaseModel):
    username: Optional[str] = None
