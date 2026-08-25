from app.services import balance, barbarian_ai, pve


def test_barbarian_ai_entrypoint_delegates_to_versioned_pve(monkeypatch, db_session):
    expected = {
        "worlds_processed": 1,
        "barbarians_regenerated": 8,
        "oases_regenerated": 20,
        "tick_bucket": 123,
    }
    calls = []

    def fake_tick(db):
        calls.append(db)
        return expected

    monkeypatch.setattr(pve, "process_pve_tick", fake_tick)
    assert barbarian_ai.process_barbarian_growth(db_session) == expected
    assert calls == [db_session]


def test_barbarian_profiles_only_use_canonical_balance_content():
    assert set(pve.BARBARIAN_PROFILES) == set(pve.PVE_TIERS)
    for profile in pve.BARBARIAN_PROFILES.values():
        assert set(profile["resources"]) == set(balance.RESOURCE_FIELDS)
        assert profile["resource_regen"] > 0
        assert set(profile["buildings"]).issubset(set(balance.BUILDING_ORDER))
        assert set(profile["troops"]).issubset(balance.UNIT_CATALOG)
        assert all(quantity > 0 for quantity in profile["troops"].values())
