import logging
import random

from sqlalchemy.orm import Session

from .. import models
from . import balance, production

logger = logging.getLogger(__name__)


def process_barbarian_growth(db: Session):
    """Advance the alpha barbarian economy using versioned balance values."""

    barbarian_cities = (
        db.query(models.City)
        .filter(models.City.owner_id.is_(None))
        .limit(balance.BARBARIAN_AI_BATCH_SIZE)
        .all()
    )

    recruit_unit = balance.BARBARIAN_RECRUIT_UNIT
    recruit_cost = balance.UNIT_CATALOG[recruit_unit]["training_cost"]

    for city in barbarian_cities:
        if random.random() < balance.BARBARIAN_RESOURCE_GROWTH_CHANCE:
            storage_limit = production.get_storage_limit(city)
            for resource in balance.RESOURCE_FIELDS:
                current = float(getattr(city, resource))
                setattr(
                    city,
                    resource,
                    min(
                        current + balance.BARBARIAN_RESOURCE_GROWTH_AMOUNT,
                        storage_limit,
                    ),
                )

        if random.random() < balance.BARBARIAN_RECRUIT_CHANCE:
            if production.check_cost(city, recruit_cost):
                production.pay_cost(city, recruit_cost)
                troop = next(
                    (t for t in city.troops if t.unit_type == recruit_unit),
                    None,
                )
                if troop:
                    troop.quantity += 1
                else:
                    db.add(
                        models.Troop(
                            city_id=city.id,
                            unit_type=recruit_unit,
                            quantity=1,
                        )
                    )

    db.commit()
