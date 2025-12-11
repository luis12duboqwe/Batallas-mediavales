from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

WIKI_CATEGORIES = (
    "buildings",
    "troops",
    "combat",
    "economy",
    "espionage",
    "events",
    "beginner",
)


class WikiArticleBase(BaseModel):
    title: str = Field(..., min_length=3)
    category: Literal[
        "buildings", "troops", "combat", "economy", "espionage", "events", "beginner"
    ]
    content_markdown: str


class WikiArticleCreate(WikiArticleBase):
    pass


class WikiArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3)
    category: Literal[
        "buildings", "troops", "combat", "economy", "espionage", "events", "beginner"
    ] | None = None
    content_markdown: str | None = None


class WikiArticleRead(WikiArticleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
