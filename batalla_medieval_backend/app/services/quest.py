from __future__ import annotations

from typing import Any, Dict, Iterable, List

from sqlalchemy.orm import Session

from .. import models

DEFAULT_QUESTS: List[Dict[str, Any]] = [
    {
        "quest_id": "tutorial_town_hall",
        "title": "Construye tu Ayuntamiento",
        "description": "Mejora tu Ayuntamiento al nivel 1.",
        "requirements": {"type": "building_finished", "building_type": "town_hall", "level": 1},
        "reward": {"resources": {"wood": 100, "clay": 100, "iron": 100}},
        "is_tutorial": True,
    },
    {
        "quest_id": "tutorial_warehouse",
        "title": "Construye un Almacén",
        "description": "Construye un Almacén para guardar más recursos.",
        "requirements": {"type": "building_finished", "building_type": "warehouse", "level": 1},
        "reward": {"resources": {"wood": 150, "clay": 150, "iron": 150}},
        "is_tutorial": True,
    },
    {
        "quest_id": "tutorial_farm",
        "title": "Construye una Granja",
        "description": "Construye una Granja para alimentar a tu población.",
        "requirements": {"type": "building_finished", "building_type": "farm", "level": 1},
        "reward": {"resources": {"wood": 150, "clay": 150, "iron": 150}},
        "is_tutorial": True,
    },
    {
        "quest_id": "tutorial_barracks",
        "title": "Construye Barracas",
        "description": "Construye Barracas para entrenar tropas.",
        "requirements": {"type": "building_finished", "building_type": "barracks", "level": 1},
        "reward": {"resources": {"wood": 200, "clay": 200, "iron": 200}},
        "is_tutorial": True,
    },
    {
        "quest_id": "tutorial_troops",
        "title": "Entrena tropas",
        "description": "Entrena 10 unidades de infantería básica.",
        "requirements": {"type": "troops_trained", "unit_type": "basic_infantry", "amount": 10},
        "reward": {"resources": {"wood": 300, "clay": 300, "iron": 300}},
        "is_tutorial": True,
    },
    {
        "quest_id": "tutorial_market",
        "title": "Construye un Mercado",
        "description": "Construye un Mercado para comerciar recursos.",
        "requirements": {"type": "building_finished", "building_type": "market", "level": 1},
        "reward": {"resources": {"wood": 250, "clay": 250, "iron": 250}},
        "is_tutorial": True,
    },
    {
        "quest_id": "gatherer",
        "title": "Recolecta recursos",
        "description": "Acumula 1000 recursos producidos en tus ciudades.",
        "requirements": {"type": "resources_collected", "amount": 1000},
        "reward": {"resources": {"wood": 300, "clay": 300, "iron": 400}},
        "is_tutorial": False,
    },
    {
        "quest_id": "join_alliance",
        "title": "Únete a una alianza",
        "description": "Acepta una invitación y forma parte de una alianza.",
        "requirements": {"type": "alliance_joined"},
        "reward": {"rename_tokens": 1},
        "is_tutorial": False,
    },
    {
        "quest_id": "first_attack",
        "title": "Envía tu primer ataque",
        "description": "Demuestra tu valor iniciando tu primera ofensiva.",
        "requirements": {"type": "attack_sent"},
        "reward": {"resources": {"wood": 200, "clay": 200, "iron": 200}},
        "is_tutorial": False,
    },
    {
        "quest_id": "first_spy",
        "title": "Envía tu primer espía",
        "description": "Lanza una misión de espionaje para conocer a tus vecinos.",
        "requirements": {"type": "spy_sent"},
        "reward": {"premium_theme": True},
        "is_tutorial": False,
    },
]


def ensure_default_quests(db: Session) -> List[models.Quest]:
    quests: List[models.Quest] = []
    for quest_def in DEFAULT_QUESTS:
        quest = db.query(models.Quest).filter(models.Quest.quest_id == quest_def["quest_id"]).first()
        if not quest:
            quest = models.Quest(**quest_def)
            db.add(quest)
            db.commit()
            db.refresh(quest)
        quests.append(quest)
    return quests


def _ensure_progress_entries(db: Session, user: models.User) -> List[models.QuestProgress]:
    quests = ensure_default_quests(db)
    progresses: List[models.QuestProgress] = []
    for quest in quests:
        progress = (
            db.query(models.QuestProgress)
            .filter(models.QuestProgress.quest_id == quest.id, models.QuestProgress.user_id == user.id)
            .first()
        )
        if not progress:
            progress = models.QuestProgress(user_id=user.id, quest_id=quest.id, status="pending", progress_data={})
            db.add(progress)
            db.commit()
            db.refresh(progress)
        progresses.append(progress)
    return progresses


def _mark_completed(progress: models.QuestProgress) -> None:
    progress.status = "completed"


def _maybe_complete_building(progress: models.QuestProgress, event_data: Dict[str, Any]) -> bool:
    req = progress.quest.requirements
    required_building = req.get("building_type")
    required_level = req.get("level", 1)
    if (
        progress.quest.requirements.get("type") == "building_finished"
        and event_data.get("building_type") == required_building
        and event_data.get("level", 0) >= required_level
    ):
        _mark_completed(progress)
        return True
    return False


def _maybe_complete_training(progress: models.QuestProgress, event_data: Dict[str, Any]) -> bool:
    if progress.quest.requirements.get("type") != "troops_trained":
        return False
    unit_type = progress.quest.requirements.get("unit_type")
    required_amount = progress.quest.requirements.get("amount", 0)
    if event_data.get("unit_type") != unit_type:
        return False
    current_amount = progress.progress_data.get("trained", 0)
    progress.progress_data["trained"] = current_amount + event_data.get("amount", 0)
    if progress.progress_data["trained"] >= required_amount:
        _mark_completed(progress)
        return True
    return False


def _maybe_complete_resources(progress: models.QuestProgress, event_data: Dict[str, Any]) -> bool:
    if progress.quest.requirements.get("type") != "resources_collected":
        return False
    required_amount = progress.quest.requirements.get("amount", 0)
    collected = progress.progress_data.get("collected", 0)
    collected += sum(event_data.get(resource, 0) for resource in ("wood", "clay", "iron"))
    progress.progress_data["collected"] = collected
    if collected >= required_amount:
        _mark_completed(progress)
        return True
    return False


def _maybe_complete_simple(progress: models.QuestProgress, event_type: str) -> bool:
    req_type = progress.quest.requirements.get("type")
    if req_type in {"alliance_joined", "attack_sent", "spy_sent"} and req_type == event_type:
        _mark_completed(progress)
        return True
    return False


def handle_event(db: Session, user: models.User, event_type: str, event_data: Dict[str, Any] | None = None) -> None:
    event_data = event_data or {}
    progresses = _ensure_progress_entries(db, user)
    for progress in progresses:
        if progress.status != "pending":
            continue
        changed = False
        if event_type == "building_finished":
            changed = _maybe_complete_building(progress, event_data)
        elif event_type == "troops_trained":
            changed = _maybe_complete_training(progress, event_data)
        elif event_type == "resources_collected":
            changed = _maybe_complete_resources(progress, event_data)
        else:
            changed = _maybe_complete_simple(progress, event_type)
        if changed:
            db.add(progress)
    db.commit()


def list_quests_for_user(db: Session, user: models.User) -> List[models.QuestProgress]:
    return _ensure_progress_entries(db, user)


def _apply_resource_reward(user: models.User, resources: Dict[str, Any]) -> None:
    if not user.cities:
        return
    city = user.cities[0]
    for resource, value in resources.items():
        if hasattr(city, resource):
            setattr(city, resource, getattr(city, resource) + value)


def _apply_rewards(progress: models.QuestProgress) -> Dict[str, Any]:
    reward = progress.quest.reward or {}
    user = progress.user
    granted: Dict[str, Any] = {}

    if resources := reward.get("resources"):
        _apply_resource_reward(user, resources)
        granted["resources"] = resources

    if rename_tokens := reward.get("rename_tokens"):
        user.rename_tokens = (user.rename_tokens or 0) + rename_tokens
        granted["rename_tokens"] = rename_tokens

    if reward.get("premium_theme"):
        user.premium_theme_unlocked = True
        granted["premium_theme"] = True

    return granted


def claim_reward(db: Session, user: models.User, quest_identifier: str) -> tuple[models.QuestProgress, Dict[str, Any]]:
    progress = (
        db.query(models.QuestProgress)
        .join(models.Quest, models.Quest.id == models.QuestProgress.quest_id)
        .filter(models.Quest.quest_id == quest_identifier, models.QuestProgress.user_id == user.id)
        .first()
    )
    if not progress:
        raise ValueError("Quest not found")
    if progress.status != "completed":
        raise ValueError("Quest not ready to claim")

    granted = _apply_rewards(progress)
    progress.status = "claimed"
    db.add(progress)
    db.add(user)
    db.commit()
    db.refresh(progress)
    return progress, granted


def serialize_progress(progress: models.QuestProgress) -> Dict[str, Any]:
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
    tutorial_progresses = [p for p in progresses if p.quest.is_tutorial]
    return bool(tutorial_progresses) and all(p.status == "claimed" for p in tutorial_progresses)
