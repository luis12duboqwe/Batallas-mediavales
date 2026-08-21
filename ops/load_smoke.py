#!/usr/bin/env python3
"""Run a bounded concurrent read load against a deployed stack.

This is intentionally dependency-free so the exact same probe can run in CI,
staging, or an incident host. It is not a substitute for production capacity
planning; it is the G5 reproducible baseline and can be lengthened for soak runs.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def one_request(url: str, timeout: float) -> tuple[int, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        exc.read()
        status = exc.code
    except Exception:
        status = 0
    return status, (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--path", default="/api/economy/balance_preview")
    parser.add_argument("--duration-seconds", type=float, default=10.0)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-p95-ms", type=float, default=750.0)
    parser.add_argument("--max-error-rate", type=float, default=0.005)
    parser.add_argument("--allow-http", action="store_true", help="Only for local/CI load tests")
    args = parser.parse_args()

    parsed = urllib.parse.urlparse(args.base_url)
    if parsed.scheme != "https" and not args.allow_http:
        parser.error("protected load tests require an https:// base URL")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        parser.error("--base-url must be an absolute http(s) URL")
    if args.duration_seconds <= 0 or args.concurrency < 1:
        parser.error("duration and concurrency must be positive")
    if not 0 <= args.max_error_rate <= 1:
        parser.error("--max-error-rate must be between 0 and 1")

    url = args.base_url.rstrip("/") + "/" + args.path.lstrip("/")
    deadline = time.monotonic() + args.duration_seconds
    lock = threading.Lock()
    statuses: list[int] = []
    latencies: list[float] = []

    def worker() -> None:
        while time.monotonic() < deadline:
            status, latency = one_request(url, args.timeout)
            with lock:
                statuses.append(status)
                latencies.append(latency)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(worker) for _ in range(args.concurrency)]
        for future in futures:
            future.result()

    if not statuses:
        print("FAIL: no requests completed")
        return 1

    errors = sum(1 for status in statuses if not 200 <= status < 300)
    server_errors = sum(1 for status in statuses if status >= 500)
    error_rate = errors / len(statuses)
    p95 = percentile(latencies, 0.95)
    result = {
        "requests": len(statuses),
        "duration_seconds": args.duration_seconds,
        "concurrency": args.concurrency,
        "requests_per_second": round(len(statuses) / args.duration_seconds, 2),
        "errors": errors,
        "server_errors": server_errors,
        "error_rate": round(error_rate, 6),
        "p95_ms": round(p95, 2),
        "max_error_rate": args.max_error_rate,
        "max_p95_ms": args.max_p95_ms,
    }
    print(json.dumps(result, sort_keys=True))

    failures: list[str] = []
    if server_errors:
        failures.append(f"observed {server_errors} HTTP 5xx responses")
    if error_rate > args.max_error_rate:
        failures.append(f"error rate {error_rate:.4%} exceeds {args.max_error_rate:.4%}")
    if p95 > args.max_p95_ms:
        failures.append(f"p95 {p95:.2f}ms exceeds {args.max_p95_ms:.2f}ms")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print("load probe passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
