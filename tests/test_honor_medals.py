import pytest

from app import models
from app.services import achievement
from app.services import movement as movement_service


def _medal(db_session, *, requirement_type="build_level", requirement_value=1):
    medal = models.Achievement(
        title="Honor de prueba",
        description="Reconocimiento sin ventaja jugable",
        category="honor",
        requirement_type=requirement_type,
        requirement_value=requirement_value,
        reward_type="resources",
        reward_value="999999",
    )
    db_session.add(medal)
    db_session.commit()
    db_session.refresh(medal)
    return medal


def _ensure_membership(db_session, user_id: int, world_id: int) -> None:
    if (
        db_session.query(models.PlayerWorld)
        .filter_by(user_id=user_id, world_id=world_id)
        .one_or_none()
        is None
    ):
        db_session.add(models.PlayerWorld(user_id=user_id, world_id=world_id))
        db_session.commit()


def test_claim_honor_medal_does_not_change_gameplay_state(db_session, user, city):
    _ensure_membership(db_session, user.id, city.world_id)
    medal = _medal(db_session)
    troop = models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=7)
    db_session.add(troop)
    db_session.commit()

    achievement.update_achievement_progress(
        db_session,
        user.id,
        city.world_id,
        "build_level",
        absolute_value=1,
    )
    progress = (
        db_session.query(models.AchievementProgress)
        .filter_by(user_id=user.id, achievement_id=medal.id, world_id=city.world_id)
        .one()
    )
    assert progress.status == "completed"

    resources_before = tuple(
        float(getattr(city, name)) for name in ("wood", "stone", "iron", "gold")
    )
    troop_before = troop.quantity
    population_before = city.population_max

    claimed = achievement.claim_achievement(db_session, user, city.world_id, medal.id)
    db_session.refresh(city)
    db_session.refresh(troop)

    assert claimed.status == "claimed"
    assert tuple(float(getattr(city, name)) for name in ("wood", "stone", "iron", "gold")) == resources_before
    assert troop.quantity == troop_before
    assert city.population_max == population_before
    assert (
        db_session.query(models.Log)
        .filter_by(user_id=user.id, action="claim_honor_medal")
        .count()
        == 1
    )


def test_honor_progress_is_isolated_per_world(db_session, user, city):
    _ensure_membership(db_session, user.id, city.world_id)
    medal = _medal(db_session, requirement_type="train_troops", requirement_value=2)
    second_world = models.World(
        name="Honor Isolation World",
        speed_modifier=1.0,
        resource_modifier=1.0,
    )
    db_session.add(second_world)
    db_session.flush()
    db_session.add(models.PlayerWorld(user_id=user.id, world_id=second_world.id))
    db_session.commit()

    achievement.update_achievement_progress(
        db_session,
        user.id,
        city.world_id,
        "train_troops",
        increment=2,
    )

    world_one = achievement.get_user_achievements(db_session, user, city.world_id)
    world_two = achievement.get_user_achievements(db_session, user, second_world.id)
    progress_one = next(progress for item, progress in world_one if item.id == medal.id)
    progress_two = next(progress for item, progress in world_two if item.id == medal.id)

    assert progress_one.status == "completed"
    assert progress_one.current_progress == 2
    assert progress_two.status == "pending"
    assert progress_two.current_progress == 0


def test_legacy_medal_event_rejects_ambiguous_multiworld_user(db_session, user, city):
    _ensure_membership(db_session, user.id, city.world_id)
    _medal(db_session, requirement_type="join_alliance", requirement_value=1)
    second_world = models.World(
        name="Ambiguous Honor World",
        speed_modifier=1.0,
        resource_modifier=1.0,
    )
    db_session.add(second_world)
    db_session.flush()
    db_session.add(models.PlayerWorld(user_id=user.id, world_id=second_world.id))
    db_session.commit()

    with pytest.raises(ValueError, match="explicit world_id"):
        achievement.update_achievement_progress(
            db_session,
            user.id,
            "join_alliance",
            absolute_value=1,
        )


def test_battle_medal_effect_uses_explicit_movement_world(db_session, user, city):
    _ensure_membership(db_session, user.id, city.world_id)
    medal = _medal(db_session, requirement_type="win_battles", requirement_value=1)
    second_world = models.World(
        name="Battle Honor Isolation World",
        speed_modifier=1.0,
        resource_modifier=1.0,
    )
    db_session.add(second_world)
    db_session.flush()
    db_session.add(models.PlayerWorld(user_id=user.id, world_id=second_world.id))
    db_session.commit()

    movement_service._run_resolution_effect(
        db_session,
        {
            "type": "achievement",
            "user_id": user.id,
            "world_id": city.world_id,
            "requirement_type": "win_battles",
            "increment": 1,
        },
    )

    scoped = (
        db_session.query(models.AchievementProgress)
        .filter_by(
            user_id=user.id,
            achievement_id=medal.id,
            world_id=city.world_id,
        )
        .one()
    )
    assert scoped.status == "completed"
    assert scoped.current_progress == 1
    assert (
        db_session.query(models.AchievementProgress)
        .filter_by(
            user_id=user.id,
            achievement_id=medal.id,
            world_id=second_world.id,
        )
        .count()
        == 0
    )
