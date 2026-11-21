"""G5 read-load budgets must not accidentally defeat the public API rate limit."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
from load_smoke import RequestPacer  # noqa: E402


class RatePacerTests(unittest.TestCase):
    def test_global_rate_is_shared_across_concurrent_clients(self):
        pacer = RequestPacer(20.0, started_at=0.0)
        with ThreadPoolExecutor(max_workers=10) as executor:
            times = list(executor.map(lambda _: pacer.reserve(10.0, now=0.0), range(40)))
        self.assertNotIn(None, times)
        ordered = sorted(times)
        self.assertAlmostEqual(ordered[0], 0.0)
        self.assertAlmostEqual(ordered[-1], 39 / 20.0)
        for previous, next_time in zip(ordered, ordered[1:]):
            self.assertGreaterEqual(next_time - previous, 1 / 20.0 - 1e-9)

    def test_deadline_is_enforced_before_reservation(self):
        pacer = RequestPacer(4.0, started_at=0.0)
        times = [pacer.reserve(1.0, now=0.0) for _ in range(5)]
        self.assertEqual(times[:4], [0.0, 0.25, 0.5, 0.75])
        self.assertIsNone(times[4])

    def test_delayed_request_can_resume_without_burst(self):
        pacer = RequestPacer(2.0, started_at=0.0)
        self.assertEqual(pacer.reserve(20.0, now=0.0), 0.0)
        self.assertEqual(pacer.reserve(20.0, now=10.0), 10.0)
        self.assertEqual(pacer.reserve(20.0, now=10.0), 10.5)

    def test_unbounded_or_invalid_target_rejected(self):
        for target in (0, -1, float("inf"), float("-inf"), float("nan")):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    RequestPacer(target, started_at=0.0)

    def test_nginx_returns_429_for_intentional_throttling(self):
        nginx = (ROOT / "nginx.conf").read_text(encoding="utf-8")
        api_location = nginx.split("location /api/ {", 1)[1].split("}", 1)[0]
        self.assertIn("limit_req zone=api_limit burst=20 nodelay;", api_location)
        self.assertIn("limit_req_status 429;", api_location)
        self.assertIn("rate=10r/s;", nginx)


if __name__ == "__main__":
    unittest.main()
