"""Tests for report writers."""

import json

import pytest

from lemonmetrics import report
from tests.fixtures import BENCH_JSON


def _report(**overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "lemonmetrics_version": "1.0.0",
        "generated_at": "2026-08-09T12:00:00+00:00",
        "wall": {
            "started_at": "2026-08-09T11:59:00+00:00",
            "finished_at": "2026-08-09T12:00:00+00:00",
            "duration_s": 60.0,
        },
        "device": {"device_id": "test-box", "fingerprint": "abc123", "os": "linux"},
        "environment": {"power_source": "ac"},
        "lemonade": {
            "cli_version": "11.5.2",
            "command": ["bench", "Qwen3-0.6B-GGUF"],
            "bench_output": BENCH_JSON,
        },
        "power": {
            "available": True,
            "sampler": "fixed",
            "samples": 5,
            "avg_watts": 25.0,
            "min_watts": 20.0,
            "max_watts": 30.0,
            "duration_s": 6.0,
            "energy_joules": 150.0,
        },
        "efficiency": {
            "available": True,
            "joules_per_token": 0.1,
            "tokens_per_kwh": 1000.0,
            "by_scenario": [
                {
                    "name": "chat-short",
                    "category": "chat",
                    "input_tokens": 27,
                    "output_tokens": 20,
                    "tps": 50.5,
                    "ttft_ms": 99.4,
                    "estimated_joules_per_token": 0.05,
                }
            ],
        },
    }
    base.update(overrides)
    return base


def test_write_report_creates_files(tmp_path):
    paths = report.write_report(_report(), str(tmp_path))
    assert paths["report"].endswith("report.json")
    assert paths["summary"].endswith("summary.md")
    assert paths["bench"].endswith("bench.json")
    assert "power" not in paths  # no raw samples supplied
    with open(paths["report"], encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["device"]["device_id"] == "test-box"


def test_write_report_writes_power_jsonl(tmp_path):
    rep = _report()
    rep["power"]["samples_raw"] = [
        {"ts": 1.0, "watts": 20.0},
        {"ts": 2.0, "watts": 30.0},
    ]
    paths = report.write_report(rep, str(tmp_path))
    with open(paths["power"], encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"ts": 1.0, "watts": 20.0}


def test_write_report_writes_baseline_jsonl(tmp_path):
    rep = _report()
    rep["power"]["baseline"] = {
        "avg_watts": 10.0,
        "duration_s": 5.0,
        "samples_raw": [{"ts": 1.0, "watts": 10.0}, {"ts": 2.0, "watts": 10.0}],
    }
    paths = report.write_report(rep, str(tmp_path))
    with open(paths["baseline"], encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"ts": 1.0, "watts": 10.0}


def test_render_markdown_includes_sections():
    md = report.render_markdown(_report())
    assert "# Lemon Metrics Report" in md
    assert "## Device" in md
    assert "## Power" in md
    assert "**avg**: 25.0 W" in md
    assert "## Energy Efficiency" in md
    assert "**J/token**" in md
    assert "## Per-Scenario" in md
    assert "chat-short" in md
    assert "## Command" in md


def test_render_markdown_power_unavailable():
    md = report.render_markdown(
        _report(power={"available": False}, efficiency={"available": False})
    )
    assert "power unavailable" in md
    assert "not computed" in md


def test_render_markdown_includes_baseline_and_incremental():
    rep = _report()
    rep["power"]["baseline"] = {"avg_watts": 10.0, "duration_s": 5.0}
    rep["efficiency"]["incremental_joules_per_token"] = 0.05
    rep["efficiency"]["incremental_tokens_per_kwh"] = 999.0
    md = report.render_markdown(rep)
    assert "**baseline (idle)**: 10.0 W over 5.0s" in md
    assert "**J/token (incremental)**: 0.05" in md
    assert "**tokens/kWh (incremental)**: 999.0" in md


def test_render_markdown_power_only():
    md = report.render_markdown(_report(power={"available": True, "avg_watts": 42.0}))
    assert "42.0 W" in md


@pytest.mark.parametrize("power_available", [True, False])
def test_write_power_jsonl_single_sample(tmp_path, power_available):
    rep = _report(power={"available": power_available})
    rep["power"]["samples_raw"] = [{"ts": 1.0, "watts": 10.0}]
    paths = report.write_report(rep, str(tmp_path))
    assert "power" in paths
