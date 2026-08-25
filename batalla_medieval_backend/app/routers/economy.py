from fastapi import APIRouter

from ..services import balance, espionage, market, pve_rules

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
    # BM-0065 versions espionage independently from BM-0064 combat so changing
    # spy rules cannot silently change combat seeds/results. Replace the legacy
    # snapshot block with the exact live espionage contract.
    payload["espionage"] = _espionage_rules_snapshot()
    # BM-0066 follows the same exact-contract discipline for commerce while
    # preserving the historical BALANCE_VERSION used by prior military seeds.
    payload["market"] = market.commerce_rules_snapshot()
    # BM-0067 pins PvE independently per world so tuning neutral content does
    # not change historical BM-0064/BM-0065 random streams.
    payload["pve"] = pve_rules.rules_snapshot()
    return payload
