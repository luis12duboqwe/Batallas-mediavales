from app import models
from app.routers.auth import create_access_token
from app.services import alliance as alliance_service
from app.services import world_membership


def _headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _world(db_session, name: str) -> models.World:
    world = models.World(
        name=name,
        speed_modifier=1.0,
        resource_modifier=1.0,
        map_size=100,
        is_active=True,
    )
    db_session.add(world)
    db_session.commit()
    db_session.refresh(world)
    return world


def _user(db_session, username: str) -> models.User:
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _join_without_spawn(db_session, user: models.User, world: models.World) -> None:
    if not db_session.query(models.PlayerWorld).filter_by(
        user_id=user.id,
        world_id=world.id,
    ).first():
        db_session.add(models.PlayerWorld(user_id=user.id, world_id=world.id))
        db_session.commit()


def _alliance(
    db_session,
    *,
    world: models.World,
    leader: models.User,
    name: str,
) -> models.Alliance:
    alliance = models.Alliance(
        name=name,
        description="",
        diplomacy="neutral",
        leader_id=leader.id,
        world_id=world.id,
    )
    db_session.add(alliance)
    db_session.flush()
    db_session.add(
        models.AllianceMember(
            alliance_id=alliance.id,
            user_id=leader.id,
            rank=alliance_service.RANK_LEADER,
        )
    )
    db_session.commit()
    db_session.refresh(alliance)
    return alliance


def test_player_can_have_one_different_alliance_per_world(client, db_session, user):
    world_a = db_session.query(models.World).first()
    world_membership.join_world(db_session, user, world_a.id)
    world_b = _world(db_session, "Alliance World B")
    world_membership.join_world(db_session, user, world_b.id)

    alliance_a = _alliance(db_session, world=world_a, leader=user, name="World A Knights")
    alliance_b = _alliance(db_session, world=world_b, leader=user, name="World B Knights")
    headers = _headers(user)

    response_a = client.get(
        "/alliance/",
        params={"world_id": world_a.id},
        headers=headers,
    )
    response_b = client.get(
        "/alliance/",
        params={"world_id": world_b.id},
        headers=headers,
    )

    assert response_a.status_code == 200, response_a.text
    assert response_b.status_code == 200, response_b.text
    assert response_a.json()["id"] == alliance_a.id
    assert response_b.json()["id"] == alliance_b.id


def test_alliance_member_list_requires_auth_and_world_membership(client, db_session, user):
    joined_world = db_session.query(models.World).first()
    world_membership.join_world(db_session, user, joined_world.id)

    foreign_world = _world(db_session, "Foreign Alliance World")
    foreign_leader = _user(db_session, "foreign_alliance_leader")
    _join_without_spawn(db_session, foreign_leader, foreign_world)
    foreign_alliance = _alliance(
        db_session,
        world=foreign_world,
        leader=foreign_leader,
        name="Foreign Alliance",
    )

    unauthenticated = client.get(f"/alliance/{foreign_alliance.id}/members")
    assert unauthenticated.status_code in {401, 403}

    cross_world = client.get(
        f"/alliance/{foreign_alliance.id}/members",
        headers=_headers(user),
    )
    assert cross_world.status_code == 403
    assert cross_world.json()["detail"]["error_code"] == "world_access_denied"


def test_invite_target_must_have_joined_the_alliance_world(client, db_session, user):
    alliance_world = db_session.query(models.World).first()
    world_membership.join_world(db_session, user, alliance_world.id)
    alliance = _alliance(
        db_session,
        world=alliance_world,
        leader=user,
        name="Invite Guards",
    )

    foreign_world = _world(db_session, "Invite Foreign World")
    foreign_player = _user(db_session, "foreign_invitee")
    _join_without_spawn(db_session, foreign_player, foreign_world)

    response = client.post(
        f"/alliance/{alliance.id}/invite",
        json={"user_id": foreign_player.id},
        headers=_headers(user),
    )

    assert response.status_code == 400
    assert "not joined this world" in response.json()["detail"]
    assert db_session.query(models.AllianceInvitation).count() == 0


def test_invitations_cannot_be_read_from_unjoined_world(client, db_session, user):
    joined_world = db_session.query(models.World).first()
    world_membership.join_world(db_session, user, joined_world.id)
    foreign_world = _world(db_session, "Invitation Read Foreign")

    response = client.get(
        "/alliance/invitations",
        params={"world_id": foreign_world.id},
        headers=_headers(user),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "world_access_denied"


def test_diplomacy_request_cannot_target_alliance_in_another_world(
    client,
    db_session,
    user,
):
    world_a = db_session.query(models.World).first()
    world_membership.join_world(db_session, user, world_a.id)
    alliance_a = _alliance(
        db_session,
        world=world_a,
        leader=user,
        name="Diplomats A",
    )

    world_b = _world(db_session, "Diplomacy World B")
    leader_b = _user(db_session, "diplomat_b")
    _join_without_spawn(db_session, leader_b, world_b)
    alliance_b = _alliance(
        db_session,
        world=world_b,
        leader=leader_b,
        name="Diplomats B",
    )

    response = client.post(
        f"/alliance/{alliance_a.id}/diplomacy",
        json={"alliance_target_id": alliance_b.id, "status": "nap"},
        headers=_headers(user),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Diplomacy cannot cross worlds"
    assert db_session.query(models.Diplomacy).count() == 0
