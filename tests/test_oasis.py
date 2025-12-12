from typing import cast, Any
from sqlalchemy.orm import Session
from app import models
from app.services import world_gen, movement, production
from datetime import timedelta
from app.utils import utc_now

def test_oasis_generation(db_session: Session):
    # Create a world using the service
    world = world_gen.create_world(db_session, name="Oasis World", speed=1.0)
    
    # Check if oases were created
    oases = db_session.query(models.Oasis).filter(models.Oasis.world_id == world.id).all()
    assert len(oases) > 0
    
    # Check properties
    oasis = oases[0]
    assert oasis.resource_type in ["wood", "clay", "iron", "crop"]
    assert oasis.bonus_percent in [25, 50]
    assert isinstance(oasis.troops, dict)

def test_oasis_combat_and_conquest(db_session: Session, user: models.User, city: models.City):
    # Setup
    world = city.world
    
    # Create an Oasis near the city
    oasis = models.Oasis(
        world_id=world.id,
        x=city.x + 1,
        y=city.y + 1,
        resource_type="wood",
        bonus_percent=25,
        troops={"rat": 5} # Weak defense
    )
    db_session.add(oasis)
    db_session.commit()
    
    # Add troops to city
    # We need to add troops manually or via service if available
    # Let's add manually
    t = models.Troop(city_id=city.id, unit_type="heavy_cavalry", quantity=100)
    db_session.add(t)
    
    # Add Hero to user and set status to moving (simulated)
    hero = models.Hero(user_id=user.id, name="Conqueror", attack_points=10, defense_points=0, status="home")
    db_session.add(hero)
    db_session.commit()
    
    # Send attack with Hero
    # Create movement
    move = models.Movement(
        origin_city_id=city.id,
        target_oasis_id=oasis.id,
        world_id=world.id,
        movement_type="attack",
        troops={"heavy_cavalry": 100},
        arrival_time=utc_now() - timedelta(seconds=1), # Already arrived
        status="ongoing"
    )
    db_session.add(move)
    db_session.commit()
    
    # Process movement
    hero.status = "moving"
    db_session.commit()
    
    movement.resolve_due_movements(db_session)
    
    # Check result
    db_session.refresh(oasis)
    db_session.refresh(hero)
    
    # Oasis should be conquered
    assert cast(int, oasis.owner_city_id) == city.id
    assert cast(dict[str, Any], oasis.troops) == {} # Cleared
    
    # Hero should be alive (heavy cavalry vs 5 rats is easy win)
    assert hero.health > 0
    
    # Check report
    report = db_session.query(models.Report).filter(models.Report.city_id == city.id).first()
    assert report is not None
    # Cast to str to satisfy type checker, though content is JSON string in DB
    content_str = str(report.content)
    assert "Oasis Conquistado" in content_str or str(report.report_type) == "battle"

def test_oasis_production_bonus(db_session: Session, city: models.City):
    # Setup
    world = city.world
    
    # Create an owned Oasis
    oasis = models.Oasis(
        world_id=world.id,
        x=city.x + 1,
        y=city.y + 1,
        resource_type="wood",
        bonus_percent=25,
        owner_city_id=city.id
    )
    db_session.add(oasis)
    db_session.commit()
    db_session.refresh(city) # Refresh to load oases
    
    # Calculate production
    prod = production.get_production_per_hour(db_session, city)
    
    # Base wood rate is 15.0
    # Bonus is 25% -> 1.25 multiplier
    # Expected: 15.0 * 1.25 = 18.75
    
    assert prod["wood"] == 15.0 * 1.25
    assert prod["clay"] == 12.0 # No bonus
    assert prod["iron"] == 10.0 # No bonus
