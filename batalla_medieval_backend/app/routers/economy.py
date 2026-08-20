from fastapi import APIRouter

from ..services import balance

router = APIRouter(prefix="/economy", tags=["economy"])


@router.get("/balance_preview")
def balance_preview():
    """Return the exact versioned rules consumed by live gameplay services."""

    return balance.snapshot()
