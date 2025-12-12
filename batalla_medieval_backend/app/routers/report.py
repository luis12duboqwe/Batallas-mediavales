from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user

router = APIRouter(tags=["reports"])


@router.get("/", response_model=list[schemas.ReportRead])
def list_reports(
    world_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    reports = (
        db.query(models.Report)
        .join(models.City, models.Report.city_id == models.City.id)
        .filter(models.City.owner_id == current_user.id, models.Report.world_id == world_id)
        .all()
    )
    return reports
