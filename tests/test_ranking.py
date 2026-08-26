from app import models
from app.services import ranking


def test_ranking_sorts_by_points_and_exposes_position(db_session, city, second_city):
    world_id = city.world_id
    city_building = models.Building(city_id=city.id, name="town_hall", level=3)
    troop = models.Troop(city_id=second_city.id, unit_type="heavy_infantry", quantity=5)
    db_session.add_all([city_building, troop])
    db_session.commit()

    entries = ranking.get_player_ranking(db_session, world_id)
    assert entries
    assert entries[0]["points"] >= entries[-1]["points"]
    assert [entry["rank"] for entry in entries] == list(range(1, len(entries) + 1))
    assert all("attacker_points" not in entry for entry in entries)
    assert all("defender_points" not in entry for entry in entries)


def test_player_ranking_uses_stable_tiebreaker(db_session, city, second_city):
    world_id = city.world_id
    city.owner.username = "zulu"
    second_city.owner.username = "Alpha"
    db_session.add_all([city.owner, second_city.owner])
    db_session.commit()

    first = ranking.get_player_ranking(db_session, world_id)
    second = ranking.get_player_ranking(db_session, world_id)

    assert [entry["user_id"] for entry in first] == [entry["user_id"] for entry in second]
    tied = [entry for entry in first if entry["points"] == 0]
    if len(tied) >= 2:
        assert [entry["username"] for entry in tied[:2]] == ["Alpha", "zulu"]


def test_ranking_is_world_scoped(db_session, city, second_city):
    world = models.World(name="Ranking isolated world", speed_modifier=1.0, resource_modifier=1.0)
    db_session.add(world)
    db_session.flush()
    isolated_city = models.City(
        name="Isolated ranking city",
        owner_id=city.owner_id,
        world_id=world.id,
        x=101,
        y=101,
    )
    db_session.add(isolated_city)
    db_session.flush()
    db_session.add(models.Building(city_id=isolated_city.id, name="town_hall", level=99))
    db_session.commit()

    original_world_entries = ranking.get_player_ranking(db_session, city.world_id)
    isolated_world_entries = ranking.get_player_ranking(db_session, world.id)

    original_entry = next(entry for entry in original_world_entries if entry["user_id"] == city.owner_id)
    isolated_entry = next(entry for entry in isolated_world_entries if entry["user_id"] == city.owner_id)
    assert isolated_entry["points"] > original_entry["points"]
    assert isolated_entry["world_id"] == world.id
    assert original_entry["world_id"] == city.world_id
