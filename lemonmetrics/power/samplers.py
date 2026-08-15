"""Platform power samplers.

Priority for a given host (best source first):

* ``hwmon``   -- Linux AMD iGPU / CPU power via sysfs (Ryzen AI, Radeon iGPU)
* ``rapl``    -- Intel RAPL energy counters (``energy_uj``)
* ``rocm-smi``-- AMD discrete GPU via the rocm-smi tool
* ``powermetrics`` -- macOS ``powermetrics`` (requires sudo)
* ``null``    -- fallback; marks power unavailable

Every sampler is defensive: if the underlying source disappears mid-run it
simply stops contributing samples.
"""

from __future__ import annotations

import glob
import os
import platform
import re
import shutil
import subprocess
import threading
import time

from lemonmetrics.power.base import PowerSampler
from lemonmetrics.power.privileges import powermetrics_accessible, powermetrics_bin

_MICRO = 1e-6


class NullSampler(PowerSampler):
    """Always-unavailable fallback so runs never hard-fail without power data."""

    name = "null"

    @classmethod
    def detect(cls) -> bool:
        return True

    def read(self) -> float | None:
        return None

    def close(self) -> None:
        pass


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return None


class HwmonSampler(PowerSampler):
    """Linux sysfs hwmon power sensors (AMD CPU/iGPU).

    Reads every ``hwmonN/power1_average`` it can find (typically microwatts on
    Ryzen AI / Radeon iGPU).  Uses the sum of all sources on the same tick so a
    CPU+GPU split appears as one number.
    """

    name = "hwmon"

    def __init__(self, interval: float = 1.0) -> None:
        super().__init__(interval)
        self._sources: list[str] = []
        self._open_failed = False
        self._lock = threading.Lock()

    @classmethod
    def detect(cls) -> bool:
        if platform.system() != "Linux":
            return False
        return bool(cls._find_sources())

    @staticmethod
    def _find_sources() -> list[str]:
        sources = []
        for device in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            power = os.path.join(device, "power1_average")
            if os.path.exists(power):
                sources.append(power)
        return sources

    def start(self) -> None:
        self._sources = self._find_sources()

    def read(self) -> float | None:
        with self._lock:
            if self._open_failed:
                return None
        total = 0.0
        found = False
        for path in self._sources:
            raw = _read(path)
            if raw is None:
                continue
            try:
                total += float(raw) * _MICRO
                found = True
            except ValueError:
                continue
        if not found:
            with self._lock:
                self._open_failed = True
            return None
        return round(total, 3)

    def close(self) -> None:
        self._sources = []


class RaplSampler(PowerSampler):
    """Intel RAPL energy counters on Linux (``/sys/class/powercap``).

    Package energy is monotonic ``energy_uj``; power per tick is derived by
    differentiating the counter.  Uses the ``intel-rapl:0`` package domain.
    """

    name = "rapl"

    def __init__(self, interval: float = 1.0) -> None:
        super().__init__(interval)
        self._energy_path: str | None = None
        self._last_uj: float | None = None
        self._last_ts: float | None = None

    @classmethod
    def detect(cls) -> bool:
        if platform.system() != "Linux":
            return False
        for d in sorted(glob.glob("/sys/class/powercap/intel-rapl*")):
            name = _read(os.path.join(d, "name")) or ""
            if "package" in name or os.path.exists(os.path.join(d, "energy_uj")):
                return True
        return False

    def start(self) -> None:
        candidates = []
        for d in sorted(glob.glob("/sys/class/powercap/intel-rapl:intel-rapl:*")):
            name = _read(os.path.join(d, "name")) or ""
            if "package" in name.lower():
                candidates.append(os.path.join(d, "energy_uj"))
        self._energy_path = candidates[0] if candidates else None
        self._last_uj = None
        self._last_ts = None

    def read(self) -> float | None:
        if not self._energy_path:
            return None
        raw = _read(self._energy_path)
        if raw is None:
            return None
        try:
            uj = float(raw)
        except ValueError:
            return None
        now = time.monotonic()
        if self._last_uj is None or self._last_ts is None:
            self._last_uj, self._last_ts = uj, now
            return None
        dt = now - self._last_ts
        delta = uj - self._last_uj
        if delta < 0:  # counter wrapped
            delta = uj
        self._last_uj, self._last_ts = uj, now
        if dt <= 0:
            return None
        return round(delta * _MICRO / dt, 3)

    def close(self) -> None:
        self._energy_path = None


class RocmSmiSampler(PowerSampler):
    """AMD discrete GPU power via the ``rocm-smi`` CLI on Linux."""

    name = "rocm-smi"

    def __init__(self, interval: float = 1.0) -> None:
        super().__init__(interval)
        self._bin = "rocm-smi"

    @classmethod
    def detect(cls) -> bool:
        if platform.system() != "Linux":
            return False
        if not shutil.which("rocm-smi"):
            return False
        return True

    def read(self) -> float | None:
        try:
            proc = subprocess.run(
                [self._bin, "--showpower", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        m = re.search(r"\"Average Graphics Package Power (Sensor)\"\s*:\s*([\d.]+) W", proc.stdout)
        if not m:
            m = re.search(
                r"\"(?:GPU OverDrive|Power)\"[\s\S]*?\"Value\"\s*:\s*([\d.]+)", proc.stdout
            )
        if not m:
            return None
        try:
            return round(float(m.group(1)), 3)
        except ValueError:
            return None

    def close(self) -> None:
        pass


_POWER_LINE = re.compile(
    r"(?:Combined Power|Intel energy model derived package power)[^:]*:\s+([\d.]+)\s*(m?)W"
)


class WindowsSampler(PowerSampler):
    """Windows power sampler (unavailable).

    Windows lacks a reliable real-time power measurement API for inference workloads.
    Modern Windows systems use energy models (RAPL-like) that are not exposed via
    user-mode APIs. The Energy Meter from Microsoft Research requires kernel
    instrumentation and is not practical for benchmark harnesses.

    As documented in docs/methodology.md, energy metrics are marked unavailable on
    Windows. Run the harness on macOS (powermetrics) or Linux (hwmon/RAPL) for
    power measurements.
    """

    name = "windows"

    @classmethod
    def detect(cls) -> bool:
        return platform.system() == "Windows"

    def read(self) -> float | None:
        return None

    def close(self) -> None:
        pass


class PowermetricsSampler(PowerSampler):
    """macOS ``powermetrics`` (needs root, non-interactive only).

    Runs ``powermetrics -n 1 -i <ms>`` per sample: each invocation samples one
    window, exits, and flushes its output (a long-lived process would
    block-buffer when piped, so fresh values would never arrive).  Handles both
    Apple Silicon (``Combined Power: 1234 mW``) and Intel
    (``Intel energy model derived package power (CPUs+GT+SA): 8.14W``) formats.
    Root access is granted once by :mod:`lemonmetrics.power.privileges`;
    otherwise the sampler degrades to null via :meth:`detect`.
    """

    name = "powermetrics"

    def __init__(self, interval: float = 2.0) -> None:
        super().__init__(interval)
        self._bin = powermetrics_bin() or "powermetrics"

    @classmethod
    def detect(cls) -> bool:
        if platform.system() != "Darwin":
            return False
        if not powermetrics_bin():
            return False
        return powermetrics_accessible()

    def read(self) -> float | None:
        try:
            proc = subprocess.run(
                [
                    "sudo",
                    "-n",
                    self._bin,
                    "-n",
                    "1",
                    "-i",
                    str(int(self.interval * 1000)),
                ],
                capture_output=True,
                text=True,
                timeout=self.interval + 10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        matches = list(_POWER_LINE.finditer(proc.stdout))
        if not matches:
            return None
        m = matches[-1]
        try:
            watts = float(m.group(1))
        except ValueError:
            return None
        if m.group(2) == "m":
            watts /= 1000.0
        return round(watts, 3)

    def close(self) -> None:
        pass


SAMPLER_CLASSES: list[type[PowerSampler]] = [
    HwmonSampler,
    RaplSampler,
    RocmSmiSampler,
    WindowsSampler,
    PowermetricsSampler,
    NullSampler,
]


def detect_sampler(interval: float = 1.0) -> PowerSampler:
    """Return the best available sampler, falling back to :class:`NullSampler`."""
    for cls in SAMPLER_CLASSES:
        try:
            if cls.detect():
                return cls(interval)
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            continue
    return NullSampler(interval)
