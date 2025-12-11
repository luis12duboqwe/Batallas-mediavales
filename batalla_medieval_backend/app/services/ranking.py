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


def _calculate_building_points(db: Session, user_id: int) -> int:
    total_levels = (
        db.query(func.coalesce(func.sum(models.Building.level), 0))
        .join(models.City, models.Building.city_id == models.City.id)
        .filter(models.City.owner_id == user_id)
        .scalar()
    )
    return int(total_levels) * 5


def _calculate_troop_points(db: Session, user_id: int) -> int:
    troop_totals = (
        db.query(models.Troop.unit_type, func.coalesce(func.sum(models.Troop.quantity), 0))
        .join(models.City, models.Troop.city_id == models.City.id)
        .filter(models.City.owner_id == user_id)
        .group_by(models.Troop.unit_type)
        .all()
    )
    points = 0
    for unit_type, quantity in troop_totals:
        points += int(quantity) * TROOP_VALUES.get(unit_type, 1)
    return points


def calculate_player_points(db: Session, user: models.User) -> int:
    building_points = _calculate_building_points(db, user.id)
    troop_points = _calculate_troop_points(db, user.id)
    return building_points + troop_points


def _get_user_points_map(db: Session, users: List[models.User]) -> Dict[int, int]:
    return {user.id: calculate_player_points(db, user) for user in users}


def calculate_alliance_points(db: Session, alliance: models.Alliance) -> int:
    users = [member.user for member in alliance.members]
    user_points = _get_user_points_map(db, users)
    return sum(user_points.values())


def get_player_ranking(db: Session) -> List[Dict[str, int | str]]:
    users = db.query(models.User).all()
    ranking = [
        {"user_id": user.id, "username": user.username, "points": calculate_player_points(db, user)}
        for user in users
    ]
    ranking.sort(key=lambda entry: entry["points"], reverse=True)
    return ranking


def get_alliance_ranking(db: Session) -> List[Dict[str, int | str]]:
    alliances = db.query(models.Alliance).all()
    users = db.query(models.User).all()
    user_points = _get_user_points_map(db, users)

    ranking = []
    for alliance in alliances:
        points = sum(user_points.get(member.user_id, 0) for member in alliance.members)
        ranking.append({"alliance_id": alliance.id, "name": alliance.name, "points": points})

    ranking.sort(key=lambda entry: entry["points"], reverse=True)
    return ranking


def recalculate_player_and_alliance_scores(db: Session, user_id: int) -> None:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return

    calculate_player_points(db, user)
    for membership in user.alliances:
        calculate_alliance_points(db, membership.alliance)
