"""Protect G5 frontend readiness from /health-only Docker Compose overrides."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendHealthContractTests(unittest.TestCase):
    def test_production_image_makes_public_assets_readable(self):
        dockerfile = (ROOT / "batalla_medieval_frontend/Dockerfile").read_text()
        self.assertIn("RUN chmod -R a+rX /usr/share/nginx/html", dockerfile)

    def test_production_image_health_requires_root_and_health(self):
        dockerfile = (ROOT / "batalla_medieval_frontend/Dockerfile").read_text()
        healthcheck = dockerfile.split("HEALTHCHECK", 1)[-1]
        self.assertIn("http://127.0.0.1/health", healthcheck)
        self.assertIn("http://127.0.0.1/ ", healthcheck)
        self.assertIn("&&", healthcheck)

    def test_all_compose_variants_check_frontend_root(self):
        for filename in ("docker-compose.yml", "docker-compose.deploy.yml"):
            with self.subTest(filename=filename):
                text = (ROOT / filename).read_text()
                block = re.search(r"(?ms)^  frontend:\n(?P<body>.*?)^  nginx:\n", text)
                self.assertIsNotNone(block, "Missing frontend service")
                healthcheck = block.group("body")
                self.assertIn("CMD-SHELL", healthcheck)
                self.assertIn("http://127.0.0.1/health", healthcheck)
                self.assertIn("http://127.0.0.1/ >/dev/null", healthcheck)
                self.assertIn("&&", healthcheck)


if __name__ == "__main__":
    unittest.main()
