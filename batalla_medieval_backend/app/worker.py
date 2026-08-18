"""Dedicated process entrypoint for periodic game jobs."""

from __future__ import annotations

import logging
import signal
from threading import Event

from .scheduler import shutdown_scheduler, start_scheduler

logger = logging.getLogger(__name__)
_shutdown_requested = Event()


def _request_shutdown(signum, _frame) -> None:
    logger.info("Worker shutdown requested by signal %s", signum)
    _shutdown_requested.set()


def main() -> None:
    """Run the scheduler until SIGINT/SIGTERM requests a clean shutdown."""

    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    start_scheduler()
    try:
        _shutdown_requested.wait()
    finally:
        shutdown_scheduler()


if __name__ == "__main__":
    main()
