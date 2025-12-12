from datetime import timedelta
import json
from sqlalchemy.orm import Session
from app import models
from app.services import movement
from app.utils import utc_now

def test_trade_report_generation(db_session: Session, city: models.City, second_city: models.City):
    # Setup: Create a transport movement that has arrived
    resources = {"wood": 100, "clay": 100, "iron": 100}
    arrival_time = utc_now() - timedelta(minutes=1)
    
    mov = models.Movement(
        origin_city_id=city.id,
        target_city_id=second_city.id,
        movement_type="transport",
        resources=resources,
        arrival_time=arrival_time,
        status="ongoing",
        world_id=city.world_id
    )
    db_session.add(mov)
    db_session.commit()
    
    # Act: Resolve movements
    movement.resolve_due_movements(db_session)
    
    # Assert: Check for Trade Report
    report = db_session.query(models.Report).filter_by(
        report_type="trade",
        attacker_city_id=city.id, # In trade report, attacker is origin
        defender_city_id=second_city.id # defender is target
    ).first()
    
    assert report is not None
    content = json.loads(str(report.content))
    assert content["resources"] == resources
    assert content["sender"]["name"] == city.name
    assert content["receiver"]["name"] == second_city.name

def test_return_report_generation(db_session: Session, city: models.City, second_city: models.City):
    # Setup: Create a return movement that has arrived
    troops = {"basic_infantry": 10}
    arrival_time = utc_now() - timedelta(minutes=1)
    
    mov = models.Movement(
        origin_city_id=second_city.id, # Returning from second_city
        target_city_id=city.id, # To city
        movement_type="return",
        troops=troops,
        arrival_time=arrival_time,
        status="ongoing",
        world_id=city.world_id
    )
    db_session.add(mov)
    db_session.commit()
    
    # Act: Resolve movements
    movement.resolve_due_movements(db_session)
    
    # Assert: Check for Return Report
    report = db_session.query(models.Report).filter_by(
        report_type="return",
        city_id=city.id
    ).first()
    
    assert report is not None
    content = json.loads(str(report.content))
    assert content["troops"] == troops
    assert content["from"]["name"] == second_city.name

def test_reinforce_report_generation(db_session: Session, city: models.City, second_city: models.City):
    # Setup: Create a reinforce movement that has arrived
    troops = {"basic_infantry": 20}
    arrival_time = utc_now() - timedelta(minutes=1)
    
    mov = models.Movement(
        origin_city_id=city.id,
        target_city_id=second_city.id,
        movement_type="reinforce",
        troops=troops,
        arrival_time=arrival_time,
        status="ongoing",
        world_id=city.world_id
    )
    db_session.add(mov)
    db_session.commit()
    
    # Act: Resolve movements
    movement.resolve_due_movements(db_session)
    
    # Assert: Check for Reinforce Report
    report = db_session.query(models.Report).filter_by(
        report_type="reinforce",
        defender_city_id=second_city.id
    ).first()
    
    assert report is not None
    content = json.loads(str(report.content))
    assert content["troops"] == troops
    assert content["sender"]["name"] == city.name
