from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException
from .. import models
from ..utils import utc_now

def get_relations(db: Session, alliance_id: int):
    return db.query(models.Diplomacy).filter(
        or_(models.Diplomacy.alliance_a_id == alliance_id, models.Diplomacy.alliance_b_id == alliance_id)
    ).all()

def request_relation(db: Session, alliance_id: int, target_id: int, relation_type: str):
    # relation_type: "nap", "ally", "war"
    
    if alliance_id == target_id:
        raise HTTPException(status_code=400, detail="Cannot have relation with self")

    # Check if relation exists
    # We store always a < b to avoid duplicates, or we check both ways.
    # The model has a unique constraint on (a, b). Let's enforce a < b convention or check both.
    
    a_id, b_id = sorted([alliance_id, target_id])
    
    existing = db.query(models.Diplomacy).filter(
        models.Diplomacy.alliance_a_id == a_id,
        models.Diplomacy.alliance_b_id == b_id
    ).first()
    
    if existing:
        # If war, we can overwrite anything immediately
        if relation_type == "war":
            existing.status = "war"
            existing.updated_at = utc_now()
            db.commit()
            return existing
        
        # If asking for same status
        if existing.status == relation_type:
            raise HTTPException(status_code=400, detail="Relation already exists")
            
        # If pending, maybe update?
        # For simplicity, let's say if you want to change status, you must cancel first unless it's war.
        raise HTTPException(status_code=400, detail="Relation already exists. Cancel it first.")

    # Create new
    status_val = "war" if relation_type == "war" else f"pending_{relation_type}"
    
    # If war, it's immediate. If NAP/Ally, it's pending until accepted.
    # But wait, who is the requester?
    # If I am A and I request NAP with B, status should be "pending_nap_by_a" or similar?
    # The simple model just has "pending_nap". We need to know who initiated to allow the other to accept.
    # The current model doesn't have "initiator_id".
    # Let's assume for now we just use "pending_nap" and we trust the system knows? 
    # Actually, if we enforce a < b, we lose info on who started it.
    # Let's modify the logic: We won't enforce a < b for the *record creation* if we want to track initiator by position,
    # OR we add initiator_id to the model.
    # Given I cannot easily change the model schema without migration (which I can do but it's risky),
    # I will check if I can add a column or if I should just use the existing structure.
    # The existing model `app/models/diplomacy.py` has `alliance_a_id` and `alliance_b_id`.
    
    # Let's try to use the existing model. If I create a record where alliance_a_id = requester, 
    # then "pending_nap" implies A asked B.
    # But the unique constraint might be (a, b). Let's check the model again.
    # __table_args__ = (UniqueConstraint("alliance_a_id", "alliance_b_id", name="uq_diplomacy_pair"),)
    # This implies order matters. So (1, 2) is different from (2, 1).
    # So I can use (requester, target) to store the direction.
    
    new_relation = models.Diplomacy(
        alliance_a_id=alliance_id,
        alliance_b_id=target_id,
        status=status_val,
        created_at=utc_now(),
        updated_at=utc_now()
    )
    db.add(new_relation)
    db.commit()
    return new_relation

def accept_relation(db: Session, alliance_id: int, diplomacy_id: int):
    relation = db.query(models.Diplomacy).filter(models.Diplomacy.id == diplomacy_id).first()
    if not relation:
        raise HTTPException(status_code=404, detail="Relation not found")
    
    # Only the target can accept
    if relation.alliance_b_id != alliance_id:
        raise HTTPException(status_code=403, detail="Only the target alliance can accept")
        
    if not relation.status.startswith("pending_"):
        raise HTTPException(status_code=400, detail="Not a pending relation")
        
    new_status = relation.status.replace("pending_", "")
    relation.status = new_status
    relation.updated_at = utc_now()
    db.commit()
    return relation

def cancel_relation(db: Session, alliance_id: int, diplomacy_id: int):
    relation = db.query(models.Diplomacy).filter(models.Diplomacy.id == diplomacy_id).first()
    if not relation:
        raise HTTPException(status_code=404, detail="Relation not found")
        
    # Either side can cancel
    if relation.alliance_a_id != alliance_id and relation.alliance_b_id != alliance_id:
        raise HTTPException(status_code=403, detail="Not involved in this relation")
        
    db.delete(relation)
    db.commit()
    return {"detail": "Relation cancelled"}
