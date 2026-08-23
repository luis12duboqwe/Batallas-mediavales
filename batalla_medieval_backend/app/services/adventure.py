import random
from typing import Any
from datetime import timedelta
from sqlalchemy.orm import Session
from .. import models
from ..utils import utc_now
from . import balance, hero as hero_service

DIFFICULTY_CONFIG = {
    "easy": {"duration": 300, "xp": 50, "damage_min": 1, "damage_max": 10},
    "medium": {"duration": 1800, "xp": 200, "damage_min": 10, "damage_max": 30},
    "hard": {"duration": 7200, "xp": 1000, "damage_min": 30, "damage_max": 60},
}

def get_adventures(db: Session, hero_id: int) -> list[models.Adventure]:
    """Get available adventures for hero. Generate new ones if needed."""
    adventures = db.query(models.Adventure).filter(
        models.Adventure.hero_id == hero_id,
        models.Adventure.status.in_(["available", "active", "completed"])
    ).all()
    
    active_or_available = [a for a in adventures if a.status in ["available", "active"]]
    
    if not active_or_available:
        new_adventures: list[models.Adventure] = []
        for _ in range(3):
            diff = random.choice(["easy", "easy", "medium", "medium", "hard"])
            config = DIFFICULTY_CONFIG[diff]
            adv = models.Adventure(
                hero_id=hero_id,
                difficulty=diff,
                duration=config["duration"],
                status="available"
            )
            db.add(adv)
            new_adventures.append(adv)
        db.commit()
        for adv in new_adventures:
            db.refresh(adv)
        return new_adventures
        
    return adventures

def start_adventure(db: Session, adventure_id: int, hero: models.Hero) -> models.Adventure:
    adv = db.query(models.Adventure).filter(models.Adventure.id == adventure_id).first()
    if not adv:
        raise ValueError("Adventure not found")
    
    if adv.hero_id != hero.id:
        raise ValueError("Not your adventure")
        
    if adv.status != "available":
        raise ValueError("Adventure not available")
        
    if hero.status != "home":
        raise ValueError("Hero is busy")
        
    if hero.health < 20:
        raise ValueError("Hero is too injured")

    adv.status = "active"
    adv.started_at = utc_now()
    hero.status = "adventure"
    
    db.commit()
    db.refresh(adv)
    return adv

def claim_adventure(db: Session, adventure_id: int, hero: models.Hero) -> dict[str, Any]:
    adv = db.query(models.Adventure).filter(models.Adventure.id == adventure_id).first()
    if not adv:
        raise ValueError("Adventure not found")
        
    if adv.status != "active":
        raise ValueError("Adventure not active")
        
    now = utc_now()
    started_at = adv.started_at
    if started_at.tzinfo is None:
        from datetime import timezone
        started_at = started_at.replace(tzinfo=timezone.utc)
        
    end_time = started_at + timedelta(seconds=adv.duration)
    
    if now < end_time:
        raise ValueError("Adventure not finished yet")
        
    config = DIFFICULTY_CONFIG[adv.difficulty]
    raw_damage = random.randint(config["damage_min"], config["damage_max"])
    defense_reduction = hero.defense_points // 10
    damage = max(1, raw_damage - defense_reduction)
    
    hero.health = max(0, hero.health - damage)
    if hero.health == 0:
        hero.status = "dead"
        adv.status = "failed"
        db.commit()
        return {"status": "dead", "damage": damage, "xp": 0, "loot": None}
    
    hero.status = "home"
    adv.status = "completed"
    adv.completed_at = now
    
    xp_gained = config["xp"]
    hero_service.add_xp(db, hero, xp_gained)
    
    loot: dict[str, Any] | None = None
    roll = random.random()
    if roll < 0.10:
        templates = db.query(models.ItemTemplate).all()
        if templates:
            item_tmpl = random.choice(templates)
            hero_item = models.HeroItem(hero_id=hero.id, template_id=item_tmpl.id)
            db.add(hero_item)
            loot = {"type": "item", "name": item_tmpl.name, "rarity": item_tmpl.rarity}
    elif roll < 0.40:
        if hero.city:
            amount = random.randint(100, 500) * (1 if adv.difficulty == "easy" else 3 if adv.difficulty == "medium" else 10)
            res_type = random.choice(list(balance.RESOURCE_FIELDS))
            setattr(hero.city, res_type, getattr(hero.city, res_type) + amount)
            loot = {"type": "resource", "resource": res_type, "amount": amount}
            
    db.commit()
    
    return {
        "status": "success",
        "damage": damage,
        "xp": xp_gained,
        "loot": loot
    }
