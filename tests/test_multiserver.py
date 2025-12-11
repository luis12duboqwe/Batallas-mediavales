from app import models
from app.services import ranking


def test_multiworld_ranking_scoped(db_session, user):
    world_two = models.World(name="World2", speed_modifier=1.0, resource_modifier=1.0)
    db_session.add(world_two)
    db_session.commit()

    city_one = models.City(name="Home", owner_id=user.id, world_id=1, x=0, y=0)
    city_two = models.City(name="Away", owner_id=user.id, world_id=world_two.id, x=1, y=1)
    db_session.add_all([city_one, city_two])
    db_session.commit()

    db_session.add(models.Building(city_id=city_one.id, name="town_hall", level=5))
    db_session.add(models.Building(city_id=city_two.id, name="town_hall", level=1))
    db_session.commit()

    ranking_world1 = ranking.get_player_ranking(db_session, 1)
    ranking_world2 = ranking.get_player_ranking(db_session, world_two.id)

    assert ranking_world1[0]["points"] != ranking_world2[0]["points"]
