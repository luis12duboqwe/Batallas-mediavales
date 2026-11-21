"""BM-0062/PD-009: legacy World Wonder audits must never migrate or mutate."""

from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import event

from app import models
from app.services import balance
from app.services.wonder_transition_audit import audit_legacy_wonder_transition
from app.utils import utc_now


def _paused(city, db):
    world = city.world
    world.lifecycle_status = "paused"
    world.is_active = False
    world.pause_started_at = utc_now()
    db.commit()
    return world


def test_active_historical_world_has_storage_gap_and_cannot_auto_convert(db_session, user, city):
    world = city.world
    db_session.add(models.PlayerWorld(user_id=user.id, world_id=world.id, starting_city_id=city.id))
    db_session.commit()
    result = audit_legacy_wonder_transition(db_session, world.id)
    assert result["world_id"] == world.id
    assert result["rules_version"] == "legacy-v1"
    assert result["counts"]["players"] == 1
    assert result["counts"]["cities"] == 1
    assert result["legacy_level_10_exceeds_storage"]
    assert result["max_warehouse_capacity_per_resource"] == 45000
    assert result["legacy_level_10_cost"]["wood"] > 45000
    assert "WORLD_NOT_PAUSED" in result["blockers"]
    assert "WORLD_ACTIVE_FLAG" in result["blockers"]
    assert "PLAYER_CONSENT_NOT_VERIFIED" in result["blockers"]
    assert result["requires_product_approval"] is True
    assert result["can_auto_convert"] is False
    db_session.refresh(world)
    assert world.wonder_rules_version == "legacy-v1"
    assert world.lifecycle_status == "open"


def test_paused_world_without_players_still_requires_product_approval(db_session, city):
    world = _paused(city, db_session)
    result = audit_legacy_wonder_transition(db_session, world.id)
    assert "WORLD_NOT_PAUSED" not in result["blockers"]
    assert "WORLD_ACTIVE_FLAG" not in result["blockers"]
    assert result["counts"]["players"] == 0
    assert "OWNED_CITIES_WITHOUT_MEMBERSHIP" in result["blockers"]
    assert result["can_auto_convert"] is False
    assert result["requires_product_approval"] is True


def test_pending_wonder_queue_existing_progress_and_winner_are_reported(db_session, user, city):
    world = _paused(city, db_session)
    db_session.add_all([
        models.Building(city_id=city.id, name="world_wonder", level=9),
        models.BuildingQueue(
            city_id=city.id,
            building_type="world_wonder",
            target_level=10,
            finish_time=utc_now() + timedelta(hours=1),
            paid_cost={"wood": 100},
        ),
    ])
    world.winner_id = user.id
    world.ended_at = utc_now()
    db_session.commit()
    report = audit_legacy_wonder_transition(db_session, world.id)
    assert report["counts"]["wonder_buildings"] == 1
    assert report["counts"]["highest_wonder_level"] == 9
    assert report["counts"]["pending_wonder_queues"] == 1
    assert "EXISTING_WONDER_LEVELS_REQUIRE_POLICY" in report["blockers"]
    assert "PENDING_WONDER_QUEUE_REQUIRES_RECONCILIATION" in report["blockers"]
    assert "WORLD_ALREADY_ENDED" in report["blockers"]
    assert report["can_auto_convert"] is False
    assert db_session.query(models.BuildingQueue).count() == 1


def test_existing_funding_ledger_detected_even_in_legacy_world(db_session, user, city):
    _paused(city, db_session)
    alliance = models.Alliance(name="Old alliance", world_id=city.world_id, leader_id=user.id)
    db_session.add(alliance)
    db_session.flush()
    funding = models.WonderFunding(
        world_id=city.world_id,
        city_id=city.id,
        owner_id=user.id,
        alliance_id=alliance.id,
        target_level=1,
        funded_wood=50,
        status="funding",
    )
    db_session.add(funding)
    db_session.flush()
    db_session.add(models.WonderContribution(
        world_id=city.world_id, funding_id=funding.id, contributor_id=user.id,
        source_city_id=city.id, idempotency_key="legacy-test-ledger-0001", wood=50,
    ))
    db_session.commit()
    report = audit_legacy_wonder_transition(db_session, city.world_id)
    assert report["counts"]["funding_projects"] == 1
    assert report["counts"]["contributions"] == 1
    assert "EXISTING_FUNDING_LEDGER_REQUIRES_RECONCILIATION" in report["blockers"]
    assert report["can_auto_convert"] is False


def test_alliance_sponsor_and_consent_require_manual_policy(db_session, user, city):
    db_session.add(models.PlayerWorld(user_id=user.id, world_id=city.world_id, starting_city_id=city.id))
    _paused(city, db_session)
    report = audit_legacy_wonder_transition(db_session, city.world_id)
    assert "ALLIANCE_SPONSOR_POLICY_REQUIRED" in report["blockers"]
    assert "PLAYER_CONSENT_NOT_VERIFIED" in report["blockers"]
    alliance = models.Alliance(name="Present alliance", world_id=city.world_id, leader_id=user.id)
    db_session.add(alliance)
    db_session.flush()
    db_session.add(models.AllianceMember(
        alliance_id=alliance.id, user_id=user.id, rank=3,
    ))
    db_session.commit()
    amended = audit_legacy_wonder_transition(db_session, city.world_id)
    assert "ALLIANCE_SPONSOR_POLICY_REQUIRED" not in amended["blockers"]
    assert "PLAYER_CONSENT_NOT_VERIFIED" in amended["blockers"]
    assert amended["counts"]["alliances"] == 1


def test_legacy_user_link_without_membership_requires_consent(db_session, user, city):
    _paused(city, db_session)
    user.world_id = city.world_id
    db_session.commit()
    report = audit_legacy_wonder_transition(db_session, city.world_id)
    assert report["counts"]["players"] == 0
    assert report["counts"]["legacy_user_links"] == 1
    assert report["counts"]["legacy_user_links_without_membership"] == 1
    assert report["counts"]["owned_cities_without_membership"] == 1
    assert "LEGACY_USER_LINK_WITHOUT_MEMBERSHIP" in report["blockers"]
    assert "OWNED_CITIES_WITHOUT_MEMBERSHIP" in report["blockers"]
    assert "PLAYER_CONSENT_NOT_VERIFIED" in report["blockers"]
    assert "ALLIANCE_SPONSOR_POLICY_REQUIRED" in report["blockers"]


def test_city_membership_in_another_world_does_not_satisfy_legacy_audit(db_session, user, city):
    _paused(city, db_session)
    other_world = models.World(name="Different membership", is_active=False, lifecycle_status="paused")
    db_session.add(other_world)
    db_session.flush()
    db_session.add(models.PlayerWorld(user_id=user.id, world_id=other_world.id))
    db_session.commit()
    report = audit_legacy_wonder_transition(db_session, city.world_id)
    assert report["counts"]["players"] == 0
    assert report["counts"]["owned_cities_without_membership"] == 1
    assert "OWNED_CITIES_WITHOUT_MEMBERSHIP" in report["blockers"]


def test_paused_alliance_v2_is_not_accidentally_reclassified_as_legacy(db_session, city):
    world = _paused(city, db_session)
    world.wonder_rules_version = balance.WONDER_ALLIANCE_RULES
    db_session.commit()
    report = audit_legacy_wonder_transition(db_session, world.id)
    assert "NOT_LEGACY_RULES" in report["blockers"]
    assert report["rules_version"] == balance.WONDER_ALLIANCE_RULES
    assert report["can_auto_convert"] is False
    db_session.refresh(world)
    assert world.wonder_rules_version == "alliance-v2"


def test_world_isolation_and_no_pii(db_session, user, city):
    world = _paused(city, db_session)
    second = models.World(name="Independent legacy", lifecycle_status="paused", is_active=False)
    db_session.add(second)
    db_session.flush()
    foreign_city = models.City(
        name="Private fortress", world_id=second.id, owner_id=user.id, x=0, y=0,
    )
    db_session.add(foreign_city)
    db_session.flush()
    db_session.add(models.Building(city_id=foreign_city.id, name="world_wonder", level=51))
    db_session.add(models.BuildingQueue(
        city_id=foreign_city.id, building_type="world_wonder", target_level=52,
        finish_time=utc_now() + timedelta(hours=1),
    ))
    db_session.commit()
    original = audit_legacy_wonder_transition(db_session, world.id)
    other = audit_legacy_wonder_transition(db_session, second.id)
    assert original["counts"]["wonder_buildings"] == 0
    assert original["counts"]["pending_wonder_queues"] == 0
    assert other["counts"]["wonder_buildings"] == 1
    assert other["counts"]["highest_wonder_level"] == 51
    assert other["counts"]["pending_wonder_queues"] == 1
    serialized = json.dumps(other, sort_keys=True)
    assert "Private fortress" not in serialized
    assert user.username not in serialized
    assert user.email not in serialized


def test_no_flush_or_commit_even_with_pending_session_changes(db_session, city):
    _paused(city, db_session)
    pending = models.City(name="Pending and private", owner_id=city.owner_id,
                          world_id=city.world_id, x=7, y=7)
    db_session.add(pending)
    events = []
    def record_flush(*_args):
        events.append("flush")
    event.listen(db_session, "before_flush", record_flush)
    try:
        report = audit_legacy_wonder_transition(db_session, city.world_id)
    finally:
        event.remove(db_session, "before_flush", record_flush)
    assert events == []
    assert pending.id is None
    assert report["counts"]["cities"] == 1
    assert report["can_auto_convert"] is False
    db_session.rollback()


@pytest.mark.parametrize("invalid", [0, -1, True, False, 1.0, "1", None])
def test_invalid_world_ids_rejected_without_db_effect(db_session, invalid):
    with pytest.raises(ValueError, match="positive integer"):
        audit_legacy_wonder_transition(db_session, invalid)


def test_unknown_world_fails_closed(db_session):
    with pytest.raises(ValueError, match="World not found"):
        audit_legacy_wonder_transition(db_session, 2_000_000_000)


def test_cli_prints_only_read_only_json_and_requires_world_id(db_session, city):
    _paused(city, db_session)
    repo = Path(__file__).resolve().parents[1]
    backend = repo / "batalla_medieval_backend"
    command = [sys.executable, str(repo / "scripts/audit_legacy_wonder.py")]
    missing = subprocess.run(command, cwd=backend, capture_output=True, text=True,
                             env=os.environ.copy(), timeout=15, check=False)
    assert missing.returncode != 0
    assert "--world-id" in missing.stderr
    process = subprocess.run(
        command + ["--world-id", str(city.world_id)],
        cwd=backend, capture_output=True, text=True,
        env=os.environ.copy(), timeout=15, check=False,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["world_id"] == city.world_id
    assert report["can_auto_convert"] is False
    assert "test" not in process.stderr.lower()
