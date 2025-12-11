from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, Integer, String, Text

from ..database import Base


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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
