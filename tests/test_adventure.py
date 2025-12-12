import pytest
from app import models, schemas
from app.services import adventure, hero

def test_adventure_flow(db_session, user):
    # Setup hero
    hero_obj = hero.get_hero(db_session, user.id)
    assert hero_obj is not None
    
    # Seed items
    hero.seed_items(db_session)
    
    # Get adventures (should generate)
    adventures = adventure.get_adventures(db_session, hero_obj.id)
    assert len(adventures) == 3
    assert adventures[0].status == "available"
    
    # Start adventure
    adv = adventures[0]
    adventure.start_adventure(db_session, adv.id, hero_obj)
    
    assert adv.status == "active"
    assert hero_obj.status == "adventure"
    assert adv.started_at is not None
    
    # Try to claim too early
    with pytest.raises(ValueError, match="Adventure not finished yet"):
        adventure.claim_adventure(db_session, adv.id, hero_obj)
        
    # Fast forward time (hack: modify started_at)
    from datetime import timedelta
    adv.started_at -= timedelta(seconds=adv.duration + 1)
    db_session.commit()
    
    # Claim
    result = adventure.claim_adventure(db_session, adv.id, hero_obj)
    assert result["status"] == "success"
    assert adv.status == "completed"
    assert hero_obj.status == "home"
    assert hero_obj.xp > 0
    
    # Check if loot works (might be None, but function shouldn't crash)
    if result["loot"]:
        assert "type" in result["loot"]

