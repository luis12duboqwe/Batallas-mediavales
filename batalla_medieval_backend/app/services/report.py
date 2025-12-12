import json
from sqlalchemy.orm import Session
from .. import models

def create_trade_report(db: Session, sender: models.City, receiver: models.City, resources: dict[str, int]):
    content = json.dumps({
        "type": "trade",
        "sender": {"id": sender.id, "name": sender.name},
        "receiver": {"id": receiver.id, "name": receiver.name},
        "resources": resources
    })
    
    # Report for sender
    db.add(models.Report(
        city_id=sender.id,
        world_id=sender.world_id,
        report_type="trade",
        content=content,
        attacker_city_id=sender.id,
        defender_city_id=receiver.id
    ))
    
    # Report for receiver
    db.add(models.Report(
        city_id=receiver.id,
        world_id=receiver.world_id,
        report_type="trade",
        content=content,
        attacker_city_id=sender.id,
        defender_city_id=receiver.id
    ))
    db.commit()

def create_return_report(db: Session, city: models.City, from_city: models.City, troops: dict[str, int], resources: dict[str, int] | None = None):
    content = json.dumps({
        "type": "return",
        "from": {"id": from_city.id, "name": from_city.name},
        "troops": troops,
        "resources": resources or {}
    })
    
    db.add(models.Report(
        city_id=city.id,
        world_id=city.world_id,
        report_type="return",
        content=content,
        attacker_city_id=from_city.id,
        defender_city_id=city.id
    ))
    db.commit()

def create_reinforce_report(db: Session, sender: models.City, receiver: models.City, troops: dict[str, int]):
    content = json.dumps({
        "type": "reinforce",
        "sender": {"id": sender.id, "name": sender.name},
        "receiver": {"id": receiver.id, "name": receiver.name},
        "troops": troops
    })
    
    # Report for sender
    db.add(models.Report(
        city_id=sender.id,
        world_id=sender.world_id,
        report_type="reinforce",
        content=content,
        attacker_city_id=sender.id,
        defender_city_id=receiver.id
    ))
    
    # Report for receiver
    db.add(models.Report(
        city_id=receiver.id,
        world_id=receiver.world_id,
        report_type="reinforce",
        content=content,
        attacker_city_id=sender.id,
        defender_city_id=receiver.id
    ))
    db.commit()
