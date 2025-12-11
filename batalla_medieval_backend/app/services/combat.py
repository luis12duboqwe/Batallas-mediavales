from typing import Dict


def simulate_round(attacker: Dict[str, int], defender: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    result = {"attacker_losses": {}, "defender_losses": {}}
    for unit, amount in attacker.items():
        defender_loss = int(amount * 0.4)
        result["defender_losses"][unit] = defender_loss
    for unit, amount in defender.items():
        attacker_loss = int(amount * 0.35)
        result["attacker_losses"][unit] = attacker_loss
    return result
