from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..services import pve, ranking, world_gen, world_membership
from .auth import get_current_user
from .responses import error_response
from .world_access import require_world_access

router = APIRouter(
    prefix="/map",
    tags=["map"],
    responses={404: {"description": "Not found"}},
)


def _alliance_name(user: models.User | None, world_id: int) -> str | None:
    if not user:
        return None
    for membership in user.alliances:
        alliance = membership.alliance
        if alliance and alliance.world_id == world_id:
            return alliance.name
    return None


@router.get("/tiles", response_model=schemas.MapResponse)
def get_map_tiles(
    world_id: int,
    x: int,
    y: int,
    radius: int = Query(10, ge=0, le=20),
    db: Session = Depends(get_db),
    _membership: models.PlayerWorld = Depends(require_world_access),
):
    """Return only coordinates that actually exist inside the selected world."""

    world = _membership.world
    if world is None:
        world = db.query(models.World).filter(models.World.id == world_id).one()
    map_size = int(world.map_size)
    rules_version = pve.world_rules_version(world)

    # A viewport may be centred on the first/last row of the map. Clamp the
    # requested square so clients never receive negative or >= map_size tiles
    # that server-authoritative expansion would correctly reject.
    min_x = max(0, x - radius)
    max_x = min(map_size - 1, x + radius)
    min_y = max(0, y - radius)
    max_y = min(map_size - 1, y + radius)

    if min_x > max_x or min_y > max_y:
        return schemas.MapResponse(tiles=[])

    owner_alliance = (
        selectinload(models.City.owner)
        .selectinload(models.User.alliances)
        .selectinload(models.AllianceMember.alliance)
    )

    # Fetch settlements in range with everything needed for labels and score.
    cities = (
        db.query(models.City)
        .options(
            owner_alliance,
            selectinload(models.City.world),
            selectinload(models.City.buildings),
            selectinload(models.City.troops),
        )
        .filter(
            models.City.world_id == world_id,
            models.City.x >= min_x,
            models.City.x <= max_x,
            models.City.y >= min_y,
            models.City.y <= max_y,
        )
        .all()
    )

    city_map = {(c.x, c.y): c for c in cities}

    oases = (
        db.query(models.Oasis)
        .options(
            selectinload(models.Oasis.world),
            selectinload(models.Oasis.owner_city)
            .selectinload(models.City.owner)
            .selectinload(models.User.alliances)
            .selectinload(models.AllianceMember.alliance)
        )
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
            settlement_type = city.settlement_type if city else None
            points = ranking.calculate_city_points(city) if city else 0
            owner_id = None
            owner_name = None
            alliance_name = None

            oasis_id = None
            resource_type = None
            bonus_percent = None
            is_conquered = False
            pve_tier = None
            pve_rules_version = None

            if city:
                if city.owner:
                    owner_id = city.owner.id
                    owner_name = city.owner.username
                    alliance_name = _alliance_name(city.owner, world_id)
                else:
                    owner_name = "Bárbaros"
                    pve_tier = pve.barbarian_tier(city)
                    pve_rules_version = rules_version
            elif oasis:
                oasis_id = oasis.id
                resource_type = oasis.resource_type
                bonus_percent = oasis.bonus_percent
                pve_tier = pve.oasis_tier(oasis)
                pve_rules_version = rules_version
                if oasis.owner_city:
                    is_conquered = True
                    owner_id = oasis.owner_city.owner_id
                    if oasis.owner_city.owner:
                        owner_name = oasis.owner_city.owner.username
                        alliance_name = _alliance_name(oasis.owner_city.owner, world_id)
                else:
                    owner_name = "Naturaleza"

            tiles.append(
                schemas.MapTile(
                    x=curr_x,
                    y=curr_y,
                    type=tile_type,
                    city_id=city_id,
                    city_name=city_name,
                    settlement_type=settlement_type,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    alliance_name=alliance_name,
                    points=points,
                    oasis_id=oasis_id,
                    resource_type=resource_type,
                    bonus_percent=bonus_percent,
                    is_conquered=is_conquered,
                    pve_tier=pve_tier,
                    pve_rules_version=pve_rules_version,
                )
            )

    return schemas.MapResponse(tiles=tiles)


@router.get("/oasis/{oasis_id}", response_model=schemas.OasisRead)
def get_oasis(
    oasis_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    oasis = (
        db.query(models.Oasis)
        .options(selectinload(models.Oasis.world))
        .filter(models.Oasis.id == oasis_id)
        .first()
    )
    if not oasis:
        raise error_response(404, "oasis_not_found", "Oasis not found")
    try:
        world_membership.require_world_membership(
            db,
            user_id=current_user.id,
            world_id=oasis.world_id,
        )
    except world_membership.WorldAccessDeniedError as exc:
        raise error_response(
            403,
            "world_access_denied",
            "You have not joined this world",
            {"world_id": oasis.world_id},
        ) from exc

    return schemas.OasisRead.model_validate(oasis).model_copy(
        update={
            "pve_tier": pve.oasis_tier(oasis),
            "pve_rules_version": pve.world_rules_version(oasis.world),
        }
    )
