import json
from datetime import datetime, timezone

import pytest

from app import models
from app.services import espionage


def _seed_for(*, attacker_spies, defender_spies, predicate, spy_modifier=1.0):
    for value in range(10_000):
        seed = f"{value:064x}"
        outcome = espionage.resolve_outcome(
            attacker_spies=attacker_spies,
            defender_spies=defender_spies,
            spy_modifier=spy_modifier,
            seed=seed,
        )
        if predicate(outcome):
            return seed, outcome
    raise AssertionError("Could not find deterministic espionage seed for test")


def _movement(city, target, *, spy_count):
    return models.Movement(
        origin_city_id=city.id,
        target_city_id=target.id,
        world_id=city.world_id,
        movement_type="spy",
        spy_count=spy_count,
        arrival_time=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )


def test_spy_outcome_is_reproducible_and_bounded():
    kwargs = {
        "attacker_spies": 3,
        "defender_spies": 2,
        "spy_modifier": 1.0,
        "seed": "7" * 64,
    }
    first = espionage.resolve_outcome(**kwargs)
    second = espionage.resolve_outcome(**kwargs)

    assert first == second
    assert espionage.SPY_LUCK_MIN <= first["luck"] <= espionage.SPY_LUCK_MAX
    assert espionage.SPY_SUCCESS_CHANCE_MIN <= first["success_chance"] <= espionage.SPY_SUCCESS_CHANCE_MAX
    assert espionage.SPY_DETECTION_CHANCE_MIN <= first["detection_chance"] <= espionage.SPY_DETECTION_CHANCE_MAX
    assert first["algorithm_version"] == espionage.ESPIONAGE_ALGORITHM_VERSION
    assert first["seed"] == kwargs["seed"]


def test_spy_intel_levels_are_tiered():
    assert espionage.calculate_intel_level(
        1, 3, spy_modifier=1.0, luck=0.0, success=True
    ) == 1
    assert espionage.calculate_intel_level(
        3, 2, spy_modifier=1.0, luck=0.0, success=True
    ) == 2
    assert espionage.calculate_intel_level(
        6, 2, spy_modifier=1.0, luck=0.0, success=True
    ) == 3
    assert espionage.calculate_intel_level(
        100, 0, spy_modifier=2.0, luck=espionage.SPY_LUCK_MAX, success=False
    ) == 0


def test_spy_failure_reveals_no_target_intel(monkeypatch, db_session, city, second_city):
    db_session.add(models.Troop(city_id=second_city.id, unit_type="spy", quantity=4))
    db_session.add(models.Troop(city_id=second_city.id, unit_type="archer", quantity=9))
    db_session.add(models.Building(city_id=second_city.id, name="wall", level=3))
    second_city.wood = 1234.0
    db_session.add(second_city)
    db_session.commit()

    movement = _movement(city, second_city, spy_count=1)
    db_session.add(movement)
    db_session.commit()
    db_session.refresh(movement)

    seed, expected = _seed_for(
        attacker_spies=1,
        defender_spies=4,
        predicate=lambda outcome: not outcome["success"] and outcome["detected"],
    )
    monkeypatch.setattr(espionage, "derive_seed", lambda *args, **kwargs: seed)

    attacker_report, defender_report, surviving_spies = espionage.resolve_spy(
        db_session, movement
    )
    content = json.loads(attacker_report.content)

    assert content["success"] is False
    assert content["intel_level"] == 0
    assert content["resources"] is None
    assert content["troops"] is None
    assert content["buildings"] is None
    assert "spies" not in content["defender"]
    assert surviving_spies == 0
    assert defender_report is not None
    assert content["seed"] == seed
    assert content["success_chance"] == pytest.approx(expected["success_chance"])


def test_successful_undetected_spy_returns_and_only_reveals_allowed_tier(
    monkeypatch, db_session, city, second_city
):
    db_session.add(models.Troop(city_id=second_city.id, unit_type="spy", quantity=1))
    db_session.add(models.Troop(city_id=second_city.id, unit_type="archer", quantity=9))
    db_session.add(models.Building(city_id=second_city.id, name="wall", level=3))
    second_city.wood = 1234.0
    second_city.stone = 987.0
    db_session.add(second_city)
    db_session.commit()

    movement = _movement(city, second_city, spy_count=6)
    db_session.add(movement)
    db_session.commit()
    db_session.refresh(movement)

    seed, expected = _seed_for(
        attacker_spies=6,
        defender_spies=1,
        predicate=lambda outcome: outcome["success"]
        and not outcome["detected"]
        and outcome["intel_level"] == 3,
    )
    monkeypatch.setattr(espionage, "derive_seed", lambda *args, **kwargs: seed)

    attacker_report, defender_report, surviving_spies = espionage.resolve_spy(
        db_session, movement
    )
    content = json.loads(attacker_report.content)

    assert content["success"] is True
    assert content["detected"] is False
    assert content["intel_level"] == 3
    assert content["revealed"] == ["resources", "troops", "buildings"]
    assert content["resources"]["wood"] == pytest.approx(1234.0)
    assert content["troops"]["spy"] == 1
    assert content["troops"]["archer"] == 9
    assert content["buildings"]["wall"] == 3
    assert surviving_spies == 6
    assert defender_report is None
    assert content["seed"] == seed
    assert content["luck"] == pytest.approx(expected["luck"])


def test_spy_world_boundary_is_rejected(db_session, city, second_city):
    other_world = models.World(
        name="OtherWorld",
        speed_modifier=1.0,
        resource_modifier=1.0,
    )
    db_session.add(other_world)
    db_session.flush()
    second_city.world_id = other_world.id
    db_session.add(second_city)
    db_session.commit()

    movement = _movement(city, second_city, spy_count=1)
    db_session.add(movement)
    db_session.commit()

    with pytest.raises(ValueError, match="world boundary"):
        espionage.resolve_spy(db_session, movement)
