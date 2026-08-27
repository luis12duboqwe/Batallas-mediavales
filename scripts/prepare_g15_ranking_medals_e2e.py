"""Prepare deterministic BM-0071 ranking/honor-medal Browser G15 fixtures."""

from __future__ import annotations

from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import production, tutorial, world_membership
from app.utils import utc_now

PASSWORD = "G15-Ranking-Test-2026!"
USERS = (
    ("g15_alpha", "g15-alpha@example.com"),
    ("g15_beta", "g15-beta@example.com"),
)
MEDAL_TITLE = "G15 Honor sin ventaja"
G15_TIE_LEVEL = 1_000_000


def _user(db, username: str, email: str) -> models.User:
    row = db.query(models.User).filter_by(username=username).one_or_none()
    if row is None:
        row = models.User(
            username=username,
            email=email,
            hashed_password=get_password_hash(PASSWORD),
            is_verified=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    else:
        row.email = email
        row.hashed_password = get_password_hash(PASSWORD)
        row.is_verified = True
        db.add(row)
        db.commit()
    return row


def main() -> None:
    db = SessionLocal()
    try:
        world = db.query(models.World).filter(models.World.is_active.is_(True)).order_by(models.World.id.asc()).first()
        if world is None:
            raise RuntimeError("Canonical seed did not create an active world")

        users = [_user(db, username, email) for username, email in USERS]
        for user in users:
            membership = world_membership.join_world(db, user, world.id)
            user.world_id = world.id
            user.tutorial_step = tutorial.FINAL_STEP
            user.tutorial_reward_claimed = True
            db.add(user)
            city = db.query(models.City).filter(models.City.id == membership.starting_city_id).one()
            db.query(models.Building).filter(models.Building.city_id == city.id).delete(synchronize_session=False)
            db.query(models.Troop).filter(models.Troop.city_id == city.id).delete(synchronize_session=False)
            db.flush()
            # Give both fixture players the same score far above ordinary seeded
            # progress. The assertion then exercises only the deterministic
            # username/id tiebreaker, not assumptions about older G2-G14 users.
            db.add(models.Building(city_id=city.id, name="town_hall", level=G15_TIE_LEVEL))
            storage_cap = float(production.get_storage_limit(city))
            city.wood = storage_cap
            city.stone = storage_cap
            city.iron = storage_cap
            city.gold = storage_cap
            city.last_production = utc_now()
            db.add(city)
        db.commit()

        medal = db.query(models.Achievement).filter(models.Achievement.title == MEDAL_TITLE).one_or_none()
        if medal is None:
            medal = models.Achievement(
                title=MEDAL_TITLE,
                description="Reconocimiento G15 que no entrega ninguna ventaja jugable.",
                category="honor",
                requirement_type="g15_honor",
                requirement_value=1,
                reward_type="resources",
                reward_value="999999",
            )
            db.add(medal)
            db.flush()
        else:
            medal.description = "Reconocimiento G15 que no entrega ninguna ventaja jugable."
            medal.category = "honor"
            medal.requirement_type = "g15_honor"
            medal.requirement_value = 1
            medal.reward_type = "resources"
            medal.reward_value = "999999"

        alpha = users[0]
        db.query(models.AchievementProgress).filter(
            models.AchievementProgress.user_id.in_([user.id for user in users]),
            models.AchievementProgress.achievement_id == medal.id,
            models.AchievementProgress.world_id == world.id,
        ).delete(synchronize_session=False)
        db.add(models.AchievementProgress(
            user_id=alpha.id,
            achievement_id=medal.id,
            world_id=world.id,
            current_progress=1,
            status="completed",
        ))
        db.commit()
        print(f"prepared-g15:world={world.id}:alpha={alpha.id}:beta={users[1].id}:medal={medal.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
