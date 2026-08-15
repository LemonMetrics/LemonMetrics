"""Benchmark orchestration: run lemonade bench while sampling power.

Produces a single report dict combining:

* machine fingerprint (:mod:`lemonmetrics.fingerprint`)
* ambient snapshot (:mod:`lemonmetrics.environment`)
* raw ``lemonade bench --json`` output
* power summary + energy-efficiency metrics

Power is measured wall-clock alongside the bench.  Because ``lemonade bench``
also spends time loading models between scenarios, per-scenario energy is an
estimate (avg power x scenario duration) and is labelled as such.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import tempfile
import time
from typing import Any

import lemonmetrics
from lemonmetrics import environment, fingerprint, lemonade
from lemonmetrics.power import BackgroundSampler, detect_sampler

SCHEMA_VERSION = "1.0"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _extract_stdout_json(stdout: str) -> dict[str, Any]:
    """Pull the trailing JSON object out of ``lemonade bench --json`` stdout.

    The CLI prints a human-readable summary followed by the JSON payload.  The
    payload starts with a standalone ``{`` line; we walk backwards through those
    candidates so nested objects inside compact JSON can't confuse the parse.
    """
    lines = stdout.splitlines()
    candidates = [i for i, line in enumerate(lines) if line.strip() == "{"]
    for idx in reversed(candidates):
        try:
            return json.loads("\n".join(lines[idx:]))
        except json.JSONDecodeError:
            continue
    for idx, ch in enumerate(stdout):
        if ch == "{":
            try:
                return json.loads(stdout[idx:])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON object found in bench output")


def _measure_baseline(sampler: Any, interval: float, duration: float) -> dict[str, Any] | None:
    """Sample idle power before the bench (container running, no workload).

    Returns a summary with raw samples so it can be written to ``baseline.jsonl``.
    """
    bg = BackgroundSampler(sampler, interval=interval)
    bg.start()
    try:
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            time.sleep(0.1)
    finally:
        bg.stop()
    summary = sampler.summary()
    if not summary.get("available"):
        return None
    return {
        "avg_watts": summary.get("avg_watts"),
        "min_watts": summary.get("min_watts"),
        "max_watts": summary.get("max_watts"),
        "samples": summary.get("samples"),
        "duration_s": summary.get("duration_s"),
        "samples_raw": [{"ts": s.ts, "watts": s.watts} for s in sampler.samples()],
    }


def run_bench(
    model: str,
    *,
    backend: str | None = None,
    ctx_size: int | None = None,
    runs: int = 3,
    warmup: int = 0,
    extra_args: list[str] | None = None,
    power_interval: float = 1.0,
    baseline_duration: float = 10.0,
    no_reload: bool = False,
    auto_pull: bool = True,
    bench_timeout: int = 3600,
) -> dict[str, Any]:
    """Run one ``lemonade bench`` while sampling power; return a report dict."""
    if not lemonade.cli_available():
        raise RuntimeError(
            "lemonade CLI not found. Set LEMONADE_BIN or install the CLI "
            "(see docs/run-it-yourself.md)."
        )

    bench_json: dict[str, Any] | None = None
    stdout_payload = ""
    in_docker = lemonade.in_docker()
    cmd = lemonade.bench_command(
        model,
        backend=backend,
        ctx_size=ctx_size,
        runs=runs,
        warmup=warmup,
        no_reload=no_reload,
        auto_pull=auto_pull,
        extra_args=extra_args,
    )

    tmp_dir = tempfile.mkdtemp(prefix="lemonmetrics-")
    output_path = os.path.join(tmp_dir, "bench.json")
    if in_docker:
        cmd += ["--output", lemonade.CONTAINER_BENCH_OUTPUT]

    sampler = detect_sampler(interval=power_interval)
    if sampler.name == "null" and environment.containerized():
        print(
            "warning: the harness is running inside a container; power samples would "
            "reflect the Linux VM, not your host laptop. Run the harness on the host "
            "machine instead (see docs/run-it-yourself.md).",
            file=sys.stderr,
        )

    baseline: dict[str, Any] | None = None
    if baseline_duration > 0 and sampler.name != "null":
        baseline = _measure_baseline(sampler, interval=power_interval, duration=baseline_duration)
        sampler.clear()
        if baseline is not None:
            print(
                f"baseline idle power: {baseline['avg_watts']} W over {baseline['duration_s']}s",
                file=sys.stderr,
            )

    bg = BackgroundSampler(sampler, interval=power_interval)

    try:
        bg.start()
        started = _dt.datetime.now(_dt.timezone.utc)
        proc = lemonade.run_cli(cmd, timeout=bench_timeout)
        finished = _dt.datetime.now(_dt.timezone.utc)
    finally:
        bg.stop()
        sampler.close()

    if proc.returncode != 0:
        raise RuntimeError(
            f"lemonade bench failed (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )

    if in_docker:
        try:
            bench_json = json.loads(lemonade.container_read_file(lemonade.CONTAINER_BENCH_OUTPUT))
        except (RuntimeError, json.JSONDecodeError):
            bench_json = None
    elif os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as fh:
            bench_json = json.load(fh)

    if bench_json is None:
        stdout_payload = proc.stdout
        bench_json = _extract_stdout_json(proc.stdout)

    power = bg.summary()
    raw_samples = bg.sampler.samples()
    if raw_samples:
        power["samples_raw"] = [{"ts": s.ts, "watts": s.watts} for s in raw_samples]
    if baseline is not None:
        power["baseline"] = baseline
    efficiency = compute_efficiency(bench_json, power)
    return _assemble_report(
        cmd=cmd,
        model=model,
        backend=backend,
        bench_json=bench_json,
        power=power,
        efficiency=efficiency,
        wall_started=started,
        wall_finished=finished,
        bench_returncode=proc.returncode,
        stdout_payload=stdout_payload,
    )


def compute_efficiency(bench_json: dict[str, Any], power: dict[str, Any]) -> dict[str, Any]:
    """Derive J/token metrics from bench JSON + power summary.

    Per-scenario energy is ``avg_watts x scenario_duration`` and therefore
    *excludes* model-load overhead between scenarios (labelled estimate).
    """
    if not power.get("available") or not power.get("avg_watts"):
        return {"available": False, "note": "no power source available"}

    avg_watts = power["avg_watts"]
    total_input = 0
    total_output = 0
    by_scenario: list[dict[str, Any]] = []

    for model_entry in bench_json.get("models", []):
        for result in model_entry.get("results", []):
            for scenario in result.get("scenarios", []):
                out_tok = scenario.get("output_tokens") or 0
                in_tok = scenario.get("input_tokens") or 0
                total_input += in_tok
                total_output += out_tok
                duration_s = scenario.get("duration_ms", {}).get("mean", 0.0) / 1000.0
                energy = avg_watts * duration_s
                tokens = in_tok + out_tok
                by_scenario.append(
                    {
                        "name": scenario.get("name"),
                        "category": scenario.get("category"),
                        "backend": result.get("backend"),
                        "recipe": result.get("recipe"),
                        "duration_s": round(duration_s, 3),
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "estimated_energy_joules": round(energy, 3),
                        "estimated_joules_per_token": round(energy / tokens, 4) if tokens else None,
                        "estimated_joules_per_output_token": round(energy / out_tok, 4)
                        if out_tok
                        else None,
                        "tps": scenario.get("tps", {}).get("mean"),
                        "ttft_ms": scenario.get("ttft_ms", {}).get("mean"),
                        "memory_peak_gb": scenario.get("memory_peak_gb"),
                    }
                )

    total_tokens = total_input + total_output
    total_energy = avg_watts * (power.get("duration_s") or 0.0)
    efficiency = {
        "available": True,
        "avg_watts": avg_watts,
        "peak_watts": power.get("max_watts"),
        "wall_energy_joules": round(total_energy, 3),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_tokens,
        "joules_per_token": round(total_energy / total_tokens, 4) if total_tokens else None,
        "joules_per_output_token": round(total_energy / total_output, 4) if total_output else None,
        "tokens_per_kwh": round(3.6e6 * total_tokens / total_energy, 2) if total_energy else None,
        "by_scenario": by_scenario,
        "note": (
            "per-scenario energy is avg power x scenario duration and excludes model-load overhead"
        ),
    }

    baseline_avg = (power.get("baseline") or {}).get("avg_watts")
    if baseline_avg:
        incremental_watts = max(avg_watts - baseline_avg, 0.0)
        incremental_energy = incremental_watts * (power.get("duration_s") or 0.0)
        efficiency["baseline_watts"] = round(baseline_avg, 3)
        efficiency["incremental_watts"] = round(incremental_watts, 3)
        efficiency["incremental_energy_joules"] = round(incremental_energy, 3)
        efficiency["incremental_joules_per_token"] = (
            round(incremental_energy / total_tokens, 4) if total_tokens else None
        )
        efficiency["incremental_joules_per_output_token"] = (
            round(incremental_energy / total_output, 4) if total_output else None
        )
        efficiency["incremental_tokens_per_kwh"] = (
            round(3.6e6 * total_tokens / incremental_energy, 2) if incremental_energy else None
        )
        efficiency["note"] += (
            f"; incremental metrics subtract the idle baseline ({round(baseline_avg, 3)} W) "
            "and are estimates"
        )
    return efficiency


def _assemble_report(
    *,
    cmd: list[str],
    model: str,
    backend: str | None,
    bench_json: dict[str, Any],
    power: dict[str, Any],
    efficiency: dict[str, Any],
    wall_started: _dt.datetime,
    wall_finished: _dt.datetime,
    bench_returncode: int,
    stdout_payload: str,
) -> dict[str, Any]:
    wall = {
        "started_at": wall_started.isoformat(timespec="seconds"),
        "finished_at": wall_finished.isoformat(timespec="seconds"),
        "duration_s": round((wall_finished - wall_started).total_seconds(), 3),
    }
    lemonade_info = {
        "cli_version": lemonade.cli_version(),
        "server_root": lemonade.server_root(),
        "server_healthy": lemonade.server_healthy(),
        "api_base": lemonade.api_base(),
        "models_available": [m.get("id") for m in lemonade.list_models()],
        "command": cmd,
        "bench_returncode": bench_returncode,
        "bench_output": bench_json,
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "lemonmetrics_version": lemonmetrics.__version__,
        "generated_at": _now(),
        "wall": wall,
        "device": fingerprint.collect(),
        "environment": environment.collect(note="measured alongside bench run"),
        "lemonade": lemonade_info,
        "power": power,
        "efficiency": efficiency,
    }
    if stdout_payload:
        report["lemonade"]["bench_stdout_tail"] = stdout_payload[-2000:]
    return report
