from fastapi import APIRouter

from ..services import building as building_service
from ..services import combat, economy, production as production_service, troops as troop_service

router = APIRouter(prefix="/economy", tags=["economy"])


@router.get("/balance_preview")
def balance_preview():
    siege_units = {
        unit: combat.UNIT_STATS[unit]
        for unit in ["quebramuros", "tormenta_de_piedra", "ram", "catapult"]
        if unit in combat.UNIT_STATS
    }

    return {
        "buildings": {
            "base_costs": economy.BASE_BUILDING_COSTS,
            "queue_base_costs": building_service.BUILDING_COSTS,
            "base_build_time_seconds": building_service.BASE_BUILD_TIME_SECONDS,
            "upgrade_multipliers": {
                "economy_buildings": 1.26,
                "queue_buildings": 1.2,
            },
        },
        "troops": {
            "base_costs": economy.BASE_TROOP_COSTS,
            "queue_costs": troop_service.UNIT_COSTS,
            "base_training_times": economy.BASE_TRAINING_TIMES,
            "queue_training_times": troop_service.TRAINING_TIMES,
        },
        "production": {
            "base_rates_per_minute": production_service.PRODUCTION_RATES,
            "loyalty_recovery_per_hour": production_service.LOYALTY_RECOVERY_PER_HOUR,
        },
        "siege": {
            "unit_stats": siege_units,
            "wall_damage_formula": "damage = max(1, int(sqrt(siege_survivors)))",
        },
    }

