"""Bounded CPU workers for the Resource Lab.

Each worker publishes measured loop throughput to a private runtime file.
The controller owns the processes and mode file. This module never changes
resource controls itself; ARC contracts remain the only enforcement path.
"""

import argparse
import json
import os
import time
from pathlib import Path


def _mode(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "stop"


def run(role: str, mode_path: Path, stats_path: Path) -> None:
    count = 0
    value = 1
    window_started = time.monotonic()
    while (mode := _mode(mode_path)) != "stop":
        active = role == "foreground" or (role == "background" and mode == "high")
        if active:
            for _ in range(25_000):
                value = (value * 1_664_525 + 1_013_904_223) & 0xFFFFFFFF
            count += 25_000
        else:
            time.sleep(0.05)
        now = time.monotonic()
        elapsed = now - window_started
        if elapsed >= 0.5:
            payload = {
                "pid": os.getpid(),
                "role": role,
                "mode": mode,
                "operations_per_second": count / elapsed,
                "sampled_at": time.time(),
                "checksum": value,
            }
            temporary = stats_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            temporary.replace(stats_path)
            count = 0
            window_started = now


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--role",
        choices=("foreground", "background", "suspension-target"),
        required=True,
    )
    parser.add_argument("--mode-file", type=Path, required=True)
    parser.add_argument("--stats-file", type=Path, required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    run(args.role, args.mode_file, args.stats_file)


if __name__ == "__main__":
    main()
