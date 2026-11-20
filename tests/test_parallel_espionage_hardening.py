"""Privacy, authorization and determinism regression tests for espionage."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from app import models
from app.services import espionage


def _mission(db_session, city, target, *, movement_type="spy", spy_count=1):
    movement = models.Movement(
        origin_city_id=city.id,
        target_city_id=target.id,
        world_id=city.world_id,
        movement_type=movement_type,
        spy_count=spy_count,
        arrival_time=datetime.now(timezone.utc),
        status="ongoing",
    )
    db_session.add(movement)
    db_session.commit()
    db_session.refresh(movement)
    return movement


def _outcome_seed(*, attacker_spies=1, defender_spies=4, condition):
    for index in range(5000):
        seed = f"{index:064x}"
        outcome = espionage.resolve_outcome(
            attacker_spies=attacker_spies,
            defender_spies=defender_spies,
            spy_modifier=1.0,
            seed=seed,
        )
        if condition(outcome):
            return seed
    raise AssertionError("No matching deterministic outcome found")


def test_parallel_espionage_anonymous_defender_report_hides_attacker_fk(
    db_session, city, second_city, monkeypatch
):
    db_session.add(models.Troop(city_id=second_city.id, unit_type="spy", quantity=4))
    db_session.commit()
    mission = _mission(db_session, city, second_city)
    seed = _outcome_seed(
        condition=lambda o: o["detected"] and not o["attacker_identified"],
    )
    monkeypatch.setattr(espionage, "derive_seed", lambda *a, **k: seed)

    attacker_report, defender_report, _ = espionage.resolve_spy(db_session, mission)

    assert defender_report is not None
    defender_payload = json.loads(defender_report.content)
    assert defender_payload["attacker"]["name"] == "Desconocido"
    assert "seed" not in defender_payload
    assert defender_report.attacker_city_id is None
    assert attacker_report.attacker_city_id == city.id
    assert defender_report.city_id == second_city.id


def test_parallel_espionage_identified_defender_report_keeps_attacker_fk(
    db_session, city, second_city, monkeypatch
):
    db_session.add(models.Troop(city_id=second_city.id, unit_type="spy", quantity=4))
    db_session.commit()
    mission = _mission(db_session, city, second_city)
    seed = _outcome_seed(
        condition=lambda o: o["detected"] and o["attacker_identified"],
    )
    monkeypatch.setattr(espionage, "derive_seed", lambda *a, **k: seed)

    _, defender_report, _ = espionage.resolve_spy(db_session, mission)

    assert defender_report is not None
    assert json.loads(defender_report.content)["attacker"]["name"] == city.name
    assert defender_report.attacker_city_id == city.id


def test_parallel_espionage_rejects_other_movement_type_before_reports(
    db_session, city, second_city
):
    mission = _mission(
        db_session, city, second_city, movement_type="attack", spy_count=2
    )

    with pytest.raises(ValueError, match="spy"):
        espionage.resolve_spy(db_session, mission)

    assert db_session.query(models.Report).count() == 0


def test_parallel_espionage_rejects_nonplayer_origin_without_reports(
    db_session, city, second_city
):
    barbarian = models.City(
        name="No player origin",
        world_id=city.world_id,
        owner_id=None,
        x=22,
        y=23,
    )
    db_session.add(barbarian)
    db_session.commit()
    mission = _mission(db_session, barbarian, second_city)

    with pytest.raises(ValueError, match="player|owner"):
        espionage.resolve_spy(db_session, mission)

    assert db_session.query(models.Report).count() == 0


def test_parallel_espionage_rejects_cross_world_before_reports(
    db_session, city, second_city
):
    world = models.World(name="Spy other world")
    db_session.add(world)
    db_session.flush()
    second_city.world_id = world.id
    db_session.commit()
    mission = _mission(db_session, city, second_city)

    with pytest.raises(ValueError, match="world boundary"):
        espionage.resolve_spy(db_session, mission)

    assert db_session.query(models.Report).count() == 0


def test_parallel_espionage_simultaneous_rng_streams_are_isolated():
    seeds = [f"parallel-spy-{index}" for index in range(32)]

    def calculate(seed):
        return espionage.resolve_outcome(
            attacker_spies=5, defender_spies=3, spy_modifier=1.0, seed=seed
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        concurrent = list(executor.map(calculate, seeds))

    assert concurrent == [calculate(seed) for seed in seeds]
    assert len({result["seed"] for result in concurrent}) == len(seeds)
    assert all(0 <= result["intel_level"] <= 3 for result in concurrent)
