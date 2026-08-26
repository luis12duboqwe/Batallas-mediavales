from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now

RELATION_TYPES = frozenset({"nap", "ally", "war"})
PENDING_TYPES = frozenset({"pending_nap", "pending_ally"})
ACTIVE_TYPES = frozenset({"nap", "ally", "war"})


def _get_alliance(db: Session, alliance_id: int) -> models.Alliance:
    alliance = db.query(models.Alliance).filter(models.Alliance.id == alliance_id).first()
    if not alliance:
        raise HTTPException(status_code=404, detail="Alliance not found")
    return alliance


def _lock_same_world_pair(
    db: Session,
    alliance_id: int,
    target_id: int,
) -> tuple[models.Alliance, models.Alliance]:
    """Lock both alliances in stable ID order to serialize unordered pair changes."""

    if alliance_id == target_id:
        raise HTTPException(status_code=400, detail="Cannot have relation with self")

    ordered_ids = sorted((int(alliance_id), int(target_id)))
    locked = (
        db.query(models.Alliance)
        .filter(models.Alliance.id.in_(ordered_ids))
        .order_by(models.Alliance.id.asc())
        .with_for_update()
        .all()
    )
    if len(locked) != 2:
        raise HTTPException(status_code=404, detail="Alliance not found")
    by_id = {alliance.id: alliance for alliance in locked}
    alliance = by_id.get(alliance_id)
    target = by_id.get(target_id)
    if alliance is None or target is None:
        raise HTTPException(status_code=404, detail="Alliance not found")
    if alliance.world_id != target.world_id:
        raise HTTPException(status_code=400, detail="Diplomacy cannot cross worlds")
    return alliance, target


def _require_same_world_pair(
    db: Session,
    alliance_id: int,
    target_id: int,
) -> tuple[models.Alliance, models.Alliance]:
    alliance = _get_alliance(db, alliance_id)
    target = _get_alliance(db, target_id)
    if alliance.world_id != target.world_id:
        raise HTTPException(status_code=400, detail="Diplomacy cannot cross worlds")
    return alliance, target


def _find_pair(db: Session, alliance_id: int, target_id: int):
    return (
        db.query(models.Diplomacy)
        .filter(
            or_(
                (
                    (models.Diplomacy.alliance_a_id == alliance_id)
                    & (models.Diplomacy.alliance_b_id == target_id)
                ),
                (
                    (models.Diplomacy.alliance_a_id == target_id)
                    & (models.Diplomacy.alliance_b_id == alliance_id)
                ),
            )
        )
        .first()
    )


def get_relations(db: Session, alliance_id: int):
    alliance = _get_alliance(db, alliance_id)
    relations = (
        db.query(models.Diplomacy)
        .filter(
            or_(
                models.Diplomacy.alliance_a_id == alliance_id,
                models.Diplomacy.alliance_b_id == alliance_id,
            )
        )
        .all()
    )
    # Ignore any legacy/corrupt cross-world relation instead of exposing it.
    return [
        relation
        for relation in relations
        if relation.alliance_a.world_id == alliance.world_id
        and relation.alliance_b.world_id == alliance.world_id
    ]


def request_relation(
    db: Session,
    alliance_id: int,
    target_id: int,
    relation_type: str,
):
    if relation_type not in RELATION_TYPES:
        raise HTTPException(status_code=400, detail="Invalid diplomacy status")

    try:
        _lock_same_world_pair(db, alliance_id, target_id)
        existing = _find_pair(db, alliance_id, target_id)
        if existing:
            if relation_type == "war":
                # War is unilateral and declaring it again is idempotent.
                existing.status = "war"
                existing.updated_at = utc_now()
                db.commit()
                db.refresh(existing)
                return existing

            expected_pending = f"pending_{relation_type}"
            if (
                existing.status == expected_pending
                and existing.alliance_a_id == alliance_id
                and existing.alliance_b_id == target_id
            ):
                # Network retry by the original requester: replay the same row.
                db.commit()
                db.refresh(existing)
                return existing
            if existing.status == relation_type:
                raise HTTPException(status_code=400, detail="Relation already active")
            raise HTTPException(
                status_code=400,
                detail="Relation already exists. Cancel it first.",
            )

        status_value = "war" if relation_type == "war" else f"pending_{relation_type}"
        relation = models.Diplomacy(
            # Direction is preserved so alliance_b is the party allowed to accept.
            alliance_a_id=alliance_id,
            alliance_b_id=target_id,
            status=status_value,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(relation)
        db.commit()
        db.refresh(relation)
        return relation
    except Exception:
        db.rollback()
        raise


def accept_relation(db: Session, alliance_id: int, diplomacy_id: int):
    try:
        relation = (
            db.query(models.Diplomacy)
            .filter(models.Diplomacy.id == diplomacy_id)
            .with_for_update()
            .one_or_none()
        )
        if not relation:
            raise HTTPException(status_code=404, detail="Relation not found")
        if relation.alliance_b_id != alliance_id:
            raise HTTPException(status_code=403, detail="Only the target alliance can accept")

        _lock_same_world_pair(db, relation.alliance_a_id, relation.alliance_b_id)
        if relation.status in {"nap", "ally"}:
            # Safe replay by the same target alliance after a successful response.
            db.commit()
            db.refresh(relation)
            return relation
        if relation.status not in PENDING_TYPES:
            raise HTTPException(status_code=400, detail="Not a pending relation")

        relation.status = relation.status.replace("pending_", "", 1)
        relation.updated_at = utc_now()
        db.commit()
        db.refresh(relation)
        return relation
    except Exception:
        db.rollback()
        raise


def cancel_relation(db: Session, alliance_id: int, diplomacy_id: int):
    try:
        relation = (
            db.query(models.Diplomacy)
            .filter(models.Diplomacy.id == diplomacy_id)
            .with_for_update()
            .one_or_none()
        )
        if not relation:
            raise HTTPException(status_code=404, detail="Relation not found")
        if alliance_id not in {relation.alliance_a_id, relation.alliance_b_id}:
            raise HTTPException(status_code=403, detail="Not involved in this relation")

        _lock_same_world_pair(db, relation.alliance_a_id, relation.alliance_b_id)
        db.delete(relation)
        db.commit()
        return {"detail": "Relation cancelled"}
    except Exception:
        db.rollback()
        raise
