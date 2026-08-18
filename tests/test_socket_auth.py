import pytest

from app.routers.auth import create_access_token
from app.services import socket_manager


def test_socket_token_maps_to_authenticated_user(user):
    token = create_access_token({"sub": user.username})

    assert socket_manager.authenticate_socket_token(token) == user.id


def test_socket_token_rejects_missing_token():
    with pytest.raises(socket_manager.SocketAuthenticationError):
        socket_manager.authenticate_socket_token(None)


def test_socket_token_rejects_invalid_token():
    with pytest.raises(socket_manager.SocketAuthenticationError):
        socket_manager.authenticate_socket_token("not-a-jwt")


def test_socket_token_cannot_select_another_user(user, db_session):
    second_user = type(user)(
        username="attacker-target",
        email="target@example.com",
        hashed_password="placeholder",
    )
    db_session.add(second_user)
    db_session.commit()
    db_session.refresh(second_user)

    token = create_access_token({"sub": user.username})

    authenticated_user_id = socket_manager.authenticate_socket_token(token)
    assert authenticated_user_id == user.id
    assert authenticated_user_id != second_user.id
