from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict


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
    model_config = ConfigDict(from_attributes=True)

    id: int


class ThemeOwnershipCreate(BaseModel):
    user_id: int
    theme_id: int
    source: str


class ThemeOwnershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    theme_id: int
    source: str
    created_at: datetime


class ThemeApplied(ThemeRead):
    css_variables: Dict[str, str]
    assets: Dict[str, str]
