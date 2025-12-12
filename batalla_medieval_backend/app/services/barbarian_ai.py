import logging
import random
from sqlalchemy.orm import Session
from .. import models

logger = logging.getLogger(__name__)

def process_barbarian_growth(db: Session):
    """
    Iterate over barbarian cities (owner_id=None) and simulate growth.
    - Increase resources slightly (if not full).
    - Occasionally recruit basic troops.
    - Occasionally upgrade a building (rarely).
    """
    # Get all barbarian cities
    # Limit to a batch to avoid locking DB for too long if there are many
    barbarian_cities = db.query(models.City).filter(models.City.owner_id.is_(None)).limit(50).all()
    
    for city in barbarian_cities:
        # 1. Resource Growth (already handled by production service on access, but we can boost it)
        # Barbarians don't have "production" calculated often, so let's just add flat amounts
        # or rely on the standard production.recalculate_resources if we call it.
        # Let's just add a small flat amount to simulate "finding" resources.
        if random.random() < 0.1: # 10% chance per tick
            city.wood = min(city.wood + 10, 5000)
            city.clay = min(city.clay + 10, 5000)
            city.iron = min(city.iron + 10, 5000)
            
        # 2. Recruit Troops
        # Barbarians recruit basic infantry to defend themselves
        if random.random() < 0.05: # 5% chance
            # Check if they have resources (cheating a bit, they just spawn them)
            # Or we can deduct resources. Let's deduct.
            cost_wood = 50
            cost_clay = 30
            cost_iron = 10
            if city.wood >= cost_wood and city.clay >= cost_clay and city.iron >= cost_iron:
                city.wood -= cost_wood
                city.clay -= cost_clay
                city.iron -= cost_iron
                
                # Add troop
                # Check if troop record exists
                troop = next((t for t in city.troops if t.unit_type == "basic_infantry"), None)
                if troop:
                    troop.quantity += 1
                else:
                    new_troop = models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=1)
                    db.add(new_troop)
        
        # 3. Upgrade Buildings (Very rare)
        if random.random() < 0.001: # 0.1% chance
            # Pick a random building to upgrade
            # For now, just wall or warehouse
            pass
            
    db.commit()
