"""Report writers: raw JSONL, normalized JSON, and a Markdown summary.

Layout on disk (one directory per run, designed to be PR-mergeable):

    data/results/<device_id>/<run_id>/
        report.json     # full normalized report
        power.jsonl     # raw power samples (one JSON object per line)
        bench.json      # raw lemonade bench --json payload
        summary.md      # human-readable summary
"""

from __future__ import annotations

import json
import os
from typing import Any


def _sample_to_dict(sample: Any) -> dict[str, Any]:
    if hasattr(sample, "ts"):
        return {"ts": sample.ts, "watts": sample.watts}
    return {"ts": sample.get("ts"), "watts": sample.get("watts")}


def write_power_jsonl(samples: list[Any], path: str) -> None:
    """Write power samples as newline-delimited JSON (``ts`` monotonic sec, ``watts``)."""
    with open(path, "w", encoding="utf-8") as fh:
        for sample in samples:
            fh.write(json.dumps(_sample_to_dict(sample)) + "\n")


def render_markdown(report: dict[str, Any]) -> str:
    """Render a human-readable Markdown summary of a report."""
    device = report.get("device", {})
    cpu = device.get("cpu", {})
    lemonade_info = report.get("lemonade", {})
    power = report.get("power", {})
    efficiency = report.get("efficiency", {})
    bench = lemonade_info.get("bench_output", {}) or {}
    wall = report.get("wall", {})

    lines: list[str] = []
    lines.append("# Lemon Metrics Report")
    lines.append("")
    lines.append(f"- **generated_at**: {report.get('generated_at')}")
    lines.append(
        f"- **lemonmetrics**: {report.get('lemonmetrics_version')} "
        f"(schema {report.get('schema_version')})"
    )
    lines.append(f"- **wall duration**: {wall.get('duration_s')}s")
    lines.append("")

    lines.append("## Device")
    lines.append("")
    lines.append(f"- **device_id**: `{device.get('device_id')}`")
    lines.append(f"- **fingerprint**: `{device.get('fingerprint')}`")
    lines.append(f"- **OS**: {device.get('os')} {device.get('os_release')}")
    lines.append(f"- **CPU**: {cpu.get('model')}")
    lines.append(
        f"- **cores**: {cpu.get('physical_cores')} physical / {cpu.get('logical_cores')} logical"
    )
    lines.append(f"- **memory**: {device.get('memory_gb')} GB")
    if device.get("gpu"):
        lines.append(f"- **GPU**: {', '.join(device['gpu'])}")
    if device.get("npu"):
        lines.append(f"- **NPU**: {', '.join(device['npu'])}")
    lines.append("")

    env = report.get("environment", {})
    lines.append("## Environment")
    lines.append("")
    lines.append(f"- **power source**: {env.get('power_source')}")
    if env.get("battery_percent") is not None:
        lines.append(f"- **battery**: {env['battery_percent']}%")
    if env.get("cpu_governor"):
        lines.append(f"- **cpu governor**: {env['cpu_governor']}")
    if env.get("thermal_celsius") is not None:
        lines.append(f"- **thermal**: {env['thermal_celsius']} C")
    lines.append("")

    lines.append("## Power")
    lines.append("")
    if power.get("available"):
        lines.append(f"- **sampler**: {power.get('sampler')}")
        lines.append(f"- **samples**: {power.get('samples')}")
        lines.append(f"- **avg**: {power.get('avg_watts')} W")
        lines.append(f"- **min / peak**: {power.get('min_watts')} / {power.get('max_watts')} W")
        lines.append(f"- **energy (wall)**: {power.get('energy_joules')} J")
    else:
        lines.append("- power unavailable (no supported source found)")
    baseline = power.get("baseline") or {}
    if baseline.get("avg_watts") is not None:
        lines.append(
            f"- **baseline (idle)**: {baseline['avg_watts']} W over {baseline.get('duration_s')}s"
        )
    lines.append("")

    lines.append("## Energy Efficiency")
    lines.append("")
    if efficiency.get("available"):
        lines.append(f"- **J/token** (all): {efficiency.get('joules_per_token')}")
        lines.append(f"- **J/output token**: {efficiency.get('joules_per_output_token')}")
        lines.append(f"- **tokens/kWh**: {efficiency.get('tokens_per_kwh')}")
        lines.append(f"- **total tokens**: {efficiency.get('total_tokens')}")
        if efficiency.get("incremental_joules_per_token") is not None:
            lines.append(
                f"- **J/token (incremental)**: {efficiency.get('incremental_joules_per_token')}"
            )
            lines.append(
                f"- **tokens/kWh (incremental)**: {efficiency.get('incremental_tokens_per_kwh')}"
            )
    else:
        lines.append("- not computed (no power data)")
    lines.append("")

    scenarios = efficiency.get("by_scenario") or []
    if scenarios:
        lines.append("## Per-Scenario")
        lines.append("")
        lines.append("| scenario | category | in tok | out tok | tps | ttft ms | est. J/token |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
        for s in scenarios:
            jpt = s.get("estimated_joules_per_token")
            jpt_s = "-" if jpt is None else f"{jpt:.4f}"
            tps_s = "-" if s.get("tps") is None else f"{s['tps']:.1f}"
            ttft_s = "-" if s.get("ttft_ms") is None else f"{s['ttft_ms']:.1f}"
            lines.append(
                f"| {s.get('name')} | {s.get('category')} | {s.get('input_tokens')} "
                f"| {s.get('output_tokens')} | {tps_s} | {ttft_s} | {jpt_s} |"
            )
        lines.append("")
        lines.append(f"> {efficiency.get('note')}")
        lines.append("")

    bench_hw = bench.get("hardware", {})
    if bench_hw:
        lines.append("## Lemonade Bench Hardware")
        lines.append("")
        lines.append(f"- **cpu**: {bench_hw.get('cpu')}")
        lines.append(f"- **ram**: {bench_hw.get('ram_gb')} GB")
        lines.append(f"- **os**: {bench_hw.get('os')}")
        if bench_hw.get("backends"):
            lines.append(f"- **backends**: {bench_hw.get('backends')}")
        lines.append("")

    cmd = lemonade_info.get("command") or []
    lines.append("## Command")
    lines.append("")
    lines.append(f"```\n{' '.join(cmd)}\n```")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], base_dir: str) -> dict[str, str]:
    """Write report.json, power.jsonl, bench.json, summary.md for a run.

    Returns a map of logical name -> absolute path.
    """
    device_id = report.get("device", {}).get("device_id") or "unknown"
    run_id = (report.get("wall", {}).get("started_at") or "run").replace(":", "-")
    run_dir = os.path.join(base_dir, device_id, run_id)
    os.makedirs(run_dir, exist_ok=True)

    paths: dict[str, str] = {}
    report_path = os.path.join(run_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    paths["report"] = report_path

    samples = report.get("power", {}).get("samples_raw", [])
    if samples:
        power_path = os.path.join(run_dir, "power.jsonl")
        write_power_jsonl(samples, power_path)
        paths["power"] = power_path

    baseline_samples = report.get("power", {}).get("baseline", {}).get("samples_raw", [])
    if baseline_samples:
        baseline_path = os.path.join(run_dir, "baseline.jsonl")
        write_power_jsonl(baseline_samples, baseline_path)
        paths["baseline"] = baseline_path

    bench = report.get("lemonade", {}).get("bench_output")
    if bench:
        bench_path = os.path.join(run_dir, "bench.json")
        with open(bench_path, "w", encoding="utf-8") as fh:
            json.dump(bench, fh, indent=2, sort_keys=True)
        paths["bench"] = bench_path

    md_path = os.path.join(run_dir, "summary.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))
    paths["summary"] = md_path
    return paths
