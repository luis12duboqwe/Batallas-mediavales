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


def _calculate_building_points(db: Session, user_id: int, world_id: int) -> int:
    total_levels = (
        db.query(func.coalesce(func.sum(models.Building.level), 0))
        .join(models.City, models.Building.city_id == models.City.id)
        .filter(models.City.owner_id == user_id, models.City.world_id == world_id)
        .scalar()
    )
    return int(total_levels) * 5


def _calculate_troop_points(db: Session, user_id: int, world_id: int) -> int:
    troop_totals = (
        db.query(models.Troop.unit_type, func.coalesce(func.sum(models.Troop.quantity), 0))
        .join(models.City, models.Troop.city_id == models.City.id)
        .filter(models.City.owner_id == user_id, models.City.world_id == world_id)
        .group_by(models.Troop.unit_type)
        .all()
    )
    points = 0
    for unit_type, quantity in troop_totals:
        points += int(quantity) * TROOP_VALUES.get(unit_type, 1)
    return points


def calculate_player_points(db: Session, user: models.User, world_id: int) -> int:
    building_points = _calculate_building_points(db, user.id, world_id)
    troop_points = _calculate_troop_points(db, user.id, world_id)
    return building_points + troop_points


def _get_user_points_map(db: Session, users: List[models.User], world_id: int) -> Dict[int, int]:
    return {user.id: calculate_player_points(db, user, world_id) for user in users}


def calculate_alliance_points(db: Session, alliance: models.Alliance, world_id: int) -> int:
    users = [member.user for member in alliance.members]
    user_points = _get_user_points_map(db, users, world_id)
    return sum(user_points.values())


def get_player_ranking(db: Session, world_id: int) -> List[Dict[str, int | str | int]]:
    users = (
        db.query(models.User)
        .join(models.City, models.City.owner_id == models.User.id)
        .filter(models.City.world_id == world_id)
        .distinct()
        .all()
    )
    ranking = [
        {
            "user_id": user.id,
            "username": user.username,
            "points": calculate_player_points(db, user, world_id),
            "world_id": world_id,
        }
        for user in users
    ]
    ranking.sort(key=lambda entry: entry["points"], reverse=True)
    return ranking


def get_alliance_ranking(db: Session, world_id: int) -> List[Dict[str, int | str | int]]:
    alliances = db.query(models.Alliance).filter(models.Alliance.world_id == world_id).all()
    users = (
        db.query(models.User)
        .join(models.City, models.City.owner_id == models.User.id)
        .filter(models.City.world_id == world_id)
        .distinct()
        .all()
    )
    user_points = _get_user_points_map(db, users, world_id)

    ranking = []
    for alliance in alliances:
        points = sum(user_points.get(member.user_id, 0) for member in alliance.members)
        ranking.append(
            {
                "alliance_id": alliance.id,
                "name": alliance.name,
                "points": points,
                "world_id": world_id,
            }
        )

    ranking.sort(key=lambda entry: entry["points"], reverse=True)
    return ranking


def recalculate_player_and_alliance_scores(db: Session, user_id: int, world_id: int) -> None:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return

    calculate_player_points(db, user, world_id)
    for membership in user.alliances:
        calculate_alliance_points(db, membership.alliance, world_id)
