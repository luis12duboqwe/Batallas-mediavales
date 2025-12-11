from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel


class ThemeBase(BaseModel):
    name: str
    primary_color: str
    secondary_color: str
    background_url: str
    icon_pack_url: str
    locked: bool = True


class ThemeCreate(ThemeBase):
    pass


class ThemeUpdate(BaseModel):
    name: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    background_url: Optional[str] = None
    icon_pack_url: Optional[str] = None
    locked: Optional[bool] = None


class ThemeRead(ThemeBase):
    id: int

    class Config:
        orm_mode = True


class ThemeOwnershipCreate(BaseModel):
    user_id: int
    theme_id: int
    source: str


class ThemeOwnershipRead(BaseModel):
    id: int
    user_id: int
    theme_id: int
    source: str
    created_at: datetime

    class Config:
        orm_mode = True


class ThemeApplied(ThemeRead):
    css_variables: Dict[str, str]
    assets: Dict[str, str]
