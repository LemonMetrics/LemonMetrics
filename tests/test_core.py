"""Tests for the benchmark runner (core.py)."""

import json

import pytest

from lemonmetrics import core
from tests.fixtures import BENCH_JSON, STDOUT_WITH_PREFIX
from tests.test_power import FixedSampler


def test_extract_stdout_json():
    parsed = core._extract_stdout_json(STDOUT_WITH_PREFIX)
    assert parsed["models"][0]["model"] == "Qwen3-0.6B-GGUF"
    assert parsed["hardware"]["cpu"].startswith("Intel")


def test_extract_stdout_json_raises_on_no_json():
    with pytest.raises(ValueError):
        core._extract_stdout_json("no json here")


def test_compute_efficiency_no_power():
    eff = core.compute_efficiency(BENCH_JSON, {"available": False})
    assert eff["available"] is False


def test_measure_baseline_collects_samples():
    sampler = FixedSampler(15.0, interval=0.05)
    baseline = core._measure_baseline(sampler, interval=0.05, duration=0.25)
    assert baseline is not None
    assert baseline["avg_watts"] == 15.0
    assert baseline["samples"] >= 2
    assert len(baseline["samples_raw"]) == baseline["samples"]
    assert len(sampler.samples()) == baseline["samples"]
    sampler.clear()
    assert sampler.samples() == []


def test_measure_baseline_null_sampler_returns_none():
    from lemonmetrics.power import NullSampler

    baseline = core._measure_baseline(NullSampler(), interval=0.05, duration=0.1)
    assert baseline is None


def test_compute_efficiency_with_baseline():
    power = {
        "available": True,
        "sampler": "fixed",
        "avg_watts": 30.0,
        "max_watts": 35.0,
        "duration_s": 10.0,
        "baseline": {"avg_watts": 10.0, "duration_s": 5.0},
    }
    eff = core.compute_efficiency(BENCH_JSON, power)
    assert eff["available"] is True
    assert eff["baseline_watts"] == 10.0
    assert eff["incremental_watts"] == 20.0
    assert eff["incremental_energy_joules"] == pytest.approx(200.0, rel=1e-3)
    total_tokens = 27 + 44 + 20 + 256
    assert eff["incremental_joules_per_token"] == pytest.approx(200.0 / total_tokens, rel=1e-3)
    assert eff["incremental_tokens_per_kwh"] == pytest.approx(
        3.6e6 * total_tokens / 200.0, rel=1e-3
    )
    assert "incremental" in eff["note"]


def test_compute_efficiency_baseline_higher_than_avg_clamps_zero():
    power = {
        "available": True,
        "sampler": "fixed",
        "avg_watts": 5.0,
        "max_watts": 8.0,
        "duration_s": 10.0,
        "baseline": {"avg_watts": 10.0, "duration_s": 5.0},
    }
    eff = core.compute_efficiency(BENCH_JSON, power)
    assert eff["incremental_watts"] == 0.0
    assert eff["incremental_energy_joules"] == 0.0
    assert eff["incremental_tokens_per_kwh"] is None


def test_compute_efficiency_without_baseline_has_no_incremental():
    power = {
        "available": True,
        "sampler": "fixed",
        "avg_watts": 25.0,
        "max_watts": 30.0,
        "duration_s": 10.0,
    }
    eff = core.compute_efficiency(BENCH_JSON, power)
    assert "incremental_watts" not in eff
    assert "incremental" not in eff["note"]


def test_compute_efficiency_with_power():
    power = {
        "available": True,
        "sampler": "fixed",
        "samples": 10,
        "avg_watts": 25.0,
        "min_watts": 20.0,
        "max_watts": 30.0,
        "duration_s": 6.16,  # sum of both scenario means (0.512 + 5.653)
    }
    eff = core.compute_efficiency(BENCH_JSON, power)
    assert eff["available"] is True
    assert eff["total_input_tokens"] == 27 + 44
    assert eff["total_output_tokens"] == 20 + 256
    assert eff["total_tokens"] == 27 + 44 + 20 + 256
    # avg 25 W over 6.16 s => 154 J wall
    assert eff["wall_energy_joules"] == pytest.approx(25.0 * 6.16, rel=1e-3)
    assert eff["joules_per_token"] == pytest.approx(25.0 * 6.16 / (27 + 44 + 20 + 256), rel=1e-3)
    # per-scenario energy: 25 W * duration
    assert len(eff["by_scenario"]) == 2
    s0 = eff["by_scenario"][0]
    assert s0["estimated_energy_joules"] == pytest.approx(25.0 * 0.5119, rel=1e-3)
    assert s0["estimated_joules_per_token"] == pytest.approx(25.0 * 0.5119 / (27 + 20), rel=1e-3)
    assert "note" in eff


def test_bench_command_build():
    cmd = core.lemonade.bench_command(
        "Qwen3-0.6B-GGUF", backend="cpu", runs=3, output="/tmp/x.json"
    )
    assert cmd == [
        "bench",
        "Qwen3-0.6B-GGUF",
        "--backend",
        "cpu",
        "--runs",
        "3",
        "--json",
        "--output",
        "/tmp/x.json",
    ]


def test_bench_command_optional_flags():
    cmd = core.lemonade.bench_command("M", ctx_size=2048, warmup=1, no_reload=True, auto_pull=True)
    assert "--ctx-size" in cmd and "2048" in cmd
    assert "--warmup" in cmd and "1" in cmd
    assert "--no-reload" in cmd
    assert "--auto-pull" in cmd


def test_report_schema_fields_present():
    report = {
        "schema_version": core.SCHEMA_VERSION,
        "lemonmetrics_version": "1.0.0",
        "generated_at": "t",
        "wall": {"started_at": "t", "finished_at": "t", "duration_s": 1.0},
        "device": {"device_id": "test", "fingerprint": "abc"},
        "environment": {},
        "lemonade": {},
        "power": {"available": False},
        "efficiency": {"available": False},
    }
    # report must be JSON-serializable
    json.dumps(report)
    assert report["schema_version"] == "1.0"
