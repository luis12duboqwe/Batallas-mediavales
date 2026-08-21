#!/usr/bin/env python3
"""Smoke a deployed web stack and enforce a small latency/error budget."""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request


def request(url: str, timeout: float) -> tuple[int, bytes, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
    elapsed_ms = (time.perf_counter() - started) * 1000
    return status, body, elapsed_ms


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-p95-ms", type=float, default=750.0)
    parser.add_argument("--allow-http", action="store_true", help="Only for local/CI smoke tests")
    args = parser.parse_args()

    parsed = urllib.parse.urlparse(args.base_url)
    if parsed.scheme != "https" and not args.allow_http:
        parser.error("protected deployment smoke requires an https:// base URL")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        parser.error("--base-url must be an absolute http(s) URL")
    if args.requests < 1:
        parser.error("--requests must be positive")

    base = args.base_url.rstrip("/")
    failures: list[str] = []

    probes = [
        ("edge health", "/health", False),
        ("backend health", "/api/health", False),
        ("frontend", "/", False),
        ("balance contract", "/api/economy/balance_preview", True),
    ]
    for name, path, expect_json in probes:
        status, body, _ = request(base + path, args.timeout)
        if status != 200:
            failures.append(f"{name}: expected HTTP 200, got {status}")
            continue
        if not body:
            failures.append(f"{name}: empty response")
            continue
        if expect_json:
            try:
                payload = json.loads(body)
                if not payload.get("version"):
                    failures.append(f"{name}: balance response has no version")
            except json.JSONDecodeError:
                failures.append(f"{name}: invalid JSON")

    latencies: list[float] = []
    statuses: list[int] = []
    for _ in range(args.requests):
        status, _, elapsed_ms = request(base + "/api/economy/balance_preview", args.timeout)
        statuses.append(status)
        latencies.append(elapsed_ms)

    errors = sum(1 for status in statuses if not 200 <= status < 300)
    server_errors = sum(1 for status in statuses if status >= 500)
    p95 = percentile(latencies, 0.95)
    result = {
        "requests": len(statuses),
        "errors": errors,
        "server_errors": server_errors,
        "error_rate": errors / len(statuses),
        "p95_ms": round(p95, 2),
        "max_p95_ms": args.max_p95_ms,
    }
    print(json.dumps(result, sort_keys=True))

    if server_errors:
        failures.append(f"observed {server_errors} HTTP 5xx responses")
    if errors:
        failures.append(f"observed {errors} non-2xx responses")
    if p95 > args.max_p95_ms:
        failures.append(f"p95 {p95:.2f}ms exceeds {args.max_p95_ms:.2f}ms")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print("deployment smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
