import pytest

from app import models
from app.services import balance, combat, hero, hero_rules, production


def _equip(db_session, hero_obj: models.Hero, name: str) -> models.HeroItem:
    hero.seed_items(db_session)
    template = db_session.query(models.ItemTemplate).filter_by(name=name).one()
    item = models.HeroItem(hero_id=hero_obj.id, template_id=template.id)
    db_session.add(item)
    db_session.commit()
    hero.equip_item(db_session, hero_obj, item.id)
    db_session.expire(hero_obj, ["items"])
    return item


def test_attack_and_defense_items_modify_live_combat_with_versioned_caps(
    db_session,
    user,
    city,
):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero_obj.attack_points = 2
    hero_obj.defense_points = 2
    hero_obj.status = "moving"
    _equip(db_session, hero_obj, "Hacha de Guerra")
    db_session.refresh(hero_obj)

    troops = {"basic_infantry": 10}
    base_distribution, base_attack = combat._split_attack_by_type(troops, None)
    boosted_distribution, boosted_attack = combat._split_attack_by_type(troops, hero_obj)
    expected_attack_bonus = 0.02 + 0.15

    assert hero_rules.attack_bonus(hero_obj) == pytest.approx(expected_attack_bonus)
    assert boosted_attack == pytest.approx(base_attack * (1 + expected_attack_bonus))
    for category in base_distribution:
        assert boosted_distribution[category] == pytest.approx(
            base_distribution[category] * (1 + expected_attack_bonus)
        )

    hero_obj.status = "home"
    _equip(db_session, hero_obj, "Armadura de Placas")
    db_session.refresh(hero_obj)
    base_defense = combat._defense_values(troops, None)
    boosted_defense = combat._defense_values(troops, hero_obj)
    expected_defense_bonus = 0.02 + 0.20

    assert hero_rules.defense_bonus(hero_obj) == pytest.approx(expected_defense_bonus)
    for category in base_defense:
        assert boosted_defense[category] == pytest.approx(
            base_defense[category] * (1 + expected_defense_bonus)
        )

    assert hero_rules.HERO_RULES_VERSION == "2026.08.25-bm0068-v1"


def test_hero_bonus_caps_prevent_item_or_attribute_stacking_abuse(
    db_session,
    user,
    city,
):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero_obj.attack_points = 999
    hero_obj.defense_points = 999
    db_session.commit()
    _equip(db_session, hero_obj, "Hacha de Guerra")
    _equip(db_session, hero_obj, "Caballo de Guerra")
    _equip(db_session, hero_obj, "Mapa Antiguo")
    db_session.refresh(hero_obj)

    assert hero_rules.attack_bonus(hero_obj) == hero_rules.HERO_MAX_ATTACK_BONUS
    assert hero_rules.defense_bonus(hero_obj) == hero_rules.HERO_MAX_DEFENSE_BONUS
    assert hero_rules.speed_bonus(hero_obj) == hero_rules.HERO_MAX_SPEED_BONUS


def test_production_attribute_affects_only_home_alive_hero_city(
    db_session,
    user,
    city,
):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero_obj.production_points = 4
    hero_obj.status = "home"
    hero_obj.health = 100
    db_session.commit()

    home_rates = production.get_gross_production_per_hour(db_session, city)
    expected_bonus = 4 * hero_rules.HERO_PRODUCTION_BONUS_PER_POINT
    for resource in balance.RESOURCE_FIELDS:
        assert home_rates[resource] == pytest.approx(
            balance.PRODUCTION_RATES_PER_HOUR[resource] * (1 + expected_bonus)
        )

    hero_obj.status = "moving"
    db_session.commit()
    away_rates = production.get_gross_production_per_hour(db_session, city)
    for resource in balance.RESOURCE_FIELDS:
        assert away_rates[resource] == pytest.approx(
            balance.PRODUCTION_RATES_PER_HOUR[resource]
        )
