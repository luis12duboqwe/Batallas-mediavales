from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app import models, schemas
from app.services import combat, pve


def test_world_creation_rejects_map_too_small_for_pve_catalog_but_legacy_read_survives():
    with pytest.raises(ValidationError):
        schemas.WorldCreate(name="Too Small", map_size=5)

    created = schemas.WorldCreate(name="Minimum PvE World", map_size=10)
    assert created.map_size == 10

    # Existing data must remain readable so an old world can be inspected and
    # migrated instead of turning list/read endpoints into response 500s.
    legacy = schemas.WorldRead(
        id=99,
        name="Legacy Tiny World",
        map_size=5,
        created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )
    assert legacy.map_size == 5


def test_owned_oasis_cannot_pay_first_conquest_reward_again(
    db_session,
    city: models.City,
    monkeypatch,
):
    city.wood = 100.0
    oasis = models.Oasis(
        world_id=city.world_id,
        x=city.x + 3,
        y=city.y + 3,
        resource_type="wood",
        bonus_percent=25,
        troops={},
        owner_city_id=city.id,
    )
    db_session.add_all([city, oasis])
    db_session.commit()
    db_session.refresh(city)
    db_session.refresh(oasis)

    expected_reward = pve.oasis_conquest_reward(oasis)
    assert expected_reward["wood"] > 0
    before_wood = float(city.wood)

    monkeypatch.setattr(
        combat._impl,
        "resolve_oasis_battle",
        lambda *args, **kwargs: {
            "conquered": True,
            "conquest": True,
            "loot": {},
        },
    )

    result = combat.resolve_oasis_battle(city, oasis)

    assert float(city.wood) == before_wood
    assert result["loot"] == {}
    assert result["pve"]["conquest_reward"] == expected_reward
    assert result["pve"]["credited_reward"] == {}
    assert result["pve"]["was_wild"] is False
    assert result["pve"]["reward_eligible"] is False
