"""BM-0073 administrative role and capability contract."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException

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
    },
    "admin": {
        "audit.read",
        "support.manage",
        "account.freeze",
        "content.moderate",
        "game.correct",
        "world.manage",
        "admin.manage",
        "admin.roles",
        "admin.revert",
    },
}


def effective_admin_role(user: models.User) -> str | None:
    if not bool(getattr(user, "is_admin", False)):
        return None
    role = getattr(user, "admin_role", None)
    if role is None:
        # Compatibility for pre-BM-0073 administrators that have not yet been
        # assigned an explicit role. Unknown non-null values must fail closed.
        return "admin"
    return role if role in ADMIN_ROLES else None


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


def require_reason(
    x_admin_reason: str = Header(..., alias="X-Admin-Reason", min_length=1, max_length=1000),
) -> str:
    """Require a non-blank reason for legacy admin endpoints without body room.

    New BM-0073 endpoints carry ``reason`` in their typed request body. Older
    administrative routes keep their existing body contracts and use this
    header so the security invariant is enforced without overloading unrelated
    domain schemas.
    """

    normalized = x_admin_reason.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Administrative reason is required")
    return normalized
