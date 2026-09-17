"""Compatibility shim for the retired legacy quest system.

BM-0075 makes ``app.services.tutorial`` the only authoritative mandatory-mission
system. Historical quest tables stay in place for backwards-compatible schema
history, but runtime gameplay must not create progress or grant rewards through
this module anymore.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from sqlalchemy.orm import Session

from .. import models

DEFAULT_QUESTS: tuple[()] = ()
LEGACY_QUEST_RETIREMENT_MESSAGE = (
    "Legacy quests were retired in BM-0075; use the server-authoritative tutorial"
)


def ensure_default_quests(db: Session) -> List[models.Quest]:
    """Do not seed the retired quest catalogue."""

    _ = db
    return []


def handle_event(
    db: Session,
    user: models.User,
    event_type: str,
    event_data: Dict[str, Any] | None = None,
) -> None:
    """Compatibility no-op for older call sites.

    Keeping this function avoids coupling BM-0075 to unrelated gameplay
    services while guaranteeing those hooks cannot create progress or rewards.
    """

    _ = (db, user, event_type, event_data)


def list_quests_for_user(db: Session, user: models.User) -> List[models.QuestProgress]:
    _ = (db, user)
    return []


def claim_reward(
    db: Session,
    user: models.User,
    quest_identifier: str,
) -> tuple[models.QuestProgress, Dict[str, Any]]:
    _ = (db, user, quest_identifier)
    raise ValueError(LEGACY_QUEST_RETIREMENT_MESSAGE)


def serialize_progress(progress: models.QuestProgress) -> Dict[str, Any]:
    """Serialize historical rows for maintenance/debug tooling only."""

    quest = progress.quest
    return {
        "quest_id": quest.quest_id,
        "title": quest.title,
        "description": quest.description,
        "requirements": quest.requirements,
        "reward": quest.reward,
        "is_tutorial": quest.is_tutorial,
        "status": progress.status,
        "progress_data": progress.progress_data or {},
    }


def tutorial_completed(progresses: Iterable[models.QuestProgress]) -> bool:
    """Legacy progress never decides tutorial completion anymore."""

    _ = progresses
    return False
