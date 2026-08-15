"""Power sampler abstraction and background sampling loop.

Samplers poll a platform power source (powermetrics, hwmon sysfs, RAPL, ...)
and produce ``(timestamp, watts)`` samples.  When no usable source exists the
``null`` sampler reports ``available=False`` and the harness records
``power_available: false`` instead of failing the run.
"""

from __future__ import annotations

import abc
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class Sample:
    ts: float
    watts: float


class PowerSampler(abc.ABC):
    """A single platform power source.

    Instances are stateful: call :meth:`start` once, read samples as they
    arrive, then :meth:`stop`.  Implementations must be safe to run from the
    background sampling thread.
    """

    name = "base"

    @classmethod
    @abc.abstractmethod
    def detect(cls) -> bool:
        """Return True if this sampler can read power on the current host."""

    def __init__(self, interval: float = 1.0) -> None:
        self.interval = interval
        self._samples: list[Sample] = []
        self._lock = threading.Lock()

    @abc.abstractmethod
    def read(self) -> float | None:
        """Return current power in watts, or None if unavailable."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release any resources (processes, handles)."""

    def start(self) -> None:
        """Begin sampling (called before the benchmark starts)."""

    def stop(self) -> None:
        """Stop sampling (called after the benchmark finishes)."""

    def add(self, ts: float, watts: float) -> None:
        with self._lock:
            self._samples.append(Sample(ts, watts))

    def samples(self) -> list[Sample]:
        with self._lock:
            return list(self._samples)

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()

    def summary(self) -> dict[str, Any]:
        samples = self.samples()
        if not samples:
            return {"available": False, "sampler": self.name, "samples": 0}
        watts = [s.watts for s in samples]
        total_s = samples[-1].ts - samples[0].ts if len(samples) > 1 else 0.0
        avg_w = sum(watts) / len(watts)
        return {
            "available": True,
            "sampler": self.name,
            "samples": len(samples),
            "duration_s": round(total_s, 3),
            "avg_watts": round(avg_w, 3),
            "min_watts": round(min(watts), 3),
            "max_watts": round(max(watts), 3),
            "energy_joules": round(avg_w * total_s, 3),
        }


class BackgroundSampler:
    """Drives a :class:`PowerSampler` from a daemon thread at a fixed interval."""

    def __init__(self, sampler: PowerSampler, interval: float = 1.0) -> None:
        self.sampler = sampler
        self.interval = interval if interval > 0 else sampler.interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.sampler.start()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name=f"lemonmetrics-power-{self.sampler.name}", daemon=True
        )
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            start = time.monotonic()
            try:
                watts = self.sampler.read()
            except Exception:
                watts = None
            if watts is not None and watts >= 0:
                self.sampler.add(time.monotonic(), watts)
            remaining = self.interval - (time.monotonic() - start)
            if remaining > 0:
                self._stop.wait(remaining)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 2 + 1)
        self.sampler.stop()

    def summary(self) -> dict[str, Any]:
        return self.sampler.summary()
