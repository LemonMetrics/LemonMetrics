"""Tests for the power sampling package."""

import time

from lemonmetrics.power import BackgroundSampler, NullSampler, PowerSampler
from lemonmetrics.power.samplers import SAMPLER_CLASSES, PowermetricsSampler, detect_sampler


class FixedSampler(PowerSampler):
    """Test sampler that always reports a fixed wattage."""

    name = "fixed"

    @classmethod
    def detect(cls) -> bool:
        return True

    def __init__(self, watts: float, interval: float = 1.0) -> None:
        super().__init__(interval)
        self._watts = watts
        self._closes = 0

    def read(self) -> float | None:
        return self._watts

    def close(self) -> None:
        self._closes += 1


def test_null_sampler():
    sampler = NullSampler()
    assert sampler.name == "null"
    assert sampler.read() is None
    summary = sampler.summary()
    assert summary["available"] is False
    assert summary["samples"] == 0


def test_summary_math():
    sampler = FixedSampler(10.0)
    now = time.monotonic()
    sampler.add(now, 10.0)
    sampler.add(now + 1.0, 20.0)
    sampler.add(now + 2.0, 30.0)
    summary = sampler.summary()
    assert summary["available"] is True
    assert summary["avg_watts"] == 20.0
    assert summary["max_watts"] == 30.0
    assert summary["min_watts"] == 10.0
    assert summary["energy_joules"] == 40.0  # 20 W x 2 s


def test_background_sampler_collects_samples():
    sampler = FixedSampler(42.0)
    bg = BackgroundSampler(sampler, interval=0.05)
    bg.start()
    time.sleep(0.3)
    bg.stop()
    assert len(sampler.samples()) >= 2
    assert all(s.watts == 42.0 for s in sampler.samples())


def test_background_sampler_stops_cleanly_when_never_started():
    sampler = FixedSampler(1.0)
    bg = BackgroundSampler(sampler, interval=0.05)
    bg.stop()  # should not raise
    assert sampler.samples() == []


def test_detect_sampler_returns_a_sampler():
    sampler = detect_sampler()
    assert isinstance(sampler, PowerSampler)
    assert sampler.name in {cls.name for cls in SAMPLER_CLASSES}
    sampler.close()


def test_null_is_last_in_priority():
    assert SAMPLER_CLASSES[-1] is NullSampler


def test_clear_removes_samples():
    sampler = FixedSampler(10.0)
    now = time.monotonic()
    sampler.add(now, 10.0)
    sampler.add(now + 1.0, 12.0)
    assert len(sampler.samples()) == 2
    sampler.clear()
    assert sampler.samples() == []


def test_powermetrics_detect_delegates_to_privileges(monkeypatch):
    import lemonmetrics.power.samplers as samplers_mod

    monkeypatch.setattr(samplers_mod.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(samplers_mod, "powermetrics_bin", lambda: "/usr/bin/powermetrics")

    monkeypatch.setattr(samplers_mod, "powermetrics_accessible", lambda: True)
    assert PowermetricsSampler.detect() is True

    monkeypatch.setattr(samplers_mod, "powermetrics_accessible", lambda: False)
    assert PowermetricsSampler.detect() is False

    monkeypatch.setattr(samplers_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(samplers_mod, "powermetrics_accessible", lambda: True)
    assert PowermetricsSampler.detect() is False


def _stub_powermetrics(monkeypatch, stdout="", returncode=0):
    import lemonmetrics.power.samplers as samplers_mod

    class _Result:
        def __init__(self):
            self.stdout = stdout
            self.returncode = returncode

    monkeypatch.setattr(samplers_mod.subprocess, "run", lambda *a, **k: _Result())
    return _Result


def test_powermetrics_read_parses_intel_watts(monkeypatch):
    _stub_powermetrics(
        monkeypatch,
        "*** Sampled system activity ***\n"
        "Intel energy model derived package power (CPUs+GT+SA): 8.14W\n",
    )
    sampler = PowermetricsSampler(interval=1.0)
    assert sampler.read() == 8.14


def test_powermetrics_read_parses_apple_silicon_milliwatts(monkeypatch):
    _stub_powermetrics(monkeypatch, "Combined Power: 1234 mW\n")
    sampler = PowermetricsSampler(interval=1.0)
    assert sampler.read() == 1.234


def test_powermetrics_read_takes_last_power_line(monkeypatch):
    _stub_powermetrics(monkeypatch, "Combined Power: 1000 mW\nCombined Power: 2500 mW\n")
    sampler = PowermetricsSampler(interval=1.0)
    assert sampler.read() == 2.5


def test_powermetrics_read_returns_none_without_power_line(monkeypatch):
    _stub_powermetrics(monkeypatch, "some unrelated output\n")
    sampler = PowermetricsSampler(interval=1.0)
    assert sampler.read() is None


def test_powermetrics_read_returns_none_on_failure(monkeypatch):
    _stub_powermetrics(monkeypatch, "denied", returncode=1)
    sampler = PowermetricsSampler(interval=1.0)
    assert sampler.read() is None
