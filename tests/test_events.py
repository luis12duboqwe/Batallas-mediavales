from datetime import datetime, timezone, timedelta

from app import models
from app.services import balance, combat, event


def test_event_modifiers_and_creation(db_session):
    payload = models.WorldEvent(
        world_id=1,
        name="Doble de Recursos",
        description="",
        start_time=datetime.now(timezone.utc) - timedelta(hours=1),
        end_time=datetime.now(timezone.utc) + timedelta(hours=1),
        modifiers={"production_speed": 2.0},
    )
    db_session.add(payload)
    db_session.commit()

    modifiers = event.get_active_modifiers(db_session)
    assert modifiers["production_speed"] == 2.0

    merged = event._merge_modifiers({"movement_speed": 0.5})
    assert merged["movement_speed"] == 0.5


def test_event_tables_are_canonical_balance_objects():
    assert event.DEFAULT_MODIFIERS is balance.EVENT_DEFAULT_MODIFIERS
    assert event.EVENT_TEMPLATES is balance.EVENT_TEMPLATES


def test_loot_modifier_increases_effective_carry_without_overdrawing(
    db_session, city, second_city
):
    city.wood = city.clay = city.iron = 500.0
    second_city.wood = second_city.clay = second_city.iron = 1000.0
    db_session.commit()

    base_result = combat.resolve_battle(
        city,
        second_city,
        {"basic_infantry": 10},
        modifiers={**balance.EVENT_DEFAULT_MODIFIERS, "loot_modifier": 1.0},
    )
    base_loot = sum(base_result["loot"].values())

    city.wood = city.clay = city.iron = 500.0
    second_city.wood = second_city.clay = second_city.iron = 1000.0
    db_session.flush()

    boosted_result = combat.resolve_battle(
        city,
        second_city,
        {"basic_infantry": 10},
        modifiers={**balance.EVENT_DEFAULT_MODIFIERS, "loot_modifier": 1.2},
    )
    boosted_loot = sum(boosted_result["loot"].values())

    base_capacity = 10 * balance.UNIT_COMBAT_STATS["basic_infantry"]["carry"]
    assert boosted_loot > base_loot
    assert boosted_loot <= int(base_capacity * 1.2)
    assert second_city.wood >= 0
    assert second_city.clay >= 0
    assert second_city.iron >= 0
