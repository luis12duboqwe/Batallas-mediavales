from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..services import icon_generator

router = APIRouter(prefix="/icons", tags=["icons"])


@router.get("/generate")
def generate_icon(
    icon_type: str = Query(..., alias="type"),
    subtype: str = Query(...),
    size: int = Query(128, ge=32, le=512),
):
    """Generate an SVG icon and return it as a file response."""
    try:
        icon_path = icon_generator.generate_icon(icon_type=icon_type, subtype=subtype, size=size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(str(icon_path), media_type="image/svg+xml", filename=icon_path.name)
