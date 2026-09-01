"""BM-0073 administrative role and capability contract."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from .. import models
from ..routers.auth import get_current_user

ADMIN_ROLES = {"support", "moderator", "operator", "admin"}

ROLE_CAPABILITIES = {
    "support": {
        "audit.read",
        "support.manage",
        "account.freeze",
    },
    "moderator": {
        "audit.read",
        "support.manage",
        "account.freeze",
        "content.moderate",
    },
    "operator": {
        "audit.read",
        "support.manage",
        "account.freeze",
        "content.moderate",
        "game.correct",
        "world.manage",
    },
    "admin": {
        "audit.read",
        "support.manage",
        "account.freeze",
        "content.moderate",
        "game.correct",
        "world.manage",
        "admin.roles",
        "admin.revert",
    },
}


def effective_admin_role(user: models.User) -> str | None:
    if not bool(getattr(user, "is_admin", False)):
        return None
    role = getattr(user, "admin_role", None)
    return role if role in ADMIN_ROLES else "admin"


def has_capability(user: models.User, capability: str) -> bool:
    role = effective_admin_role(user)
    return bool(role and capability in ROLE_CAPABILITIES[role])


def require_capability(capability: str):
    def dependency(
        current_user: models.User = Depends(get_current_user),
    ) -> models.User:
        if not has_capability(current_user, capability):
            raise HTTPException(
                status_code=403,
                detail=f"Administrative capability required: {capability}",
            )
        return current_user

    return dependency
