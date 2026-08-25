from datetime import timedelta

import pytest

from app import models
from app.services import adventure, hero, hero_rules


def _join_fixture_world(db_session, user, city):
    membership = models.PlayerWorld(
        user_id=user.id,
        world_id=city.world_id,
        starting_city_id=city.id,
    )
    db_session.add(membership)
    user.world_id = city.world_id
    db_session.add(user)
    db_session.commit()


def test_adventure_flow_is_world_scoped_and_retry_safe(db_session, user, city):
    _join_fixture_world(db_session, user, city)
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    assert hero_obj.world_id == city.world_id

    adventures = adventure.get_adventures(db_session, hero_obj)
    assert len([item for item in adventures if item.status == "available"]) == 3
    current = next(item for item in adventures if item.status == "available")
    assert current.rules_version == hero_rules.HERO_RULES_VERSION
    assert len(current.seed) == 64

    adventure.start_adventure(db_session, current.id, hero_obj)
    assert current.status == "active"
    assert hero_obj.status == "adventure"

    with pytest.raises(ValueError, match="Adventure not finished yet"):
        adventure.claim_adventure(db_session, current.id, hero_obj)

    current.started_at -= timedelta(seconds=current.duration + 1)
    db_session.commit()

    result = adventure.claim_adventure(db_session, current.id, hero_obj)
    assert result["status"] == "success"
    assert result["rules_version"] == hero_rules.HERO_RULES_VERSION
    assert result["seed"] == current.seed

    db_session.refresh(current)
    db_session.refresh(hero_obj)
    xp_after_first = (hero_obj.level, hero_obj.xp)
    items_after_first = db_session.query(models.HeroItem).filter_by(hero_id=hero_obj.id).count()
    resources_after_first = tuple(
        float(getattr(city, resource)) for resource in ("wood", "stone", "iron", "gold")
    )

    retry = adventure.claim_adventure(db_session, current.id, hero_obj)
    assert retry == result
    db_session.refresh(hero_obj)
    db_session.refresh(city)
    assert (hero_obj.level, hero_obj.xp) == xp_after_first
    assert db_session.query(models.HeroItem).filter_by(hero_id=hero_obj.id).count() == items_after_first
    assert tuple(
        float(getattr(city, resource)) for resource in ("wood", "stone", "iron", "gold")
    ) == resources_after_first
