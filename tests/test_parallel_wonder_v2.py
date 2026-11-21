"""BM-0062 world-pinned, collaborative wonder financing regressions."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app import models
from app.database import SessionLocal
from app.schemas.wonder import WonderContributionCreate
from app.services import balance, building, wonder_funding
from app.utils import utc_now


def _setup(db, user, city, *, level=0, second_user=True):
    world = city.world
    world.wonder_rules_version = balance.WONDER_ALLIANCE_RULES
    world.lifecycle_status = "open"
    world.is_active = True
    membership = models.PlayerWorld(user_id=user.id, world_id=world.id, starting_city_id=city.id)
    alliance = models.Alliance(world_id=world.id, name="MaravillaQA", leader_id=user.id)
    db.add_all([membership, alliance])
    db.flush()
    db.add(models.AllianceMember(alliance_id=alliance.id, user_id=user.id, rank=3))
    other = None
    donor = None
    if second_user:
        other = models.User(username="allied_wonder", email="allied.wonder@example.com", hashed_password="test", is_verified=True)
        db.add(other)
        db.flush()
        donor = models.City(name="Ciudad aliada", owner_id=other.id, world_id=world.id, x=4, y=4)
        db.add(donor)
        db.flush()
        db.add_all([
            models.PlayerWorld(user_id=other.id, world_id=world.id, starting_city_id=donor.id),
            models.AllianceMember(alliance_id=alliance.id, user_id=other.id, rank=1),
        ])
    for name, value in (("town_hall", 20), ("warehouse", 20), ("cathedral", 10), ("world_wonder", level)):
        if name != "world_wonder" or level:
            db.add(models.Building(city_id=city.id, name=name, level=value))
    for player_city in (city, donor):
        if player_city:
            for res in balance.RESOURCE_FIELDS:
                setattr(player_city, res, 45000.0)
            player_city.last_production = utc_now()
    db.commit()
    return alliance, other, donor


def _fund(db, user_id, city, donor, values, key=None):
    return wonder_funding.contribute(
        db, world_id=city.world_id, contributor_id=user_id, target_city_id=city.id,
        source_city_id=donor.id, amounts=values, idempotency_key=key or uuid4().hex,
    )


def _amounts(**values):
    return {key: values.get(key, 0) for key in balance.RESOURCE_FIELDS}


@pytest.mark.parametrize("level", [1, 9, 10, 50, 100])
def test_legacy_pinned_and_v2_viable_cost_and_schedule(level):
    legacy = balance.get_wonder_cost(level, "legacy-v1")
    assert legacy == balance.get_building_cost("world_wonder", level)
    assert balance.get_wonder_build_time(level, "legacy-v1") == balance.get_building_build_time("world_wonder", level)
    current = balance.get_wonder_cost(level, "alliance-v2")
    assert all(type(x) is int and x >= 1 for x in current.values())
    assert all(current[res] <= 100000 for res in ("wood", "stone", "iron"))
    assert balance.get_wonder_build_time(level, "alliance-v2") <= 20000
    assert current["wood"] <= balance.get_wonder_cost(100, "alliance-v2")["wood"]


def test_v2_sequential_time_and_total_cost_reasonable():
    total_seconds = sum(balance.get_wonder_build_time(i, "alliance-v2") for i in range(1, 101))
    assert 7 * 86400 <= total_seconds <= 30 * 86400
    total_wood = sum(balance.get_wonder_cost(i, "alliance-v2")["wood"] for i in range(1, 101))
    assert 1_000_000 < total_wood < 10_000_000
    assert sum(balance.get_wonder_cost(i, "legacy-v1")["wood"] for i in range(1, 101)) > 1e12


def test_contributions_allied_and_owner_cancel_resume_complete(db_session, user, city):
    alliance, ally, donor = _setup(db_session, user, city)
    first = _amounts(wood=5000, stone=5000, iron=5000, gold=1250)
    second = _amounts(wood=5000, stone=5000, iron=5000, gold=1250)
    before_ally = donor.wood
    key = uuid4().hex
    progress = _fund(db_session, ally.id, city, donor, first, key)
    assert progress["status"] == "funding"
    assert progress["remaining"]["wood"] == 5000
    db_session.refresh(donor)
    assert donor.wood == pytest.approx(before_ally - 5000)
    again = _fund(db_session, ally.id, city, donor, first, key)
    assert again == progress
    db_session.refresh(donor)
    assert donor.wood == pytest.approx(before_ally - 5000)
    with pytest.raises(ValueError, match="Idempotency"):
        _fund(db_session, ally.id, city, donor, _amounts(wood=1), key)

    ready = _fund(db_session, user.id, city, city, second)
    assert ready["status"] == "ready"
    assert ready["remaining"] == _amounts()
    assert ready["can_queue"]
    quote = next(x for x in building.get_available_buildings(db_session, city) if x["name"] == "world_wonder")
    assert quote["can_upgrade"] is True
    assert quote["cost"] == balance.get_wonder_cost(1, "alliance-v2")

    queue = building.queue_upgrade(db_session, city, "world_wonder")
    assert queue.paid_cost == {}
    assert db_session.query(models.WonderFunding).one().status == "queued"
    with pytest.raises(ValueError, match="queue slots|already queued"):
        building.queue_upgrade(db_session, city, "world_wonder")
    assert building.cancel_building_queue(db_session, queue.id, user.id) is True
    assert db_session.query(models.WonderFunding).one().status == "ready"
    db_session.refresh(city)
    assert city.wood == pytest.approx(40000)  # No liquid refund of 5000 units
    second_queue = building.queue_upgrade(db_session, city, "world_wonder")
    second_queue.finish_time = utc_now() - timedelta(seconds=5)
    db_session.commit()
    building.process_building_queues(db_session)
    project = db_session.query(models.WonderFunding).one()
    assert project.status == "completed"
    assert db_session.query(models.Building).filter_by(city_id=city.id, name="world_wonder").one().level == 1
    assert db_session.query(models.WonderContribution).count() == 2


def test_atomic_reject_overpay_and_no_resources(db_session, user, city):
    _, ally, donor = _setup(db_session, user, city)
    pre = donor.wood
    with pytest.raises(ValueError, match="remaining"):
        _fund(db_session, ally.id, city, donor, _amounts(wood=10001))
    db_session.refresh(donor)
    assert donor.wood == pre
    assert db_session.query(models.WonderContribution).count() == 0
    assert db_session.query(models.WonderFunding).count() == 0

    donor.wood = 1
    db_session.commit()
    with pytest.raises(ValueError, match="Insufficient"):
        _fund(db_session, ally.id, city, donor, _amounts(wood=500))
    db_session.refresh(donor)
    assert donor.wood == 1
    assert db_session.query(models.WonderContribution).count() == 0


def test_unauthorized_cross_world_and_alliance_rejected(db_session, user, city):
    _, ally, donor = _setup(db_session, user, city)
    stranger = models.User(username="wonder_stranger", email="stranger.wonder@example.com", hashed_password="test", is_verified=True)
    db_session.add(stranger)
    db_session.flush()
    foreign_city = models.City(name="Ajena", owner_id=stranger.id, world_id=city.world_id, x=5, y=5)
    db_session.add(foreign_city)
    db_session.commit()
    with pytest.raises(ValueError, match="alliance"):
        _fund(db_session, stranger.id, city, foreign_city, _amounts(wood=1))
    with pytest.raises(ValueError, match="source city"):
        _fund(db_session, ally.id, city, foreign_city, _amounts(wood=1))
    with pytest.raises(ValueError, match="not owned by your alliance"):
        wonder_funding.get_funding(db_session, city.id, city.world_id, stranger.id)
    with pytest.raises(ValueError, match="World is not open"):
        wonder_funding.contribute(
            db_session, world_id=city.world_id + 999, contributor_id=user.id,
            target_city_id=city.id, source_city_id=city.id,
            amounts=_amounts(wood=1), idempotency_key=uuid4().hex,
        )


def test_stale_world_and_legacy_rejected_without_debit(db_session, user, city):
    _setup(db_session, user, city)
    city.world.lifecycle_status = "paused"
    city.world.is_active = False
    db_session.commit()
    with pytest.raises(ValueError, match="World is not open"):
        _fund(db_session, user.id, city, city, _amounts(wood=1))
    db_session.refresh(city)
    assert city.wood == 45000
    city.world.lifecycle_status = "open"
    city.world.is_active = True
    city.world.wonder_rules_version = "legacy-v1"
    db_session.commit()
    with pytest.raises(ValueError, match="Legacy"):
        _fund(db_session, user.id, city, city, _amounts(wood=1))
    assert db_session.query(models.WonderContribution).count() == 0


@pytest.mark.parametrize("bad", [True, 1.5, "5", -1])
def test_strict_amount_validation(bad):
    with pytest.raises(ValidationError):
        WonderContributionCreate(
            target_city_id=1, source_city_id=2,
            idempotency_key="testunique123", wood=bad,
        )


def test_victory_level_100_can_be_funded_without_overflow(db_session, user, city):
    alliance, ally, donor = _setup(db_session, user, city, level=99)
    cost = balance.get_wonder_cost(100, "alliance-v2")
    assert cost["wood"] > balance.get_storage_capacity(20)
    ally_amounts = _amounts(
        wood=min(40000, cost["wood"]), stone=min(40000, cost["stone"]),
        iron=min(40000, cost["iron"]), gold=min(10000, cost["gold"]),
    )
    owner_amounts = {res: cost[res] - ally_amounts[res] for res in balance.RESOURCE_FIELDS}
    assert max(owner_amounts.values()) <= 45000
    _fund(db_session, ally.id, city, donor, ally_amounts)
    ready = _fund(db_session, user.id, city, city, owner_amounts)
    assert ready["status"] == "ready"
    queue = building.queue_upgrade(db_session, city, "world_wonder")
    queue.finish_time = utc_now() - timedelta(seconds=3)
    db_session.commit()
    building.process_building_queues(db_session)
    db_session.refresh(city.world)
    assert city.world.lifecycle_status == "closed"
    assert city.world.winner_id == user.id
    assert city.world.winner_alliance_id == alliance.id
    assert db_session.query(models.WonderFunding).one().status == "completed"


def test_v2_funding_is_pinned_to_original_owner_and_alliance(db_session, user, city):
    alliance, ally, donor = _setup(db_session, user, city)
    _fund(db_session, ally.id, city, donor, _amounts(wood=100))
    original = db_session.query(models.WonderFunding).one()
    city.owner_id = ally.id
    db_session.commit()
    assert wonder_funding.get_funding(db_session, city.id, city.world_id, ally.id)["funded"]["wood"] == 0
    assert original.funded_wood == 100  # no transfer to a new owner
    db_session.refresh(city)
    with pytest.raises(ValueError, match="complete alliance financing"):
        building.queue_upgrade(db_session, city, "world_wonder")


def test_fabricated_v2_queue_never_progresses_or_wins(db_session, user, city):
    _setup(db_session, user, city, level=99)
    pending = models.BuildingQueue(
        city_id=city.id, building_type="world_wonder", target_level=100,
        finish_time=utc_now() - timedelta(seconds=10), paid_cost={},
    )
    db_session.add(pending)
    db_session.commit()
    assert building.process_building_queues(db_session) == []
    db_session.refresh(city.world)
    assert city.world.lifecycle_status == "open"
    assert city.world.winner_id is None
    assert db_session.query(models.Building).filter_by(
        city_id=city.id, name="world_wonder",
    ).one().level == 99


def test_v2_victory_keeps_pinned_sponsor_after_leaving_alliance(db_session, user, city):
    alliance, ally, donor = _setup(db_session, user, city, level=99)
    cost = balance.get_wonder_cost(100, "alliance-v2")
    first = _amounts(wood=40000, stone=40000, iron=40000, gold=10000)
    second = {res: cost[res] - first[res] for res in balance.RESOURCE_FIELDS}
    _fund(db_session, ally.id, city, donor, first)
    _fund(db_session, user.id, city, city, second)
    queue = building.queue_upgrade(db_session, city, "world_wonder")
    db_session.query(models.AllianceMember).filter_by(
        alliance_id=alliance.id, user_id=user.id,
    ).delete()
    queue.finish_time = utc_now() - timedelta(seconds=3)
    db_session.commit()
    building.process_building_queues(db_session)
    db_session.refresh(city.world)
    assert city.world.lifecycle_status == "closed"
    assert city.world.winner_alliance_id == alliance.id


def test_idempotent_replay_releases_transaction(db_session, user, city):
    _setup(db_session, user, city, second_user=False)
    key = uuid4().hex
    amounts = _amounts(wood=100)
    original = _fund(db_session, user.id, city, city, amounts, key)

    assert _fund(db_session, user.id, city, city, amounts, key) == original
    assert not db_session.in_transaction()
    assert db_session.query(models.WonderContribution).count() == 1


def test_contribution_snapshot_precedes_next_committed_contribution(
    db_session, user, city, monkeypatch,
):
    _, ally, donor = _setup(db_session, user, city)
    city_id, world_id, donor_id, ally_id = city.id, city.world_id, donor.id, ally.id
    commit = db_session.commit

    def commit_then_contribute():
        monkeypatch.setattr(db_session, "commit", commit)
        commit()
        with SessionLocal() as concurrent:
            wonder_funding.contribute(
                concurrent, world_id=world_id, contributor_id=ally_id,
                target_city_id=city_id, source_city_id=donor_id,
                amounts={"wood": 200}, idempotency_key=uuid4().hex,
            )

    monkeypatch.setattr(db_session, "commit", commit_then_contribute)
    result = _fund(db_session, user.id, city, city, _amounts(wood=100))

    assert result["funded"]["wood"] == 100
    assert wonder_funding.get_funding(
        db_session, city_id, world_id, user.id,
    )["funded"]["wood"] == 300


@pytest.mark.parametrize("target_level", [9, 10, 50])
def test_wonder_levels_require_the_last_unit_before_queueing(
    db_session, user, city, target_level,
):
    _setup(db_session, user, city, level=target_level - 1, second_user=False)
    cost = balance.get_wonder_cost(target_level, balance.WONDER_ALLIANCE_RULES)
    partial = {**cost, "gold": cost["gold"] - 1}
    snapshot = _fund(db_session, user.id, city, city, partial)
    assert snapshot["target_level"] == target_level
    assert snapshot["remaining"] == _amounts(gold=1)
    assert not snapshot["can_queue"]

    with pytest.raises(ValueError, match="complete alliance financing"):
        building.queue_upgrade(db_session, city, "world_wonder")

    snapshot = _fund(db_session, user.id, city, city, _amounts(gold=1))
    assert snapshot["can_queue"]
    queue = building.queue_upgrade(db_session, city, "world_wonder")
    assert queue.target_level == target_level
    assert queue.paid_cost == {}
