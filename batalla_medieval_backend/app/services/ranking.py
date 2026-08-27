from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models

TROOP_VALUES: Dict[str, int] = {
    "basic_infantry": 2,
    "heavy_infantry": 3,
    "archer": 3,
    "fast_cavalry": 4,
    "heavy_cavalry": 5,
    "spy": 1,
    "ram": 8,
    "catapult": 10,
}


def calculate_city_points(city: models.City) -> int:
    """Return the same score components used by player ranking, scoped to one city."""

    building_points = sum(int(building.level) for building in city.buildings) * 5
    troop_points = sum(
        int(troop.quantity) * TROOP_VALUES.get(troop.unit_type, 1)
        for troop in city.troops
    )
    return building_points + troop_points


def _building_points_map(db: Session, world_id: int) -> Dict[int, int]:
    rows = (
        db.query(
            models.City.owner_id,
            func.coalesce(func.sum(models.Building.level), 0),
        )
        .join(models.Building, models.Building.city_id == models.City.id)
        .filter(
            models.City.world_id == world_id,
            models.City.owner_id.isnot(None),
        )
        .group_by(models.City.owner_id)
        .all()
    )
    return {int(user_id): int(total_levels) * 5 for user_id, total_levels in rows}


def _troop_points_map(db: Session, world_id: int) -> Dict[int, int]:
    rows = (
        db.query(
            models.City.owner_id,
            models.Troop.unit_type,
            func.coalesce(func.sum(models.Troop.quantity), 0),
        )
        .join(models.Troop, models.Troop.city_id == models.City.id)
        .filter(
            models.City.world_id == world_id,
            models.City.owner_id.isnot(None),
        )
        .group_by(models.City.owner_id, models.Troop.unit_type)
        .all()
    )
    points: Dict[int, int] = {}
    for user_id, unit_type, quantity in rows:
        uid = int(user_id)
        points[uid] = points.get(uid, 0) + int(quantity) * TROOP_VALUES.get(unit_type, 1)
    return points


def _world_points_map(db: Session, world_id: int) -> Dict[int, int]:
    building_points = _building_points_map(db, world_id)
    troop_points = _troop_points_map(db, world_id)
    user_ids = set(building_points) | set(troop_points)
    return {
        user_id: building_points.get(user_id, 0) + troop_points.get(user_id, 0)
        for user_id in user_ids
    }


def calculate_player_points(db: Session, user: models.User, world_id: int) -> int:
    return _world_points_map(db, world_id).get(user.id, 0)


def _get_user_points_map(db: Session, users: List[models.User], world_id: int) -> Dict[int, int]:
    points = _world_points_map(db, world_id)
    return {user.id: points.get(user.id, 0) for user in users}


def calculate_alliance_points(db: Session, alliance: models.Alliance, world_id: int) -> int:
    if alliance.world_id != world_id:
        return 0
    user_points = _world_points_map(db, world_id)
    return sum(user_points.get(member.user_id, 0) for member in alliance.members)


def get_player_ranking(db: Session, world_id: int) -> List[Dict[str, int | str]]:
    users = (
        db.query(models.User)
        .join(models.City, models.City.owner_id == models.User.id)
        .filter(models.City.world_id == world_id)
        .distinct()
        .all()
    )
    points = _world_points_map(db, world_id)
    ranking = [
        {
            "user_id": user.id,
            "username": user.username,
            "points": points.get(user.id, 0),
            "world_id": world_id,
        }
        for user in users
    ]
    ranking.sort(
        key=lambda entry: (
            -int(entry["points"]),
            str(entry["username"]).casefold(),
            int(entry["user_id"]),
        )
    )
    for position, entry in enumerate(ranking, start=1):
        entry["rank"] = position
    return ranking


def get_alliance_ranking(db: Session, world_id: int) -> List[Dict[str, int | str]]:
    alliances = db.query(models.Alliance).filter(models.Alliance.world_id == world_id).all()
    user_points = _world_points_map(db, world_id)

    ranking = []
    for alliance in alliances:
        ranking.append(
            {
                "alliance_id": alliance.id,
                "name": alliance.name,
                "points": sum(user_points.get(member.user_id, 0) for member in alliance.members),
                "world_id": world_id,
            }
        )

    ranking.sort(
        key=lambda entry: (
            -int(entry["points"]),
            str(entry["name"]).casefold(),
            int(entry["alliance_id"]),
        )
    )
    for position, entry in enumerate(ranking, start=1):
        entry["rank"] = position
    return ranking


def recalculate_player_and_alliance_scores(db: Session, user_id: int, world_id: int) -> None:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return

    calculate_player_points(db, user, world_id)
    for membership in user.alliances:
        if membership.alliance.world_id == world_id:
            calculate_alliance_points(db, membership.alliance, world_id)


def search_players(db: Session, world_id: int, query: str) -> List[models.User]:
    users = (
        db.query(models.User)
        .join(models.City, models.City.owner_id == models.User.id)
        .filter(
            models.City.world_id == world_id,
            models.User.username.ilike(f"%{query}%"),
        )
        .distinct()
        .limit(20)
        .all()
    )
    return users
