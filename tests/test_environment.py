"""Tests for the ambient environment snapshot (AC/battery, Windows safety)."""

import lemonmetrics.environment as env


def _nowindows(monkeypatch):
    monkeypatch.setattr(env.os.path, "isdir", lambda _p: False)


def test_power_source_windows_ac(monkeypatch):
    _nowindows(monkeypatch)
    monkeypatch.setattr(env.platform, "system", lambda: "Windows")
    monkeypatch.setattr(env, "_run", lambda _args: "2")
    assert env.power_source() == "ac"


def test_power_source_windows_battery(monkeypatch):
    _nowindows(monkeypatch)
    monkeypatch.setattr(env.platform, "system", lambda: "Windows")
    monkeypatch.setattr(env, "_run", lambda _args: "1")
    assert env.power_source() == "battery"


def test_power_source_windows_unknown(monkeypatch):
    _nowindows(monkeypatch)
    monkeypatch.setattr(env.platform, "system", lambda: "Windows")
    monkeypatch.setattr(env, "_run", lambda _args: "")
    assert env.power_source() == "unknown"


def test_battery_percent_windows(monkeypatch):
    _nowindows(monkeypatch)
    monkeypatch.setattr(env.platform, "system", lambda: "Windows")
    monkeypatch.setattr(env, "_run", lambda _args: "73")
    assert env.battery_percent() == 73


def test_battery_percent_windows_missing(monkeypatch):
    _nowindows(monkeypatch)
    monkeypatch.setattr(env.platform, "system", lambda: "Windows")
    monkeypatch.setattr(env, "_run", lambda _args: "")
    assert env.battery_percent() is None


def test_power_source_darwin_ac(monkeypatch):
    _nowindows(monkeypatch)
    monkeypatch.setattr(env.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(env, "_run", lambda _args: "Now drawing from 'AC Power'")
    assert env.power_source() == "ac"


def test_battery_percent_darwin(monkeypatch):
    _nowindows(monkeypatch)
    monkeypatch.setattr(env.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(env, "_run", lambda _args: "86%; discharging")
    assert env.battery_percent() == 86


def test_windows_host_does_not_require_os_uname(monkeypatch):
    _nowindows(monkeypatch)
    monkeypatch.setattr(env.platform, "system", lambda: "Windows")
    monkeypatch.setattr(env, "_run", lambda _args: "")
    assert env.power_source() == "unknown"
    assert env.battery_percent() is None
