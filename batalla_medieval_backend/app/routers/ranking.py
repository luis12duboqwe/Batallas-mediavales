from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..services import ranking as ranking_service

router = APIRouter(prefix="/ranking", tags=["ranking"])


@router.get("/players", response_model=list[schemas.PlayerRanking])
def list_player_ranking(world_id: int, db: Session = Depends(get_db)):
    return ranking_service.get_player_ranking(db, world_id)


@router.get("/alliances", response_model=list[schemas.AllianceRanking])
def list_alliance_ranking(world_id: int, db: Session = Depends(get_db)):
    return ranking_service.get_alliance_ranking(db, world_id)
