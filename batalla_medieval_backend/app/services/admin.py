from sqlalchemy.orm import Session

from .. import models, schemas


def create_alliance(db: Session, payload: schemas.AllianceCreate, leader: models.User) -> models.Alliance:
    alliance = models.Alliance(
        name=payload.name,
        description=payload.description,
        diplomacy="neutral",
        leader_id=leader.id,
    )
    db.add(alliance)
    db.commit()
    db.refresh(alliance)
    member = models.AllianceMember(alliance_id=alliance.id, user_id=leader.id, rank=schemas.RANK_LEADER)
    db.add(member)
    db.commit()
    return alliance
