from typing import Dict

from sqlalchemy.orm import Session

from .. import models

FEATURE_COSTS: Dict[str, int] = {
    "second_build_queue": 350,
    "second_troop_queue": 350,
    "rename_city_unlocked": 100,
    "rename_player_unlocked": 150,
    "extra_themes": 75,
    "profile_banner": 75,
    "instant_building_cancel": 120,
    "increased_message_storage": 80,
    "map_bookmarks": 60,
}

BASE_MESSAGE_LIMIT = 50
PREMIUM_MESSAGE_LIMIT = 200


def get_or_create_status(db: Session, user: models.User) -> models.PremiumStatus:
    status = (
        db.query(models.PremiumStatus)
        .filter(models.PremiumStatus.user_id == user.id)
        .first()
    )
    if not status:
        status = models.PremiumStatus(user_id=user.id)
        db.add(status)
        db.commit()
        db.refresh(status)
    return status


def buy_feature(db: Session, user: models.User, feature: str) -> models.PremiumStatus:
    if feature not in FEATURE_COSTS:
        raise ValueError("Unknown premium feature")

    status = get_or_create_status(db, user)
    if getattr(status, feature, False):
        raise ValueError("Feature already purchased")

    cost = FEATURE_COSTS[feature]
    if status.rubies_balance < cost:
        raise ValueError("Not enough rubies")

    status.rubies_balance -= cost
    setattr(status, feature, True)
    db.commit()
    db.refresh(status)
    return status


def grant_rubies(db: Session, user: models.User, amount: int) -> models.PremiumStatus:
    if amount <= 0:
        raise ValueError("Amount must be positive")
    status = get_or_create_status(db, user)
    status.rubies_balance += amount
    db.commit()
    db.refresh(status)
    return status


def get_build_queue_limit(status: models.PremiumStatus) -> int:
    return 2 if status.second_build_queue else 1


def get_troop_queue_limit(status: models.PremiumStatus) -> int:
    return 2 if status.second_troop_queue else 1


def get_message_limit(status: models.PremiumStatus) -> int:
    if status and status.increased_message_storage:
        return PREMIUM_MESSAGE_LIMIT
    return BASE_MESSAGE_LIMIT


def use_premium_action(
    db: Session,
    user: models.User,
    action: str,
    *,
    city_id: int | None = None,
    queue_id: int | None = None,
    new_value: str | None = None,
    bookmark: dict | None = None,
) -> models.PremiumStatus | models.City | models.MapBookmark | models.User:
    status = get_or_create_status(db, user)

    if action == "rename_city":
        if not status.rename_city_unlocked:
            raise ValueError("Rename city is not unlocked")
        if not city_id or not new_value:
            raise ValueError("City and new name are required")
        city = (
            db.query(models.City)
            .filter(models.City.id == city_id, models.City.owner_id == user.id)
            .first()
        )
        if not city:
            raise ValueError("City not found")
        city.name = new_value
        db.commit()
        db.refresh(city)
        return city

    if action == "rename_player":
        if not status.rename_player_unlocked:
            raise ValueError("Rename player is not unlocked")
        if not new_value:
            raise ValueError("New username is required")
        existing = db.query(models.User).filter(models.User.username == new_value).first()
        if existing and existing.id != user.id:
            raise ValueError("Username already taken")
        user.username = new_value
        db.commit()
        db.refresh(user)
        return user

    if action == "cancel_building_queue":
        if not status.instant_building_cancel:
            raise ValueError("Instant cancellation not unlocked")
        if not queue_id:
            raise ValueError("Queue id is required")
        queue_entry = (
            db.query(models.BuildingQueue)
            .join(models.City, models.BuildingQueue.city_id == models.City.id)
            .filter(models.BuildingQueue.id == queue_id, models.City.owner_id == user.id)
            .first()
        )
        if not queue_entry:
            raise ValueError("Queue entry not found")
        db.delete(queue_entry)
        db.commit()
        return status

    if action == "set_theme":
        if not status.extra_themes:
            raise ValueError("Themes not unlocked")
        status.selected_theme = new_value
        db.commit()
        db.refresh(status)
        return status

    if action == "set_banner":
        if not status.profile_banner:
            raise ValueError("Banners not unlocked")
        status.selected_banner = new_value
        db.commit()
        db.refresh(status)
        return status

    if action == "add_bookmark":
        if not status.map_bookmarks:
            raise ValueError("Bookmarks not unlocked")
        if not bookmark:
            raise ValueError("Bookmark payload required")
        bookmark_entry = models.MapBookmark(
            user_id=user.id,
            name=bookmark["name"],
            x=bookmark["x"],
            y=bookmark["y"],
        )
        db.add(bookmark_entry)
        db.commit()
        db.refresh(bookmark_entry)
        return bookmark_entry

    raise ValueError("Unsupported premium action")
