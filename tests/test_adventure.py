from datetime import timedelta

import pytest

from app.services import adventure, hero, hero_rules


def test_adventure_flow_is_auditable_and_retry_safe(db_session, user, city):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero.seed_items(db_session)

    adventures = adventure.get_adventures(db_session, hero_obj.id)
    assert len([row for row in adventures if row.status in {"available", "active"}]) == 3
    assert all(row.rules_version == hero_rules.HERO_RULES_VERSION for row in adventures)

    adv = adventures[0]
    adventure.start_adventure(db_session, adv.id, hero_obj)
    assert adv.status == "active"
    assert hero_obj.status == "adventure"
    assert adv.started_at is not None
    assert adv.outcome_seed is not None
    assert len(adv.outcome_seed) == 64

    with pytest.raises(ValueError, match="Adventure not finished yet"):
        adventure.claim_adventure(db_session, adv.id, hero_obj)

    adv.started_at -= timedelta(seconds=adv.duration + 1)
    db_session.commit()

    first = adventure.claim_adventure(db_session, adv.id, hero_obj)
    db_session.refresh(hero_obj)
    xp_after_first = hero_obj.xp
    health_after_first = hero_obj.health
    inventory_after_first = db_session.query(type(hero_obj.items[0])).filter_by(hero_id=hero_obj.id).count() if hero_obj.items else 0
    resources_after_first = tuple(float(getattr(city, resource)) for resource in ("wood", "stone", "iron", "gold"))

    second = adventure.claim_adventure(db_session, adv.id, hero_obj)
    db_session.refresh(hero_obj)
    db_session.refresh(city)

    assert second == first
    assert first["rules_version"] == hero_rules.HERO_RULES_VERSION
    assert first["seed"] == adv.outcome_seed
    assert len(first["seed"]) == 64
    assert hero_obj.xp == xp_after_first
    assert hero_obj.health == health_after_first
    assert (db_session.query(type(hero_obj.items[0])).filter_by(hero_id=hero_obj.id).count() if hero_obj.items else 0) == inventory_after_first
    assert tuple(float(getattr(city, resource)) for resource in ("wood", "stone", "iron", "gold")) == resources_after_first
