"""World membership and starting-city onboarding.

Joining a world is a single server-authoritative transaction: the membership,
starting city and active-world pointer either all exist together or none do.
"""

from sqlalchemy.orm import Session

from .. import models
from . import world_gen


class WorldNotAvailableError(ValueError):
    """Raised when a requested world does not exist or cannot be joined."""


class StartingCityConsistencyError(RuntimeError):
    """Raised when persisted membership data points at an invalid city."""


def _get_locked_active_world(db: Session, world_id: int) -> models.World:
    world = (
        db.query(models.World)
        .filter(models.World.id == world_id, models.World.is_active.is_(True))
        .with_for_update()
        .one_or_none()
    )
    if world is None:
        raise WorldNotAvailableError("World not found or inactive")
    return world


def _validate_existing_starting_city(
    db: Session,
    membership: models.PlayerWorld,
    user_id: int,
) -> models.City:
    city = (
        db.query(models.City)
        .filter(
            models.City.id == membership.starting_city_id,
            models.City.owner_id == user_id,
            models.City.world_id == membership.world_id,
        )
        .one_or_none()
    )
    if city is None:
        raise StartingCityConsistencyError(
            "Membership starting city is missing or belongs to another player/world"
        )
    return city


def _find_legacy_player_city(
    db: Session,
    *,
    user_id: int,
    world_id: int,
) -> models.City | None:
    """Reuse legacy progress instead of creating an extra capital."""

    return (
        db.query(models.City)
        .filter(
            models.City.owner_id == user_id,
            models.City.world_id == world_id,
        )
        .order_by(models.City.id.asc())
        .first()
    )


def _create_starting_city(
    db: Session,
    *,
    user: models.User,
    world: models.World,
) -> models.City:
    if world.map_size <= 0:
        raise WorldNotAvailableError("World map is not configured for player spawns")

    try:
        x, y = world_gen.find_spawn_location(db, world.id, world.map_size)
    except ValueError as exc:
        raise WorldNotAvailableError("World has no available starting location") from exc

    city = models.City(
        name=f"Capital de {user.username}",
        owner_id=user.id,
        world_id=world.id,
        x=x,
        y=y,
        tile_type=world_gen.get_tile_type(x, y),
    )
    db.add(city)
    db.flush()
    return city


def join_world(
    db: Session,
    user: models.User,
    world_id: int,
) -> models.PlayerWorld:
    """Join/select a world and guarantee exactly one starting city.

    The world row is locked while assigning map coordinates. This serializes
    player spawns inside a world on PostgreSQL so two concurrent joins cannot
    select the same free tile. The database additionally enforces coordinate
    uniqueness as a final invariant.

    Repeated calls are idempotent. Legacy memberships with no
    ``starting_city_id`` reuse an existing owned city when possible.
    """

    try:
        world = _get_locked_active_world(db, world_id)
        locked_user = (
            db.query(models.User)
            .filter(models.User.id == user.id)
            .with_for_update()
            .one()
        )

        membership = (
            db.query(models.PlayerWorld)
            .filter(
                models.PlayerWorld.user_id == locked_user.id,
                models.PlayerWorld.world_id == world.id,
            )
            .one_or_none()
        )

        if membership is None:
            membership = models.PlayerWorld(
                user_id=locked_user.id,
                world_id=world.id,
            )
            db.add(membership)
            db.flush()

        if membership.starting_city_id is not None:
            _validate_existing_starting_city(db, membership, locked_user.id)
        else:
            starting_city = _find_legacy_player_city(
                db,
                user_id=locked_user.id,
                world_id=world.id,
            )
            if starting_city is None:
                starting_city = _create_starting_city(
                    db,
                    user=locked_user,
                    world=world,
                )
            membership.starting_city_id = starting_city.id

        locked_user.world_id = world.id
        db.add(locked_user)
        db.add(membership)
        db.commit()
        db.refresh(membership)
        return membership
    except Exception:
        db.rollback()
        raise
