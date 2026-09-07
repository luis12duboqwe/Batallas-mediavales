from app import models
from app.services import season as season_service


def test_end_season_preserves_live_state_and_other_world(db_session, user, city):
    target_world = city.world
    target_world_id = target_world.id

    # Ensure the target world has live state whose accidental deletion would be
    # immediately visible to this regression.
    building = models.Building(city_id=city.id, name="town_hall", level=3)
    troop = models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=7)
    audit = models.Log(user_id=user.id, action="bm0073-season-sentinel", details="{}")
    db_session.add_all([building, troop, audit])

    other_world = models.World(
        name="BM0073 season isolation world",
        speed_modifier=1.0,
        resource_modifier=1.0,
        is_active=True,
        lifecycle_status="open",
        map_size=100,
    )
    other_user = models.User(
        username="bm0073_season_other",
        email="bm0073-season-other@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add_all([other_world, other_user])
    db_session.flush()
    other_city = models.City(
        name="Other world city",
        x=11,
        y=11,
        owner_id=other_user.id,
        world_id=other_world.id,
        wood=100,
        stone=100,
        iron=100,
        gold=100,
        population_max=100,
    )
    db_session.add(other_city)
    db_session.commit()

    season = season_service.start_new_season(
        db_session,
        str(target_world_id),
        "BM0073 safe season",
    )
    results = season_service.end_current_season(db_session, str(target_world_id))

    db_session.expire_all()
    persisted_season = db_session.query(models.Season).filter_by(id=season.id).one()
    assert persisted_season.is_active is False
    assert persisted_season.end_date is not None

    # Closing a season is a historical snapshot, not a data-reset operation.
    assert db_session.query(models.City).filter_by(id=city.id).one_or_none() is not None
    assert db_session.query(models.Building).filter_by(id=building.id).one_or_none() is not None
    assert db_session.query(models.Troop).filter_by(id=troop.id).one_or_none() is not None
    assert db_session.query(models.Log).filter_by(id=audit.id).one_or_none() is not None
    assert db_session.query(models.City).filter_by(id=other_city.id).one_or_none() is not None

    result_user_ids = {result.user_id for result in results}
    assert user.id in result_user_ids
    assert other_user.id not in result_user_ids
