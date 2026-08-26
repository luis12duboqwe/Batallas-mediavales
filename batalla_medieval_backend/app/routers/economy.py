from fastapi import APIRouter

from ..services import balance, espionage, hero_rules, market

router = APIRouter(prefix="/economy", tags=["economy"])


def _espionage_rules_snapshot():
    """Expose the exact versioned rules consumed by the espionage resolver."""

    return {
        "algorithm_version": espionage.ESPIONAGE_ALGORITHM_VERSION,
        "luck_min": espionage.SPY_LUCK_MIN,
        "luck_max": espionage.SPY_LUCK_MAX,
        "success_chance_min": espionage.SPY_SUCCESS_CHANCE_MIN,
        "success_chance_max": espionage.SPY_SUCCESS_CHANCE_MAX,
        "detection_chance_min": espionage.SPY_DETECTION_CHANCE_MIN,
        "detection_chance_max": espionage.SPY_DETECTION_CHANCE_MAX,
        "failure_detection_bonus": espionage.SPY_FAILURE_DETECTION_BONUS,
        "troop_intel_threshold": espionage.SPY_TROOP_INTEL_THRESHOLD,
        "building_intel_threshold": espionage.SPY_BUILDING_INTEL_THRESHOLD,
        "defender_offset": balance.SPY_DEFENDER_OFFSET,
        "unknown_attacker_chance": balance.SPY_UNKNOWN_ATTACKER_CHANCE,
        "intel_levels": {
            "0": [],
            "1": ["resources"],
            "2": ["resources", "troops"],
            "3": ["resources", "troops", "buildings"],
        },
        "undetected_creates_defender_report": False,
        "failed_mission_returns_spies": False,
        "successful_mission_returns_spies": True,
    }


@router.get("/balance_preview")
def balance_preview():
    """Return the exact versioned rules consumed by live gameplay services."""

    payload = balance.snapshot()
    # Independently versioned subsystems are injected here without changing the
    # historical BALANCE_VERSION used by combat/espionage seeds.
    payload["espionage"] = _espionage_rules_snapshot()
    payload["market"] = market.commerce_rules_snapshot()
    payload["hero"] = hero_rules.snapshot()
    return payload
