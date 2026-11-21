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

from probe_auth import build_probe_opener


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


class RequestPacer:
    """Reserve one shared request slot across all worker threads.

    A concurrency bound alone does not bound requests per second: a fast GET
    loop can overwhelm nginx's per-client rate limit and produce false 5xx
    alarms instead of meaningful G5 measurements.
    """

    def __init__(self, target_rps: float, *, started_at: float) -> None:
        if not math.isfinite(target_rps) or target_rps <= 0:
            raise ValueError("target_rps must be finite and positive")
        self._interval = 1.0 / target_rps
        self._next_at = started_at
        self._lock = threading.Lock()

    def reserve(self, deadline: float, *, now: float | None = None) -> float | None:
        """Return a scheduled monotonic timestamp or None past the deadline."""
        current = time.monotonic() if now is None else now
        with self._lock:
            scheduled = max(current, self._next_at)
            if scheduled >= deadline:
                return None
            self._next_at = scheduled + self._interval
            return scheduled


def one_request(
    url: str, timeout: float, opener: urllib.request.OpenerDirector | None = None
) -> tuple[int, float]:
    started = time.perf_counter()
    open_url = urllib.request.urlopen if opener is None else opener.open
    try:
        with open_url(url, timeout=timeout) as response:
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
    parser.add_argument("--target-rps", type=float, default=6.0,
                        help="Total requests per second across all clients (G5 safe default: 6)")
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
    if not math.isfinite(args.duration_seconds) or args.duration_seconds <= 0 or args.concurrency < 1:
        parser.error("duration and concurrency must be positive")
    if not math.isfinite(args.target_rps) or args.target_rps <= 0:
        parser.error("--target-rps must be finite and positive")
    if not math.isfinite(args.max_error_rate) or not 0 <= args.max_error_rate <= 1:
        parser.error("--max-error-rate must be finite and between 0 and 1")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if not math.isfinite(args.max_p95_ms) or args.max_p95_ms <= 0:
        parser.error("--max-p95-ms must be finite and positive")

    try:
        build_probe_opener(args.base_url)  # fail closed on partial/unsafe config
    except ValueError as exc:
        parser.error(str(exc))

    url = args.base_url.rstrip("/") + "/" + args.path.lstrip("/")
    started_at = time.monotonic()
    deadline = started_at + args.duration_seconds
    pacer = RequestPacer(args.target_rps, started_at=started_at)
    lock = threading.Lock()
    statuses: list[int] = []
    latencies: list[float] = []

    def worker() -> None:
        # One opener per thread: urllib's challenge/retry state is not shared.
        opener = build_probe_opener(args.base_url)
        while True:
            scheduled = pacer.reserve(deadline)
            if scheduled is None:
                break
            time.sleep(max(0.0, scheduled - time.monotonic()))
            status, latency = one_request(url, args.timeout, opener=opener)
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
        "target_rps": args.target_rps,
        "status_counts": {str(code): statuses.count(code) for code in sorted(set(statuses))},
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
