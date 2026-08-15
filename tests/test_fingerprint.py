"""Tests for machine fingerprinting (incl. Windows branches)."""

import lemonmetrics.fingerprint as fp


def test_cpu_model_windows(monkeypatch):
    monkeypatch.setattr(fp.platform, "system", lambda: "Windows")
    monkeypatch.setattr(fp, "_run", lambda _args: "AMD Ryzen 9 7945HX with Radeon Graphics")
    assert fp.cpu_model() == "AMD Ryzen 9 7945HX with Radeon Graphics"


def test_cpu_model_windows_empty_falls_back(monkeypatch):
    monkeypatch.setattr(fp.platform, "system", lambda: "Windows")
    monkeypatch.setattr(fp.platform, "processor", lambda: "AMD64 Family 25")
    monkeypatch.setattr(fp, "_run", lambda _args: "")
    assert fp.cpu_model() == "AMD64 Family 25"


def test_physical_core_count_windows(monkeypatch):
    monkeypatch.setattr(fp.platform, "system", lambda: "Windows")
    monkeypatch.setattr(fp, "_run", lambda _args: "8")
    assert fp.physical_core_count() == 8


def test_physical_core_count_windows_missing(monkeypatch):
    monkeypatch.setattr(fp.platform, "system", lambda: "Windows")
    monkeypatch.setattr(fp, "_run", lambda _args: "")
    monkeypatch.setattr(fp.os, "cpu_count", lambda: 16)
    assert fp.physical_core_count() == 16


def test_memory_gb_windows(monkeypatch):
    monkeypatch.setattr(fp.platform, "system", lambda: "Windows")
    monkeypatch.setattr(fp, "_run", lambda _args: str(32 * 1024**3))
    assert fp.memory_gb() == 32.0


def test_memory_gb_windows_missing(monkeypatch):
    monkeypatch.setattr(fp.platform, "system", lambda: "Windows")
    monkeypatch.setattr(fp, "_run", lambda _args: "")
    assert fp.memory_gb() == 0.0


def test_gpu_list_windows(monkeypatch):
    monkeypatch.setattr(fp.platform, "system", lambda: "Windows")
    monkeypatch.setattr(fp, "_run", lambda _args: "AMD Radeon 780M\nNVIDIA RTX 4070")
    assert fp.gpu_list() == ["AMD Radeon 780M", "NVIDIA RTX 4070"]


def test_gpu_list_windows_empty(monkeypatch):
    monkeypatch.setattr(fp.platform, "system", lambda: "Windows")
    monkeypatch.setattr(fp, "_run", lambda _args: "")
    assert fp.gpu_list() == []
