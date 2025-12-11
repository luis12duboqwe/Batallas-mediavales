import random
from typing import Tuple


def attempt_spy(attacker_luck: float, defender_awareness: float) -> Tuple[bool, bool]:
    success_chance = max(0.1, min(0.9, attacker_luck - defender_awareness + 0.5))
    success = random.random() < success_chance
    reveal_identity = random.random() < (1 - success_chance)
    return success, reveal_identity
