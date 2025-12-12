from app import models
from app.services import premium


def test_premium_purchase_flow(db_session, user):
    status = premium.grant_rubies(db_session, user, 500)
    assert status.rubies_balance >= 500
    initial_balance = status.rubies_balance

    updated = premium.buy_feature(db_session, user, "second_build_queue")
    assert updated.second_build_queue is True
    assert updated.rubies_balance < initial_balance

    limit = premium.get_build_queue_limit(updated)
    assert limit == 2
