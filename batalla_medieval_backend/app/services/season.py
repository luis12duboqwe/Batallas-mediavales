from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import ranking as ranking_service


def _deactivate_existing_seasons(db: Session, world_id: str) -> None:
    existing = (
        db.query(models.Season)
        .filter(models.Season.world_id == str(world_id), models.Season.is_active.is_(True))
        .all()
    )
    for season in existing:
        season.is_active = False
        season.end_date = utc_now()


def start_new_season(db: Session, world_id: str, name: str) -> models.Season:
    normalized_world_id = str(world_id)
    _deactivate_existing_seasons(db, normalized_world_id)
    db.flush()

    season_identifier = f"{normalized_world_id}-{int(utc_now().timestamp())}"
    new_season = models.Season(
        season_id=season_identifier,
        world_id=normalized_world_id,
        name=name,
        start_date=utc_now(),
        is_active=True,
    )
    db.add(new_season)
    db.commit()
    db.refresh(new_season)
    return new_season


def _assign_rewards(rank: int) -> List[str]:
    if rank == 1:
        return ["legendary_banner", "golden_theme", "dragon_emblem"]
    if rank <= 3:
        return ["royal_banner", "crimson_theme"]
    if rank <= 10:
        return ["veteran_standard", "silver_theme"]
    if rank <= 50:
        return ["season_participant", "bronze_theme"]
    return ["season_participant"]


def _snapshot_rankings(db: Session, season: models.Season) -> List[models.SeasonResult]:
    """Snapshot only the season's world and never infer alliance data cross-world."""

    try:
        world_id = int(season.world_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="Season world id is invalid") from exc

    ranking = ranking_service.get_player_ranking(db, world_id)
    results: List[models.SeasonResult] = []
    for index, entry in enumerate(ranking, start=1):
        alliance_member = (
            db.query(models.AllianceMember)
            .join(models.Alliance, models.Alliance.id == models.AllianceMember.alliance_id)
            .filter(
                models.AllianceMember.user_id == entry["user_id"],
                models.Alliance.world_id == world_id,
            )
            .first()
        )
        season_result = models.SeasonResult(
            season_id=season.id,
            user_id=entry["user_id"],
            alliance_id=alliance_member.alliance_id if alliance_member else None,
            rank=index,
            points=int(entry.get("points", 0)),
        )
        season_result.set_rewards(_assign_rewards(index))
        db.add(season_result)
        results.append(season_result)

    db.flush()
    return results


def end_current_season(db: Session, world_id: str) -> List[models.SeasonResult]:
    """Close one season without deleting live world state.

    The legacy implementation globally deleted cities, alliances, troops,
    queues, messages and audit logs. Season closure is now a historical
    snapshot operation only; any future world reset must be an explicit,
    world-scoped lifecycle operation with its own reviewed retention policy.
    """

    normalized_world_id = str(world_id)
    season = (
        db.query(models.Season)
        .filter(
            models.Season.world_id == normalized_world_id,
            models.Season.is_active.is_(True),
        )
        .with_for_update()
        .one_or_none()
    )
    if not season:
        raise HTTPException(status_code=404, detail="No active season found for this world")

    season.end_date = utc_now()
    season.is_active = False
    results = _snapshot_rankings(db, season)
    db.commit()
    for result in results:
        db.refresh(result)
    return results


def get_season_info(db: Session) -> dict:
    active_season = db.query(models.Season).filter(models.Season.is_active.is_(True)).first()
    latest_results: List[models.SeasonResult] = []
    if active_season:
        latest_results = (
            db.query(models.SeasonResult)
            .filter(models.SeasonResult.season_id == active_season.id)
            .order_by(models.SeasonResult.rank.asc())
            .all()
        )
    else:
        last_season = db.query(models.Season).order_by(models.Season.end_date.desc().nullslast()).first()
        if last_season:
            latest_results = (
                db.query(models.SeasonResult)
                .filter(models.SeasonResult.season_id == last_season.id)
                .order_by(models.SeasonResult.rank.asc())
                .all()
            )
            active_season = last_season

    return {
        "active_season": active_season,
        "latest_results": latest_results,
    }
