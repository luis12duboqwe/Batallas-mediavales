"""Compatibility entrypoint for the BM-0067 PvE regeneration job."""

from sqlalchemy.orm import Session

from . import pve


def process_barbarian_growth(db: Session):
    """Advance versioned barbarian and oasis regeneration once per time bucket.

    The historical implementation used process-global randomness and selected
    barbarian cities without world scoping. BM-0067 keeps this public function
    for scheduler/test compatibility while delegating all behavior to the
    deterministic, world-versioned PvE engine.
    """

    return pve.process_pve_tick(db)
