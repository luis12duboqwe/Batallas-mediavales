from app import models
from app.services import balance, barbarian_ai


def _create_barbarian(db_session):
    world = db_session.query(models.World).first()
    city = models.City(
        name="PvE Balance",
        owner_id=None,
        world_id=world.id,
        x=61,
        y=62,
        wood=100.0,
        stone=100.0,
        iron=100.0,
        gold=100.0,
    )
    db_session.add(city)
    db_session.commit()
    db_session.refresh(city)
    return city


def test_barbarian_growth_respects_canonical_storage(monkeypatch, db_session):
    city = _create_barbarian(db_session)
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, balance.STORAGE_BASE_CAPACITY - 5)
    db_session.commit()

    rolls = iter([0.0, 1.0])
    monkeypatch.setattr(barbarian_ai.random, "random", lambda: next(rolls))

    barbarian_ai.process_barbarian_growth(db_session)
    db_session.refresh(city)

    for resource in balance.RESOURCE_FIELDS:
        assert getattr(city, resource) == balance.STORAGE_BASE_CAPACITY


def test_barbarian_recruitment_pays_canonical_unit_cost(monkeypatch, db_session):
    city = _create_barbarian(db_session)
    before = {
        resource: float(getattr(city, resource))
        for resource in balance.RESOURCE_FIELDS
    }

    rolls = iter([1.0, 0.0])
    monkeypatch.setattr(barbarian_ai.random, "random", lambda: next(rolls))

    barbarian_ai.process_barbarian_growth(db_session)
    db_session.refresh(city)

    unit = balance.BARBARIAN_RECRUIT_UNIT
    cost = balance.UNIT_CATALOG[unit]["training_cost"]
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(city, resource) == before[resource] - cost.get(resource, 0.0)

    troop = (
        db_session.query(models.Troop)
        .filter(models.Troop.city_id == city.id, models.Troop.unit_type == unit)
        .one()
    )
    assert troop.quantity == 1
