"""Lifecycle and measurements for ARC-owned Resource Lab processes."""

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import psutil


class ResourceLabError(RuntimeError):
    """A requested lab transition is unsafe or invalid."""


class ResourceLabController:
    """Own a single bounded scenario and expose kernel-read measurements."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._directory: Path | None = None
        self._token: str | None = None
        self._mode = "stopped"
        self._processes: dict[int, subprocess.Popen[bytes]] = {}
        self._roles: dict[int, str] = {}
        self._stats_paths: dict[int, Path] = {}
        self._original_affinity: dict[int, tuple[int, ...]] = {}
        self._cpu_samples: dict[int, tuple[float, float]] = {}

    @property
    def supported(self) -> bool:
        return sys.platform == "linux"

    def start(self, workers: int) -> dict[str, object]:
        with self._lock:
            if not self.supported:
                raise ResourceLabError("Resource Lab requires Linux or WSL2")
            if self._live_pids():
                raise ResourceLabError("a Resource Lab scenario is already running")
            maximum = min(16, max(1, psutil.cpu_count(logical=True) or 1))
            if workers < 1 or workers > maximum:
                raise ResourceLabError(f"worker count must be between 1 and {maximum}")
            self._directory = Path(tempfile.mkdtemp(prefix="arc-resource-lab-"))
            self._token = uuid.uuid4().hex
            self._write_mode("low")
            self._spawn("foreground", 0)
            for index in range(workers):
                self._spawn("background", index)
            self._mode = "baseline"
            foreground_pid = next(pid for pid, role in self._roles.items() if role == "foreground")
            foreground = psutil.Process(foreground_pid)
            foreground.cpu_affinity([self._original_affinity[foreground_pid][0]])
            time.sleep(0.15)
            return self.status()

    def set_pressure(self, high: bool) -> dict[str, object]:
        with self._lock:
            if not self._live_pids():
                raise ResourceLabError("start the scenario first")
            self._write_mode("high" if high else "low")
            self._mode = "pressure" if high else "recovery"
            return self.status()

    def stop(self) -> dict[str, object]:
        with self._lock:
            self._write_mode("stop")
            for process in self._processes.values():
                if process.poll() is None:
                    process.terminate()
            for process in self._processes.values():
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            self._processes.clear()
            self._roles.clear()
            self._stats_paths.clear()
            self._original_affinity.clear()
            self._cpu_samples.clear()
            if self._directory is not None:
                shutil.rmtree(self._directory, ignore_errors=True)
            self._directory = None
            self._token = None
            self._mode = "stopped"
            return self.status()

    def close(self) -> None:
        self.stop()

    def status(self) -> dict[str, object]:
        with self._lock:
            workloads: list[dict[str, object]] = []
            foreground_rate = 0.0
            background_rate = 0.0
            for pid in self._live_pids():
                role = self._roles[pid]
                stats = self._read_stats(pid)
                rate = float(stats.get("operations_per_second", 0.0))
                if role == "foreground":
                    foreground_rate += rate
                else:
                    background_rate += rate
                proc = psutil.Process(pid)
                cpu_times = proc.cpu_times()
                cpu_total = float(cpu_times.user + cpu_times.system)
                sampled_at = time.monotonic()
                previous = self._cpu_samples.get(pid)
                cpu_percent = 0.0
                if previous is not None and sampled_at > previous[0]:
                    cpu_percent = 100.0 * (cpu_total - previous[1]) / (sampled_at - previous[0])
                self._cpu_samples[pid] = (sampled_at, cpu_total)
                workloads.append(
                    {
                        "pid": pid,
                        "role": role,
                        "cpu_percent": max(0.0, cpu_percent),
                        "affinity": sorted(proc.cpu_affinity()),
                        "original_affinity": list(self._original_affinity[pid]),
                        "nice": int(proc.nice()),
                        "operations_per_second": rate,
                        "sampled_at": stats.get("sampled_at"),
                    }
                )
            return {
                "supported": self.supported,
                "state": self._mode if workloads else "stopped",
                "worker_count": sum(item["role"] == "background" for item in workloads),
                "foreground_operations_per_second": foreground_rate,
                "background_operations_per_second": background_rate,
                "workloads": workloads,
                "target_token": "arc-resource-lab-background" if workloads else None,
                "policy_cpu": self.policy_cpu(),
            }

    def policy_cpu(self) -> int | None:
        """CPU used by the demo contract, chosen away from foreground when possible."""
        if not self._original_affinity:
            return None
        available = next(iter(self._original_affinity.values()))
        return available[-1]

    def _spawn(self, role: str, index: int) -> None:
        assert self._directory is not None and self._token is not None
        marker = f"arc-resource-lab-{role}"
        stats = self._directory / f"{role}-{index}.json"
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "arc.lab.worker",
                "--role",
                role,
                "--mode-file",
                str(self._directory / "mode"),
                "--stats-file",
                str(stats),
                "--token",
                f"{marker}-{self._token}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._processes[process.pid] = process
        self._roles[process.pid] = role
        self._stats_paths[process.pid] = stats
        self._original_affinity[process.pid] = tuple(
            sorted(psutil.Process(process.pid).cpu_affinity())
        )
        cpu_times = psutil.Process(process.pid).cpu_times()
        self._cpu_samples[process.pid] = (
            time.monotonic(),
            float(cpu_times.user + cpu_times.system),
        )

    def _write_mode(self, mode: str) -> None:
        if self._directory is None:
            return
        (self._directory / "mode").write_text(mode, encoding="utf-8")

    def _read_stats(self, pid: int) -> dict[str, object]:
        if self._directory is None:
            return {}
        path = self._stats_paths[pid]
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _live_pids(self) -> list[int]:
        live = [pid for pid, process in self._processes.items() if process.poll() is None]
        return sorted(live)
