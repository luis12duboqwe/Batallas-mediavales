import random
from sqlalchemy.orm import Session
from .. import models

def create_world(db: Session, name: str, speed: float = 1.0) -> models.World:
    world = models.World(name=name, speed_modifier=speed, is_active=True)
    db.add(world)
    db.commit()
    db.refresh(world)
    
    # Generate map
    # 100x100 grid?
    # We don't store every tile, just cities.
    # But we need to assign tile types to coordinates if we want a persistent map.
    # Or we can determine tile type deterministically based on coordinates (Perlin noise or hash).
    # For simplicity, let's just create some barbarian villages.
    
    for _ in range(50):
        x = random.randint(-50, 50)
        y = random.randint(-50, 50)
        
        # Check collision
        if db.query(models.City).filter(models.City.world_id == world.id, models.City.x == x, models.City.y == y).first():
            continue
            
        city = models.City(
            name="Aldea Bárbara",
            world_id=world.id,
            x=x,
            y=y,
            owner_id=None, # Barbarian
            wood=1000,
            clay=1000,
            iron=1000,
            tile_type=random.choice(["forest", "mountain", "water", "grass", "grass", "grass"])
        )
        db.add(city)

    # Generate Oases
    for _ in range(20): # 20 Oases
        x = random.randint(-50, 50)
        y = random.randint(-50, 50)
        
        # Check collision with cities or other oases
        if db.query(models.City).filter(models.City.world_id == world.id, models.City.x == x, models.City.y == y).first():
            continue
        if db.query(models.Oasis).filter(models.Oasis.world_id == world.id, models.Oasis.x == x, models.Oasis.y == y).first():
            continue
            
        resource_type = random.choice(["wood", "clay", "iron", "crop"])
        bonus = 25 if random.random() > 0.2 else 50 # 20% chance for 50% bonus
        
        oasis = models.Oasis(
            world_id=world.id,
            x=x,
            y=y,
            resource_type=resource_type,
            bonus_percent=bonus,
            troops={"rat": random.randint(5, 15), "spider": random.randint(3, 8)}
        )
        db.add(oasis)
        
    db.commit()
    return world

def get_tile_type(x: int, y: int) -> str:
    # Deterministic tile generation
    random.seed(f"{x},{y}")
    val = random.random()
    if val < 0.1: return "water"
    if val < 0.3: return "mountain"
    if val < 0.5: return "forest"
    return "grass"


def find_spawn_location(db: Session, world_id: int, map_size: int) -> tuple[int, int]:
    """Find a valid spawn location for a new city."""
    # Try random locations first for performance
    for _ in range(50):
        x = random.randint(0, map_size - 1)
        y = random.randint(0, map_size - 1)
        
        # Check if occupied
        if not db.query(models.City).filter(
            models.City.world_id == world_id, 
            models.City.x == x, 
            models.City.y == y
        ).first():
            # Check tile type suitability (optional, e.g. don't spawn on water)
            tile_type = get_tile_type(x, y)
            if tile_type != "water":
                return x, y

    # If random fails, search systematically (spiral from center)
    center_x, center_y = map_size // 2, map_size // 2
    # Simple spiral or expanding square
    for r in range(1, map_size):
        for i in range(-r, r + 1):
            for j in range(-r, r + 1):
                # We only want the perimeter of the square
                if abs(i) != r and abs(j) != r:
                    continue
                
                x, y = center_x + i, center_y + j
                if 0 <= x < map_size and 0 <= y < map_size:
                    if not db.query(models.City).filter(
                        models.City.world_id == world_id, 
                        models.City.x == x, 
                        models.City.y == y
                    ).first():
                        tile_type = get_tile_type(x, y)
                        if tile_type != "water":
                            return x, y
                            
    raise ValueError("No valid spawn location found")
