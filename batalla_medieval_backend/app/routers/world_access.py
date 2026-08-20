"""Shared FastAPI dependency for world-scoped player access."""

from fastapi import Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..services import world_membership
from .auth import get_current_user
from .responses import error_response


def require_world_access(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.PlayerWorld:
    """Require durable membership before exposing arbitrary world-scoped data."""

    try:
        return world_membership.require_world_membership(
            db,
            user_id=current_user.id,
            world_id=world_id,
        )
    except world_membership.WorldAccessDeniedError as exc:
        raise error_response(
            403,
            "world_access_denied",
            "You have not joined this world",
            {"world_id": world_id},
        ) from exc
