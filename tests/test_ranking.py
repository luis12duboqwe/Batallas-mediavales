from app import models
from app.services import ranking


def test_ranking_sorts_by_points(db_session, city, second_city):
    world_id = city.world_id
    city_building = models.Building(city_id=city.id, name="town_hall", level=3)
    troop = models.Troop(city_id=second_city.id, unit_type="heavy_infantry", quantity=5)
    db_session.add_all([city_building, troop])
    db_session.commit()

    entries = ranking.get_player_ranking(db_session, world_id)
    assert entries
    assert entries[0]["points"] >= entries[-1]["points"]
