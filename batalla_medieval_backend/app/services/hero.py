from sqlalchemy.orm import Session
from .. import models

XP_TABLE = [0] + [int(100 * (1.2 ** (i - 1))) for i in range(1, 101)]

def get_hero(db: Session, user_id: int) -> models.Hero:
    hero = db.query(models.Hero).filter(models.Hero.user_id == user_id).first()
    if not hero:
        # Create default hero
        # Find first city
        city = db.query(models.City).filter(models.City.owner_id == user_id).first()
        hero = models.Hero(user_id=user_id, city_id=city.id if city else None)
        db.add(hero)
        db.commit()
        db.refresh(hero)
    return hero

def add_xp(db: Session, hero: models.Hero, xp_amount: int):
    hero.xp += xp_amount
    
    # Check level up
    while hero.level < 100 and hero.xp >= XP_TABLE[hero.level]:
        hero.xp -= XP_TABLE[hero.level]
        hero.level += 1
        # Grant attribute points? Usually 4 per level
        # For now, user has to distribute them manually, but we need a field for "available points"
        # Let's assume points are calculated: level * 4 - (attack + defense + production)
        
    db.commit()
    db.refresh(hero)

def get_available_points(hero: models.Hero) -> int:
    total_points = (hero.level - 1) * 4
    used_points = hero.attack_points + hero.defense_points + hero.production_points
    return max(0, total_points - used_points)

def distribute_points(db: Session, hero: models.Hero, attack: int, defense: int, production: int):
    available = get_available_points(hero)
    cost = attack + defense + production
    
    if cost > available:
        raise ValueError("Not enough points available")
        
    hero.attack_points += attack
    hero.defense_points += defense
    hero.production_points += production
    
    db.commit()
    db.refresh(hero)

def revive_hero(db: Session, hero: models.Hero):
    if hero.status != "dead":
        raise ValueError("Hero is not dead")
        
    # Cost? Time? For now instant revive
    hero.status = "home"
    hero.health = 100.0
    db.commit()
    db.refresh(hero)


def calculate_total_bonuses(hero: models.Hero) -> dict:
    """Calculate total bonuses from attributes and equipped items."""
    bonuses = {
        "attack": hero.attack_points * 0.01, # 1% per point
        "defense": hero.defense_points * 0.01,
        "production": hero.production_points * 0.005, # 0.5% per point
        "attack_infantry": 0.0,
        "attack_cavalry": 0.0,
        "defense_infantry": 0.0,
        "defense_cavalry": 0.0,
        "speed": 0.0,
    }
    
    for item in hero.items:
        if item.is_equipped:
            tmpl = item.template
            if tmpl.bonus_type in bonuses:
                bonuses[tmpl.bonus_type] += tmpl.bonus_value
            elif tmpl.bonus_type == "attack_all":
                bonuses["attack_infantry"] += tmpl.bonus_value
                bonuses["attack_cavalry"] += tmpl.bonus_value
            # Add more mappings as needed
            
    return bonuses

def equip_item(db: Session, hero: models.Hero, item_id: int):
    item = next((i for i in hero.items if i.id == item_id), None)
    if not item:
        raise ValueError("Item not found in inventory")
        
    # Unequip current item in same slot
    current = next((i for i in hero.items if i.is_equipped and i.template.slot == item.template.slot), None)
    if current:
        current.is_equipped = False
        
    item.is_equipped = True
    db.commit()
    db.refresh(hero)

def unequip_item(db: Session, hero: models.Hero, item_id: int):
    item = next((i for i in hero.items if i.id == item_id), None)
    if not item:
        raise ValueError("Item not found in inventory")
        
    item.is_equipped = False
    db.commit()
    db.refresh(hero)


def seed_items(db: Session):
    """Create default items if none exist."""
    if db.query(models.ItemTemplate).first():
        return

    items = [
        models.ItemTemplate(name="Espada de Madera", slot="weapon", rarity="common", bonus_type="attack_infantry", bonus_value=0.05, description="Una espada simple de entrenamiento."),
        models.ItemTemplate(name="Casco de Cuero", slot="head", rarity="common", bonus_type="defense_infantry", bonus_value=0.05, description="Protección básica."),
        models.ItemTemplate(name="Botas de Viaje", slot="feet", rarity="common", bonus_type="speed", bonus_value=0.10, description="Aumentan la velocidad de movimiento."),
        models.ItemTemplate(name="Hacha de Guerra", slot="weapon", rarity="rare", bonus_type="attack_infantry", bonus_value=0.15, description="Un hacha afilada."),
        models.ItemTemplate(name="Armadura de Placas", slot="body", rarity="epic", bonus_type="defense_infantry", bonus_value=0.20, description="Armadura pesada."),
        models.ItemTemplate(name="Caballo de Guerra", slot="horse", rarity="epic", bonus_type="speed", bonus_value=0.25, description="Un corcel rápido y fuerte."),
        models.ItemTemplate(name="Mapa Antiguo", slot="artifact", rarity="legendary", bonus_type="speed", bonus_value=0.50, description="Revela atajos secretos."),
    ]
    
    db.add_all(items)
    db.commit()

