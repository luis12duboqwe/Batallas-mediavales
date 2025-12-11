from app import models
from app.services import movement


def test_send_movement_same_world(db_session, city, second_city):
    spy_troop = models.Troop(city_id=city.id, unit_type="spy", quantity=2)
    db_session.add(spy_troop)
    db_session.commit()

    movement_obj = movement.send_movement(db_session, city, second_city.id, "spy", spy_count=1)
    assert movement_obj.target_city_id == second_city.id
    assert movement_obj.world_id == city.world_id
    assert movement_obj.arrival_time > movement_obj.created_at


def test_send_movement_cross_world_error(db_session, city, second_city):
    second_city.world_id = city.world_id + 1
    db_session.commit()
    try:
        movement.send_movement(db_session, city, second_city.id, "attack")
    except ValueError as exc:
        assert "not in the same world" in str(exc)
    else:
        raise AssertionError("Movement should fail for cross-world targets")
