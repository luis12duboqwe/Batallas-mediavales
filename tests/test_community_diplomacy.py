import pytest
from fastapi import HTTPException

from app import models
from app.services import diplomacy


def _alliance(db_session, world, name):
    row = models.Alliance(name=name, world_id=world.id, diplomacy="neutral")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_pending_diplomacy_request_and_accept_are_retry_safe(db_session):
    world = db_session.query(models.World).first()
    alliance_a = _alliance(db_session, world, "Diplomacy A")
    alliance_b = _alliance(db_session, world, "Diplomacy B")

    first = diplomacy.request_relation(
        db_session,
        alliance_a.id,
        alliance_b.id,
        "ally",
    )
    retry = diplomacy.request_relation(
        db_session,
        alliance_a.id,
        alliance_b.id,
        "ally",
    )

    assert first.id == retry.id
    assert retry.status == "pending_ally"
    assert db_session.query(models.Diplomacy).count() == 1

    accepted = diplomacy.accept_relation(db_session, alliance_b.id, first.id)
    accepted_retry = diplomacy.accept_relation(db_session, alliance_b.id, first.id)
    assert accepted.id == accepted_retry.id
    assert accepted_retry.status == "ally"
    assert db_session.query(models.Diplomacy).count() == 1


def test_reverse_pending_request_cannot_create_second_pair(db_session):
    world = db_session.query(models.World).first()
    alliance_a = _alliance(db_session, world, "Reverse A")
    alliance_b = _alliance(db_session, world, "Reverse B")

    diplomacy.request_relation(db_session, alliance_a.id, alliance_b.id, "nap")
    with pytest.raises(HTTPException) as exc:
        diplomacy.request_relation(db_session, alliance_b.id, alliance_a.id, "nap")

    assert exc.value.status_code == 400
    assert db_session.query(models.Diplomacy).count() == 1


def test_only_target_alliance_can_accept_pending_relation(db_session):
    world = db_session.query(models.World).first()
    alliance_a = _alliance(db_session, world, "Accept A")
    alliance_b = _alliance(db_session, world, "Accept B")

    relation = diplomacy.request_relation(db_session, alliance_a.id, alliance_b.id, "nap")
    with pytest.raises(HTTPException) as exc:
        diplomacy.accept_relation(db_session, alliance_a.id, relation.id)
    assert exc.value.status_code == 403

    db_session.refresh(relation)
    assert relation.status == "pending_nap"


def test_war_is_unilateral_and_idempotent(db_session):
    world = db_session.query(models.World).first()
    alliance_a = _alliance(db_session, world, "War A")
    alliance_b = _alliance(db_session, world, "War B")

    relation = diplomacy.request_relation(db_session, alliance_a.id, alliance_b.id, "ally")
    war = diplomacy.request_relation(db_session, alliance_b.id, alliance_a.id, "war")
    retry = diplomacy.request_relation(db_session, alliance_b.id, alliance_a.id, "war")

    assert war.id == relation.id
    assert retry.id == relation.id
    assert retry.status == "war"
    assert db_session.query(models.Diplomacy).count() == 1


def test_diplomacy_never_crosses_worlds(db_session):
    world = db_session.query(models.World).first()
    other_world = models.World(
        name="Diplomacy Other World",
        speed_modifier=1.0,
        resource_modifier=1.0,
    )
    db_session.add(other_world)
    db_session.commit()

    alliance_a = _alliance(db_session, world, "World A")
    alliance_b = _alliance(db_session, other_world, "World B")

    with pytest.raises(HTTPException) as exc:
        diplomacy.request_relation(db_session, alliance_a.id, alliance_b.id, "war")
    assert exc.value.status_code == 400
    assert db_session.query(models.Diplomacy).count() == 0
