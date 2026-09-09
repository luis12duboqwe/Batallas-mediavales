"""Prepare deterministic BM-0074 Browser G18 anti-cheat fixtures."""

from pathlib import Path

from fastapi import HTTPException

from app import models
from app.database import SessionLocal
from app.routers.auth import create_access_token
from app.services import anticheat

ADMIN_USERNAME = "g18_admin"
PLAYER_USERNAME = "g18_player"
ACTION_KEY = "g18.browser"
ADMIN_TOKEN_PATH = Path("/tmp/g18-admin-token")
PLAYER_TOKEN_PATH = Path("/tmp/g18-player-token")


def _get_or_create_user(db, username: str, *, admin: bool = False) -> models.User:
    user = db.query(models.User).filter_by(username=username).one_or_none()
    if user is None:
        user = models.User(
            username=username,
            email=f"{username}@example.com",
            hashed_password="placeholder",
            is_verified=True,
        )
        db.add(user)
        db.flush()
    user.is_admin = admin
    user.admin_role = "admin" if admin else None
    user.is_frozen = False
    user.freeze_reason = None
    db.add(user)
    return user


def main() -> None:
    db = SessionLocal()
    try:
        admin = _get_or_create_user(db, ADMIN_USERNAME, admin=True)
        player = _get_or_create_user(db, PLAYER_USERNAME)
        db.flush()

        db.query(models.AntiCheatFlag).filter(
            models.AntiCheatFlag.user_id == player.id,
            models.AntiCheatFlag.type_of_violation == f"rate_limit:{ACTION_KEY}",
        ).delete(synchronize_session=False)
        db.query(models.AntiCheatRateBucket).filter(
            models.AntiCheatRateBucket.user_id == player.id,
            models.AntiCheatRateBucket.action_key == ACTION_KEY,
        ).delete(synchronize_session=False)
        db.commit()
        db.refresh(admin)
        db.refresh(player)

        anticheat.enforce_action_rate_limit(
            db,
            player,
            ACTION_KEY,
            limit=1,
            window_seconds=60,
        )
        try:
            anticheat.enforce_action_rate_limit(
                db,
                player,
                ACTION_KEY,
                limit=1,
                window_seconds=60,
            )
        except HTTPException as exc:
            if exc.status_code != 429:
                raise
        else:
            raise RuntimeError("G18 fixture did not trigger the expected 429")

        db.expire_all()
        player = db.query(models.User).filter_by(username=PLAYER_USERNAME).one()
        admin = db.query(models.User).filter_by(username=ADMIN_USERNAME).one()
        flag = (
            db.query(models.AntiCheatFlag)
            .filter_by(
                user_id=player.id,
                type_of_violation=f"rate_limit:{ACTION_KEY}",
            )
            .one()
        )
        if player.is_frozen:
            raise RuntimeError("Detection sanctioned G18 player automatically")

        ADMIN_TOKEN_PATH.write_text(
            create_access_token({"sub": admin.username, "ver": admin.auth_version})
        )
        PLAYER_TOKEN_PATH.write_text(
            create_access_token({"sub": player.username, "ver": player.auth_version})
        )
        print(
            f"prepared-g18:admin={admin.id}:player={player.id}:flag={flag.id}:"
            f"action={ACTION_KEY}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
