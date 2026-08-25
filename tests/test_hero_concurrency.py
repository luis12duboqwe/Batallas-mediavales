import threading
from datetime import timedelta

import pytest

from app import models
from app.database import SessionLocal, engine
from app.services import adventure, hero, hero_rules
from app.utils import utc_now


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Hero/adventure concurrency guarantees require PostgreSQL row locks",
)


def _run_parallel(callbacks):
    barrier = threading.Barrier(len(callbacks))
    results = [None] * len(callbacks)

    def runner(index, callback):
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            results[index] = ("ok", callback(session))
        except Exception as exc:
            session.rollback()
            results[index] = (type(exc).__name__, str(exc))
        finally:
            session.close()

    threads = [
        threading.Thread(target=runner, args=(index, callback))
        for index, callback in enumerate(callbacks)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), "Concurrent hero transaction did not finish"
    return results


def test_concurrent_first_hero_creation_resolves_one_world_scoped_row(db_session, user, city):
    user_id = user.id
    world_id = city.world_id

    def create_once(session):
        return hero.get_hero(session, user_id, world_id).id

    results = _run_parallel([create_once, create_once])

    assert [status for status, _ in results] == ["ok", "ok"]
    hero_ids = [value for _, value in results]
    assert hero_ids[0] == hero_ids[1]
    db_session.expire_all()
    rows = (
        db_session.query(models.Hero)
        .filter_by(user_id=user_id, world_id=world_id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].id == hero_ids[0]
    assert rows[0].city_id == city.id


def test_concurrent_revive_charges_gold_exactly_once(db_session, user, city):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    city.gold = 500.0
    city.last_production = utc_now()
    hero_obj.status = "dead"
    hero_obj.health = 0.0
    db_session.add_all([city, hero_obj])
    db_session.commit()
    hero_id = hero_obj.id

    def revive_once(session):
        loaded = session.query(models.Hero).filter_by(id=hero_id).one()
        revived = hero.revive_hero(session, loaded)
        return {"status": revived.status, "health": float(revived.health)}

    results = _run_parallel([revive_once, revive_once])

    assert [status for status, _ in results].count("ok") == 1
    assert [status for status, _ in results].count("ValueError") == 1
    assert any("not dead" in str(value) for status, value in results if status == "ValueError")

    db_session.expire_all()
    persisted_hero = db_session.query(models.Hero).filter_by(id=hero_id).one()
    persisted_city = db_session.query(models.City).filter_by(id=city.id).one()
    assert persisted_hero.status == "home"
    assert persisted_hero.health == hero_rules.HERO_REVIVE_HEALTH
    assert persisted_city.gold == pytest.approx(
        500.0 - hero_rules.HERO_REVIVE_COST_GOLD,
        abs=0.5,
    )


def test_concurrent_same_slot_equips_leave_exactly_one_item_equipped(db_session, user, city):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero.seed_items(db_session)
    templates = {
        row.name: row for row in db_session.query(models.ItemTemplate).all()
    }
    first = models.HeroItem(
        hero_id=hero_obj.id,
        template_id=templates["Espada de Madera"].id,
        is_equipped=False,
    )
    second = models.HeroItem(
        hero_id=hero_obj.id,
        template_id=templates["Hacha de Guerra"].id,
        is_equipped=False,
    )
    db_session.add_all([first, second])
    db_session.commit()
    hero_id = hero_obj.id
    item_ids = [first.id, second.id]

    def equip(item_id):
        def callback(session):
            loaded = session.query(models.Hero).filter_by(id=hero_id).one()
            hero.equip_item(session, loaded, item_id)
            return item_id

        return callback

    results = _run_parallel([equip(first.id), equip(second.id)])
    assert [status for status, _ in results] == ["ok", "ok"]

    db_session.expire_all()
    items = (
        db_session.query(models.HeroItem)
        .filter(models.HeroItem.id.in_(item_ids))
        .all()
    )
    equipped = [item for item in items if item.is_equipped]
    assert len(equipped) == 1
    assert equipped[0].template.slot == "weapon"


def test_concurrent_adventure_claim_replays_one_persisted_reward(db_session, user, city):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero.seed_items(db_session)
    city.wood = city.stone = city.iron = city.gold = 1000.0
    city.last_production = utc_now()
    hero_obj.status = "adventure"
    hero_obj.health = 100.0
    hero_obj.xp = 0
    hero_obj.level = 1
    adv = models.Adventure(
        hero_id=hero_obj.id,
        difficulty="easy",
        duration=1,
        status="active",
        rules_version=hero_rules.HERO_RULES_VERSION,
        outcome_seed="1" * 64,
        started_at=utc_now() - timedelta(minutes=5),
    )
    db_session.add_all([city, hero_obj, adv])
    db_session.commit()
    adventure_id = adv.id
    hero_id = hero_obj.id
    before_resources = {
        resource: float(getattr(city, resource))
        for resource in ("wood", "stone", "iron", "gold")
    }
    before_items = db_session.query(models.HeroItem).filter_by(hero_id=hero_id).count()

    def claim_once(session):
        loaded = session.query(models.Hero).filter_by(id=hero_id).one()
        return adventure.claim_adventure(session, adventure_id, loaded)

    results = _run_parallel([claim_once, claim_once])

    assert [status for status, _ in results] == ["ok", "ok"]
    first_result = results[0][1]
    second_result = results[1][1]
    assert first_result == second_result
    assert first_result["seed"] == "1" * 64
    assert first_result["rules_version"] == hero_rules.HERO_RULES_VERSION

    db_session.expire_all()
    persisted_adv = db_session.query(models.Adventure).filter_by(id=adventure_id).one()
    persisted_hero = db_session.query(models.Hero).filter_by(id=hero_id).one()
    persisted_city = db_session.query(models.City).filter_by(id=city.id).one()
    after_items = db_session.query(models.HeroItem).filter_by(hero_id=hero_id).count()

    assert persisted_adv.result == first_result
    assert persisted_adv.status in {"completed", "failed"}
    assert persisted_adv.completed_at is not None
    assert persisted_hero.status in {"home", "dead"}

    if first_result["status"] == "success":
        assert persisted_hero.xp == first_result["xp"]
    else:
        assert first_result["xp"] == 0
        assert persisted_hero.xp == 0

    loot = first_result.get("loot")
    if loot and loot.get("type") == "item":
        assert after_items == before_items + 1
    else:
        assert after_items == before_items

    for resource, before in before_resources.items():
        delta = float(getattr(persisted_city, resource)) - before
        if loot and loot.get("type") == "resource" and loot.get("resource") == resource:
            assert delta == pytest.approx(float(loot["amount"]), abs=0.5)
        else:
            assert delta == pytest.approx(0.0, abs=0.5)
