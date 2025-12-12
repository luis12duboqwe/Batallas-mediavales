from datetime import datetime
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import ranking as ranking_service


def _deactivate_existing_seasons(db: Session, world_id: str) -> None:
    existing = (
        db.query(models.Season)
        .filter(models.Season.world_id == world_id, models.Season.is_active.is_(True))
        .all()
    )
    for season in existing:
        season.is_active = False
        season.end_date = utc_now()


def start_new_season(db: Session, world_id: str, name: str) -> models.Season:
    _deactivate_existing_seasons(db, world_id)
    db.commit()

    season_identifier = f"{world_id}-{int(utc_now().timestamp())}"
    new_season = models.Season(
        season_id=season_identifier,
        world_id=world_id,
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
    ranking = ranking_service.get_player_ranking(db)
    results: List[models.SeasonResult] = []
    for index, entry in enumerate(ranking, start=1):
        alliance_member = (
            db.query(models.AllianceMember)
            .filter(models.AllianceMember.user_id == entry["user_id"])
            .first()
        )
        rewards = _assign_rewards(index)
        season_result = models.SeasonResult(
            season_id=season.id,
            user_id=entry["user_id"],
            alliance_id=alliance_member.alliance_id if alliance_member else None,
            rank=index,
            points=int(entry.get("points", 0)),
        )
        season_result.set_rewards(rewards)
        db.add(season_result)
        results.append(season_result)
    db.commit()
    for result in results:
        db.refresh(result)
    return results


def _reset_world_state(db: Session) -> None:
    db.query(models.Movement).delete(synchronize_session=False)
    db.query(models.BuildingQueue).delete(synchronize_session=False)
    db.query(models.TroopQueue).delete(synchronize_session=False)
    db.query(models.Troop).delete(synchronize_session=False)
    db.query(models.Building).delete(synchronize_session=False)
    db.query(models.Report).delete(synchronize_session=False)
    db.query(models.SpyReport).delete(synchronize_session=False)
    db.query(models.Message).delete(synchronize_session=False)
    db.query(models.Log).delete(synchronize_session=False)
    db.query(models.AllianceChatMessage).delete(synchronize_session=False)
    db.query(models.AllianceInvitation).delete(synchronize_session=False)
    db.query(models.AllianceMember).delete(synchronize_session=False)
    db.query(models.Alliance).delete(synchronize_session=False)
    db.query(models.City).delete(synchronize_session=False)
    db.commit()


def end_current_season(db: Session, world_id: str) -> List[models.SeasonResult]:
    season = (
        db.query(models.Season)
        .filter(models.Season.world_id == world_id, models.Season.is_active.is_(True))
        .first()
    )
    if not season:
        raise HTTPException(status_code=404, detail="No active season found for this world")

    season.end_date = utc_now()
    season.is_active = False
    results = _snapshot_rankings(db, season)
    _reset_world_state(db)
    db.commit()
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
