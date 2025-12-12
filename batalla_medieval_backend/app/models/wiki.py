from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, Integer, String, Text

from ..database import Base
from ..utils import get_utc_now


class WikiCategory(str, Enum):
    BUILDINGS = "buildings"
    TROOPS = "troops"
    COMBAT = "combat"
    ECONOMY = "economy"
    ESPIONAGE = "espionage"
    EVENTS = "events"
    BEGINNER = "beginner"


class WikiArticle(Base):
    __tablename__ = "wiki_articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, unique=True)
    category = Column(SAEnum(WikiCategory), nullable=False, index=True)
    content_markdown = Column(Text, nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now, nullable=False)
