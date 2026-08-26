"""Prepare deterministic BM-0070 community/diplomacy Browser G14 fixtures."""

from __future__ import annotations

from datetime import timedelta

from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import tutorial, world_membership
from app.utils import utc_now


PASSWORD = "G14-Community-Test-2026!"
USERS = (
    ("g14_leader", "g14-leader@example.com"),
    ("g14_member", "g14-member@example.com"),
    ("g14_rival", "g14-rival@example.com"),
)
ALLIANCE_A = "G14 Guardianes"
ALLIANCE_B = "G14 Cuervos"


def _user(db, username: str, email: str) -> models.User:
    row = db.query(models.User).filter_by(username=username).one_or_none()
    if row is None:
        row = models.User(
            username=username,
            email=email,
            hashed_password=get_password_hash(PASSWORD),
            is_verified=True,
            protection_ends_at=utc_now() - timedelta(hours=1),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    else:
        row.email = email
        row.hashed_password = get_password_hash(PASSWORD)
        row.is_verified = True
        row.protection_ends_at = utc_now() - timedelta(hours=1)
        db.add(row)
        db.commit()
    return row


def _reset_social_rows(db, users: list[models.User], world_id: int) -> None:
    user_ids = [user.id for user in users]
    alliance_ids = [
        row.id
        for row in db.query(models.Alliance.id)
        .filter(
            models.Alliance.world_id == world_id,
            models.Alliance.name.in_([ALLIANCE_A, ALLIANCE_B]),
        )
        .all()
    ]

    if alliance_ids:
        thread_ids = [
            row.id
            for row in db.query(models.ForumThread.id)
            .filter(models.ForumThread.alliance_id.in_(alliance_ids))
            .all()
        ]
        if thread_ids:
            db.query(models.ForumPost).filter(models.ForumPost.thread_id.in_(thread_ids)).delete(
                synchronize_session=False
            )
            db.query(models.ForumThread).filter(models.ForumThread.id.in_(thread_ids)).delete(
                synchronize_session=False
            )
        db.query(models.ChatMessage).filter(models.ChatMessage.alliance_id.in_(alliance_ids)).delete(
            synchronize_session=False
        )
        db.query(models.AllianceChatMessage).filter(
            models.AllianceChatMessage.alliance_id.in_(alliance_ids)
        ).delete(synchronize_session=False)
        db.query(models.AllianceInvitation).filter(
            models.AllianceInvitation.alliance_id.in_(alliance_ids)
        ).delete(synchronize_session=False)
        db.query(models.Diplomacy).filter(
            (models.Diplomacy.alliance_a_id.in_(alliance_ids))
            | (models.Diplomacy.alliance_b_id.in_(alliance_ids))
        ).delete(synchronize_session=False)
        db.query(models.AllianceMember).filter(
            models.AllianceMember.alliance_id.in_(alliance_ids)
        ).delete(synchronize_session=False)
        db.query(models.Alliance).filter(models.Alliance.id.in_(alliance_ids)).delete(
            synchronize_session=False
        )

    db.query(models.UserBlock).filter(
        models.UserBlock.world_id == world_id,
        (models.UserBlock.blocker_id.in_(user_ids)) | (models.UserBlock.blocked_id.in_(user_ids)),
    ).delete(synchronize_session=False)
    db.query(models.ChatMessage).filter(
        models.ChatMessage.world_id == world_id,
        (models.ChatMessage.user_id.in_(user_ids)) | (models.ChatMessage.receiver_id.in_(user_ids)),
    ).delete(synchronize_session=False)
    db.query(models.Message).filter(
        models.Message.world_id == world_id,
        (models.Message.sender_id.in_(user_ids)) | (models.Message.receiver_id.in_(user_ids)),
    ).delete(synchronize_session=False)
    db.commit()


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

        users = [_user(db, username, email) for username, email in USERS]
        for user in users:
            world_membership.join_world(db, user, world.id)
            user.world_id = world.id
            user.tutorial_step = tutorial.FINAL_STEP
            user.tutorial_reward_claimed = True
            db.add(user)
        db.commit()

        _reset_social_rows(db, users, world.id)
        leader, member, rival = users

        alliance_a = models.Alliance(
            name=ALLIANCE_A,
            description="Fixture G14 principal",
            diplomacy="neutral",
            leader_id=leader.id,
            world_id=world.id,
        )
        alliance_b = models.Alliance(
            name=ALLIANCE_B,
            description="Fixture G14 rival",
            diplomacy="neutral",
            leader_id=rival.id,
            world_id=world.id,
        )
        db.add_all([alliance_a, alliance_b])
        db.flush()
        leader_membership = models.AllianceMember(
            alliance_id=alliance_a.id,
            user_id=leader.id,
            rank=3,
        )
        member_membership = models.AllianceMember(
            alliance_id=alliance_a.id,
            user_id=member.id,
            rank=1,
        )
        rival_membership = models.AllianceMember(
            alliance_id=alliance_b.id,
            user_id=rival.id,
            rank=3,
        )
        db.add_all([leader_membership, member_membership, rival_membership])
        db.commit()

        if db.query(models.AllianceMember).filter_by(alliance_id=alliance_a.id).count() != 2:
            raise RuntimeError("G14 primary alliance membership precondition mismatch")
        if db.query(models.AllianceMember).filter_by(alliance_id=alliance_b.id).count() != 1:
            raise RuntimeError("G14 rival alliance membership precondition mismatch")

        print(
            "prepared-g14:"
            f"world={world.id}:leader={leader.id}:member={member.id}:rival={rival.id}:"
            f"alliance_a={alliance_a.id}:alliance_b={alliance_b.id}:"
            f"member_row={member_membership.id}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
