from app import models
from app.services import alliance


def test_alliance_join_leave_promote(db_session, user):
    world = db_session.query(models.World).first()
    membership_record = models.PlayerWorld(user_id=user.id, world_id=world.id)
    db_session.add(membership_record)
    db_session.commit()

    payload = models.Alliance(name="Knights", description="", diplomacy="neutral", leader_id=user.id, world_id=world.id)
    db_session.add(payload)
    db_session.commit()
    db_session.refresh(payload)

    leader_member = models.AllianceMember(alliance_id=payload.id, user_id=user.id, rank=2)
    db_session.add(leader_member)
    db_session.commit()

    new_user = models.User(username="ally", email="ally@example.com", hashed_password="")
    db_session.add(new_user)
    db_session.commit()
    db_session.refresh(new_user)

    invite = alliance.invite_member(db_session, payload.id, user, new_user.id)
    membership = alliance.accept_invitation(db_session, invite.id, new_user)
    assert membership.alliance_id == payload.id

    promoted = alliance.promote_member(db_session, payload.id, user, membership.id)
    assert promoted.rank > membership.rank - 1

    alliance.leave_alliance(db_session, new_user)
    assert db_session.query(models.AllianceMember).filter_by(user_id=new_user.id).first() is None
