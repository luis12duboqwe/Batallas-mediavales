import pytest

from app.routers.auth import create_access_token
from app.services import socket_manager


def access_token_for(user):
    return create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )


def test_socket_token_maps_to_authenticated_user(user):
    assert socket_manager.authenticate_socket_token(access_token_for(user)) == user.id


def test_socket_token_rejects_missing_token():
    with pytest.raises(socket_manager.SocketAuthenticationError):
        socket_manager.authenticate_socket_token(None)


def test_socket_token_rejects_invalid_token():
    with pytest.raises(socket_manager.SocketAuthenticationError):
        socket_manager.authenticate_socket_token("not-a-jwt")


def test_socket_token_rejects_wrong_purpose(user):
    reset_token = create_access_token(
        {"sub": user.username, "type": "reset", "ver": user.auth_version}
    )
    with pytest.raises(socket_manager.SocketAuthenticationError):
        socket_manager.authenticate_socket_token(reset_token)


def test_socket_token_rejects_stale_session(user, db_session):
    token = access_token_for(user)
    user.auth_version += 1
    db_session.commit()

    with pytest.raises(socket_manager.SocketAuthenticationError):
        socket_manager.authenticate_socket_token(token)


def test_socket_token_cannot_select_another_user(user, db_session):
    second_user = type(user)(
        username="attacker-target",
        email="target@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(second_user)
    db_session.commit()
    db_session.refresh(second_user)

    authenticated_user_id = socket_manager.authenticate_socket_token(access_token_for(user))
    assert authenticated_user_id == user.id
    assert authenticated_user_id != second_user.id
