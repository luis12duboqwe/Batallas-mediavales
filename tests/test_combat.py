from app import models
from app.services import combat


def test_combat_resolution_balances_losses(monkeypatch, db_session, city, second_city):
    attacker_troop = models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=20)
    defender_troop = models.Troop(city_id=second_city.id, unit_type="basic_infantry", quantity=10)
    db_session.add_all([attacker_troop, defender_troop])
    db_session.commit()

    def zero_luck():
        return 0

    monkeypatch.setattr(combat, "_luck", zero_luck)
    result = combat.resolve_battle(city, second_city, {"basic_infantry": 20})
    assert result["attacker_losses"]["basic_infantry"] >= 0
    assert result["defender_losses"]["basic_infantry"] >= 0
    assert "loot" in result
