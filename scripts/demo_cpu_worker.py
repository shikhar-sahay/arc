"""ARC demo CPU worker: predictable load cycles for contract demos.

Alternates between a busy high-load phase and an idle low-load phase so
a hysteresis contract (high CPU trigger, low CPU restore) can activate
and restore while this same process stays alive. Standard library only.
Exits cleanly on Ctrl+C.
"""

import argparse
import math
import os
import sys
import time


def burn(seconds: float) -> None:
    """One-core busy loop for roughly ``seconds``."""
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        total = 0
        for index in range(5000):
            total += math.isqrt(index * index + 1)
        if total == -1:  # pragma: no cover, keeps the loop honest
            print("unreachable")


def main(argv: list[str] | None = None) -> int:
    """Run load cycles until interrupted. Returns exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--high-seconds", type=float, default=15.0)
    parser.add_argument("--low-seconds", type=float, default=15.0)
    args = parser.parse_args(argv)
    if args.high_seconds <= 0 or args.low_seconds < 0:
        print("error: durations must be positive", file=sys.stderr)
        return 2
    print(
        f"demo_cpu_worker pid={os.getpid()} "
        f"high={args.high_seconds}s low={args.low_seconds}s (Ctrl+C to stop)",
        flush=True,
    )
    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"cycle {cycle}: high load", flush=True)
            burn(args.high_seconds)
            print(f"cycle {cycle}: idle", flush=True)
            time.sleep(args.low_seconds)
    except KeyboardInterrupt:
        print("demo_cpu_worker stopping", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
