"""Bounded ARC faculty-demo workload controller for Linux and WSL2.

The controller only signals child processes whose PID, Linux start time, and
unique command-line token match its own state file. It never uses sudo and
never targets unrelated processes.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

TARGET_TOKEN = "arc-faculty-demo-target"
LOAD_TOKEN = "arc-faculty-demo-load"
STATE_PATH = Path(f"/tmp/arc-faculty-demo-{getattr(os, 'getuid', lambda: 0)()}.json")


def _proc_start(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[21]
    except (FileNotFoundError, IndexError, PermissionError):
        return None


def _cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError):
        return ""


def _owned(entry: dict[str, object], token: str) -> bool:
    pid = int(entry["pid"])
    return _proc_start(pid) == entry.get("start") and token in _cmdline(pid)


def _load_state() -> dict[str, object]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"target": None, "load": []}


def _save_state(state: dict[str, object]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _spawn(role: str, token: str) -> dict[str, object]:
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "_worker", role, token],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(20):
        start = _proc_start(process.pid)
        if start is not None:
            return {"pid": process.pid, "start": start}
        time.sleep(0.05)
    process.terminate()
    raise RuntimeError(f"worker {process.pid} did not become observable")


def _stop_entries(entries: list[dict[str, object]], token: str) -> None:
    for entry in entries:
        if _owned(entry, token):
            os.kill(int(entry["pid"]), signal.SIGTERM)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if not any(_owned(entry, token) for entry in entries):
            return
        time.sleep(0.1)
    for entry in entries:
        if _owned(entry, token):
            os.kill(int(entry["pid"]), signal.SIGKILL)


def _affinity(pid: int) -> str:
    return Path(f"/proc/{pid}/status").read_text(encoding="utf-8").split(
        "Cpus_allowed_list:\t", 1
    )[1].splitlines()[0]


def _sample_cpu(seconds: float = 1.0) -> float:
    def counters() -> tuple[int, int]:
        values = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        return sum(values), values[3] + values[4]

    total_a, idle_a = counters()
    time.sleep(seconds)
    total_b, idle_b = counters()
    return 100 * (1 - (idle_b - idle_a) / max(1, total_b - total_a))


def command_start(workers: int) -> int:
    if sys.platform != "linux":
        print("error: this demo requires Linux or WSL2", file=sys.stderr)
        return 2
    state = _load_state()
    target = state.get("target")
    if not isinstance(target, dict) or not _owned(target, TARGET_TOKEN):
        target = _spawn("target", TARGET_TOKEN)
    old_load = [entry for entry in state.get("load", []) if isinstance(entry, dict)]
    _stop_entries(old_load, LOAD_TOKEN)
    load = [_spawn("load", LOAD_TOKEN) for _ in range(workers)]
    state = {"target": target, "load": load}
    _save_state(state)
    pid = int(target["pid"])
    print(f"target PID: {pid}")
    print(f"original affinity: {_affinity(pid)}")
    print(f"load workers: {len(load)}")
    print(f"measured system CPU during HIGH phase: {_sample_cpu():.1f}%")
    print(f"verify: taskset -pc {pid}")
    print(f"verify: grep -E 'State|Cpus_allowed_list' /proc/{pid}/status")
    return 0


def command_high(workers: int) -> int:
    state = _load_state()
    target = state.get("target")
    if not isinstance(target, dict) or not _owned(target, TARGET_TOKEN):
        print("error: run 'start' first", file=sys.stderr)
        return 2
    old_load = [entry for entry in state.get("load", []) if isinstance(entry, dict)]
    _stop_entries(old_load, LOAD_TOKEN)
    state["load"] = [_spawn("load", LOAD_TOKEN) for _ in range(workers)]
    _save_state(state)
    print(f"HIGH phase started with {workers} bounded workers")
    print(f"measured system CPU: {_sample_cpu():.1f}%")
    return 0


def command_low() -> int:
    state = _load_state()
    load = [entry for entry in state.get("load", []) if isinstance(entry, dict)]
    _stop_entries(load, LOAD_TOKEN)
    state["load"] = []
    _save_state(state)
    print("LOW phase started; controlled target remains alive")
    print(f"measured system CPU: {_sample_cpu():.1f}%")
    return 0


def command_status() -> int:
    state = _load_state()
    target = state.get("target")
    if isinstance(target, dict) and _owned(target, TARGET_TOKEN):
        pid = int(target["pid"])
        print(f"target PID: {pid}, affinity: {_affinity(pid)}")
    else:
        print("target: stopped")
    load = [entry for entry in state.get("load", []) if isinstance(entry, dict)]
    print(f"live load workers: {sum(_owned(entry, LOAD_TOKEN) for entry in load)}")
    return 0


def command_stop() -> int:
    state = _load_state()
    load = [entry for entry in state.get("load", []) if isinstance(entry, dict)]
    _stop_entries(load, LOAD_TOKEN)
    target = state.get("target")
    if isinstance(target, dict):
        _stop_entries([target], TARGET_TOKEN)
    STATE_PATH.unlink(missing_ok=True)
    print("ARC demo workers stopped")
    return 0


def worker(role: str, token: str) -> int:
    del token
    stopping = False
    value = 1

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    if role == "target":
        while not stopping:
            time.sleep(0.2)
    else:
        while not stopping:
            value = (value * 1664525 + 1013904223) & 0xFFFFFFFF
    return value == -1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    default_workers = max(1, min(8, (os.cpu_count() or 2) // 2))
    for name in ("start", "high"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--workers", type=int, default=default_workers, choices=range(1, 17))
    subparsers.add_parser("low")
    subparsers.add_parser("status")
    subparsers.add_parser("stop")
    internal = subparsers.add_parser("_worker")
    internal.add_argument("role", choices=("target", "load"))
    internal.add_argument("token")
    args = parser.parse_args()
    if args.command == "_worker":
        return worker(args.role, args.token)
    if args.command in ("start", "high"):
        return command_start(args.workers) if args.command == "start" else command_high(args.workers)
    if args.command == "low":
        return command_low()
    if args.command == "status":
        return command_status()
    return command_stop()


if __name__ == "__main__":
    raise SystemExit(main())
