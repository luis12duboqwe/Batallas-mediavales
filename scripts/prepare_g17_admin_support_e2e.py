"""Prepare deterministic BM-0073 Browser G17 fixtures from G16 users."""

from pathlib import Path

from app import models
from app.database import SessionLocal
from app.routers.auth import create_access_token
from app.utils import utc_now

ADMIN_USERNAME = "g16_admin"
PLAYER_USERNAME = "g16_player"
CASE_SUBJECT = "G17 correction request"
CHAT_CONTENT = "G17 moderation target"
TOKEN_PATH = Path("/tmp/g17-admin-token")


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.query(models.User).filter_by(username=ADMIN_USERNAME).one()
        player = db.query(models.User).filter_by(username=PLAYER_USERNAME).one()
        world = (
            db.query(models.World)
            .filter(models.World.lifecycle_status == "open", models.World.is_active.is_(True))
            .order_by(models.World.id.asc())
            .first()
        )
        if world is None:
            raise RuntimeError("No open world available for G17")

        admin.is_admin = True
        admin.admin_role = "admin"
        admin.is_frozen = False
        player.is_frozen = False
        db.add_all([admin, player])

        case = db.query(models.SupportCase).filter_by(
            requester_id=player.id,
            subject=CASE_SUBJECT,
        ).one_or_none()
        if case is None:
            case = models.SupportCase(
                requester_id=player.id,
                world_id=world.id,
                subject=CASE_SUBJECT,
                description="Deterministic support request for the G17 audited journey.",
                status="open",
                priority="normal",
            )
            db.add(case)
        else:
            case.world_id = world.id
            case.status = "open"
            case.priority = "normal"
            case.assigned_to_id = None
            case.resolution = None
            case.resolved_at = None
            case.closed_at = None
        db.flush()

        message = db.query(models.ChatMessage).filter_by(
            user_id=player.id,
            world_id=world.id,
            channel="global",
            content=CHAT_CONTENT,
        ).one_or_none()
        if message is None:
            message = models.ChatMessage(
                user_id=player.id,
                world_id=world.id,
                channel="global",
                content=CHAT_CONTENT,
                timestamp=utc_now(),
            )
            db.add(message)
        message.is_hidden = False
        message.moderation_reason = None
        message.moderated_by_id = None
        message.moderated_at = None
        db.flush()

        db.query(models.Log).filter(
            models.Log.user_id == admin.id,
            models.Log.reason.like("G17%"),
        ).delete(synchronize_session=False)
        db.commit()
        db.refresh(admin)
        db.refresh(case)
        db.refresh(message)

        token = create_access_token({"sub": admin.username, "ver": admin.auth_version})
        TOKEN_PATH.write_text(token)
        print(
            f"prepared-g17:world={world.id}:admin={admin.id}:player={player.id}:"
            f"case={case.id}:chat={message.id}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
