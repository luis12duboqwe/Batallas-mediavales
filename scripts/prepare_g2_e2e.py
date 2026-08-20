"""Prepare deterministic local data for the G2 browser smoke test."""

from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import world_membership


USERNAME = "g2_browser"
PASSWORD = "G2-Browser-Test-2026!"
EMAIL = "g2-browser@example.com"


def main() -> None:
    db = SessionLocal()
    try:
        world = (
            db.query(models.World)
            .filter(models.World.is_active.is_(True))
            .order_by(models.World.id.asc())
            .first()
        )
        if world is None:
            raise RuntimeError("Canonical seed did not create an active world")

        user = db.query(models.User).filter_by(username=USERNAME).one_or_none()
        if user is None:
            user = models.User(
                username=USERNAME,
                email=EMAIL,
                hashed_password=get_password_hash(PASSWORD),
                is_verified=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.email = EMAIL
            user.hashed_password = get_password_hash(PASSWORD)
            user.is_verified = True
            db.add(user)
            db.commit()

        world_membership.join_world(db, user, world.id)
        print(f"prepared:{USERNAME}:{world.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
