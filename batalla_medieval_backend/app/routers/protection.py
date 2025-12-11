from fastapi import APIRouter, Depends

from .. import models, schemas
from ..routers.auth import get_current_user
from ..services import protection

router = APIRouter(prefix="/protection", tags=["protection"])


@router.get("/status", response_model=schemas.ProtectionStatus)
def get_protection_status(current_user: models.User = Depends(get_current_user)):
    seconds_left = protection.get_protection_seconds_left(current_user)
    return schemas.ProtectionStatus(seconds_left=seconds_left)
