from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import economy, event as event_service, ranking as ranking_service, world_gen

RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60
_request_logs: Dict[str, Deque[float]] = defaultdict(deque)


def _mask_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    if len(name) <= 2:
        return "*" * len(name)
    return f"{name[0]}{'*' * (len(name) - 2)}{name[-1]}"


def rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "anonymous"
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    log = _request_logs[client_ip]

    while log and log[0] < window_start:
        log.popleft()

    if len(log) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Max 60 requests per minute.")

    log.append(now)


class PublicCityMapEntry(BaseModel):
    city_id: int
    x: int
    y: int
    owner: Optional[str]
    alliance: Optional[str]
    points: int
    tile_type: str


class MapTile(BaseModel):
    x: int
    y: int
    type: str
    city: Optional[PublicCityMapEntry] = None


router = APIRouter(tags=["public"], dependencies=[Depends(rate_limit)])


@router.get("/map", response_model=List[MapTile])
def get_map_viewport(
    world_id: int,
    x: int,
    y: int,
    radius: int = 10,
    db: Session = Depends(get_db)
):
    """Get map tiles for a specific viewport."""
    if radius > 20:
        raise HTTPException(status_code=400, detail="Radius too large (max 20)")
        
    world = db.query(models.World).filter(models.World.id == world_id, models.World.is_active.is_(True)).first()
    if not world:
        raise HTTPException(status_code=404, detail="World not found")

    min_x, max_x = x - radius, x + radius
    min_y, max_y = y - radius, y + radius
    
    # Fetch cities in range
    cities = (
        db.query(models.City)
        .filter(
            models.City.world_id == world_id,
            models.City.x >= min_x,
            models.City.x <= max_x,
            models.City.y >= min_y,
            models.City.y <= max_y
        )
        .all()
    )
    
    # Pre-fetch owners and alliances
    owner_ids = {city.owner_id for city in cities if city.owner_id}
    users = db.query(models.User).filter(models.User.id.in_(owner_ids)).all() if owner_ids else []
    user_map = {user.id: user for user in users}
    
    memberships = db.query(models.AllianceMember).filter(models.AllianceMember.user_id.in_(owner_ids)).all() if owner_ids else []
    alliance_ids = {m.alliance_id for m in memberships}
    alliances = db.query(models.Alliance).filter(models.Alliance.id.in_(alliance_ids)).all() if alliance_ids else []
    alliance_map = {a.id: a for a in alliances}
    
    # Map user to alliance name
    user_alliance_map = {}
    for m in memberships:
        if m.alliance_id in alliance_map:
            user_alliance_map[m.user_id] = alliance_map[m.alliance_id].name

    # Create city map for quick lookup
    city_map = {(c.x, c.y): c for c in cities}
    
    tiles = []
    for cur_x in range(min_x, max_x + 1):
        for cur_y in range(min_y, max_y + 1):
            # Skip out of bounds
            if cur_x < 0 or cur_y < 0 or cur_x >= world.map_size or cur_y >= world.map_size:
                continue
                
            tile_type = world_gen.get_tile_type(cur_x, cur_y)
            city_entry = None
            
            if (cur_x, cur_y) in city_map:
                city = city_map[(cur_x, cur_y)]
                owner_name = user_map[city.owner_id].username if city.owner_id and city.owner_id in user_map else None
                alliance_name = user_alliance_map.get(city.owner_id) if city.owner_id else None
                
                # Calculate points (simplified)
                points = ranking_service.calculate_player_points(db, user_map[city.owner_id], world_id) if city.owner_id and city.owner_id in user_map else 0
                
                city_entry = PublicCityMapEntry(
                    city_id=city.id,
                    x=city.x,
                    y=city.y,
                    owner=_mask_name(owner_name),
                    alliance=alliance_name,
                    points=points,
                    tile_type=city.tile_type or tile_type
                )
            
            tiles.append(MapTile(x=cur_x, y=cur_y, type=tile_type, city=city_entry))
            
    return tiles


@router.get("/worlds", response_model=list[schemas.WorldRead])
def list_public_worlds(db: Session = Depends(get_db)):
    return db.query(models.World).filter(models.World.is_active.is_(True)).all()


@router.get("/world/{world_id}", response_model=schemas.WorldRead)
def get_public_world(world_id: int, db: Session = Depends(get_db)):
    world = db.query(models.World).filter(models.World.id == world_id, models.World.is_active.is_(True)).first()
    if not world:
        raise HTTPException(status_code=404, detail="World not found")
    return world


@router.get("/world/{world_id}/cities", response_model=list[PublicCityMapEntry])
def list_public_cities(world_id: int, db: Session = Depends(get_db)):
    world = db.query(models.World).filter(models.World.id == world_id, models.World.is_active.is_(True)).first()
    if not world:
        raise HTTPException(status_code=404, detail="World not found")

    cities = db.query(models.City).filter(models.City.world_id == world_id).all()
    owner_ids = {city.owner_id for city in cities if city.owner_id}

    users = (
        db.query(models.User)
        .filter(models.User.id.in_(owner_ids))
        .all()
    ) if owner_ids else []
    user_map = {user.id: user for user in users}

    memberships = (
        db.query(models.AllianceMember)
        .filter(models.AllianceMember.user_id.in_(owner_ids))
        .all()
    ) if owner_ids else []
    alliance_ids = {membership.alliance_id for membership in memberships}

    alliances = (
        db.query(models.Alliance)
        .filter(models.Alliance.id.in_(alliance_ids))
        .all()
    ) if alliance_ids else []
    alliance_map = {alliance.id: alliance for alliance in alliances}

    user_points: Dict[int, int] = {
        user.id: ranking_service.calculate_player_points(db, user, world_id)
        for user in users
    }

    entries: List[PublicCityMapEntry] = []
    for city in cities:
        owner = user_map.get(city.owner_id)
        membership = next((m for m in memberships if m.user_id == city.owner_id), None)
        alliance_name = None
        if membership:
            alliance = alliance_map.get(membership.alliance_id)
            if alliance:
                alliance_name = _mask_name(alliance.name)

        entries.append(
            PublicCityMapEntry(
                city_id=city.id,
                x=city.x,
                y=city.y,
                owner=_mask_name(owner.username) if owner else None,
                alliance=alliance_name,
                points=user_points.get(city.owner_id, 0),
            )
        )

    return entries


@router.get("/ranking/players", response_model=list[schemas.PlayerRanking])
def public_player_ranking(world_id: int, db: Session = Depends(get_db)):
    return ranking_service.get_player_ranking(db, world_id)


@router.get("/ranking/alliances", response_model=list[schemas.AllianceRanking])
def public_alliance_ranking(world_id: int, db: Session = Depends(get_db)):
    return ranking_service.get_alliance_ranking(db, world_id)


@router.get("/troops")
def public_troop_stats():
    return {
        "base_costs": economy.BASE_TROOP_COSTS,
        "training_times": economy.BASE_TRAINING_TIMES,
    }


@router.get("/buildings")
def public_building_info():
    return {
        "base_costs": economy.BASE_BUILDING_COSTS,
        "cost_growth": "Costs scale by 26% per level (1.26^(level-1)).",
    }


@router.get("/events/active", response_model=schemas.ActiveEventResponse)
def public_active_event(world_id: int = 1, db: Session = Depends(get_db)):
    event = event_service.get_active_event(db, world_id=world_id)
    modifiers = event_service.get_active_modifiers(db, world_id=world_id)
    return schemas.ActiveEventResponse(event=event, modifiers=schemas.EventModifiers(**modifiers))
