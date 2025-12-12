from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..services import world_gen
from .responses import error_response

router = APIRouter(
    prefix="/map",
    tags=["map"],
    responses={404: {"description": "Not found"}},
)

@router.get("/tiles", response_model=schemas.MapResponse)
def get_map_tiles(
    world_id: int,
    x: int,
    y: int,
    radius: int = Query(10, le=20), # Limit radius to avoid huge payloads
    db: Session = Depends(get_db),
):
    min_x = x - radius
    max_x = x + radius
    min_y = y - radius
    max_y = y + radius

    # Fetch cities in range
    cities = (
        db.query(models.City)
        .options(selectinload(models.City.owner).selectinload(models.User.alliance))
        .filter(
            models.City.world_id == world_id,
            models.City.x >= min_x,
            models.City.x <= max_x,
            models.City.y >= min_y,
            models.City.y <= max_y,
        )
        .all()
    )

    # Map cities by coordinate for O(1) lookup
    city_map = {(c.x, c.y): c for c in cities}

    # Fetch oases in range
    oases = (
        db.query(models.Oasis)
        .options(selectinload(models.Oasis.owner_city).selectinload(models.City.owner).selectinload(models.User.alliance))
        .filter(
            models.Oasis.world_id == world_id,
            models.Oasis.x >= min_x,
            models.Oasis.x <= max_x,
            models.Oasis.y >= min_y,
            models.Oasis.y <= max_y,
        )
        .all()
    )
    oasis_map = {(o.x, o.y): o for o in oases}

    tiles: list[schemas.MapTile] = []
    for curr_x in range(min_x, max_x + 1):
        for curr_y in range(min_y, max_y + 1):
            city = city_map.get((curr_x, curr_y))
            oasis = oasis_map.get((curr_x, curr_y))
            
            tile_type = world_gen.get_tile_type(curr_x, curr_y)
            
            city_id = city.id if city else None
            city_name = city.name if city else None
            points = city.points if city else 0
            owner_id = None
            owner_name = None
            alliance_name = None
            
            oasis_id = None
            resource_type = None
            bonus_percent = None
            is_conquered = False

            if city:
                if city.owner:
                    owner_id = city.owner.id
                    owner_name = city.owner.username
                    if city.owner.alliance:
                        alliance_name = city.owner.alliance.name
                else:
                    owner_name = "Bárbaros"
            elif oasis:
                oasis_id = oasis.id
                resource_type = oasis.resource_type
                bonus_percent = oasis.bonus_percent
                if oasis.owner_city:
                    is_conquered = True
                    owner_id = oasis.owner_city.owner_id
                    owner_name = oasis.owner_city.owner.username
                    if oasis.owner_city.owner.alliance:
                        alliance_name = oasis.owner_city.owner.alliance.name
                else:
                    owner_name = "Naturaleza"

            tiles.append(schemas.MapTile(
                x=curr_x,
                y=curr_y,
                type=tile_type,
                city_id=city_id,
                city_name=city_name,
                owner_id=owner_id,
                owner_name=owner_name,
                alliance_name=alliance_name,
                points=points,
                oasis_id=oasis_id,
                resource_type=resource_type,
                bonus_percent=bonus_percent,
                is_conquered=is_conquered
            ))

    return schemas.MapResponse(tiles=tiles)


@router.get("/oasis/{oasis_id}", response_model=schemas.OasisRead)
def get_oasis(
    oasis_id: int,
    db: Session = Depends(get_db),
):
    oasis = db.query(models.Oasis).filter(models.Oasis.id == oasis_id).first()
    if not oasis:
        raise error_response(404, "oasis_not_found", "Oasis not found")
    return oasis
