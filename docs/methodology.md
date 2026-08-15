# Methodology: how Lemon Metrics measures energy

Lemon Metrics combines Lemonade's built-in performance benchmark with a power-sampling layer so results are reported as **energy per token** (J/token) and **peak power** in addition to tokens/sec and latency.

## What gets measured

For every run we record three layers:

1. **Machine fingerprint** — CPU model, physical/logical cores, RAM, GPU/NPU list, OS, and a stable `device_id` derived from those (so community results are comparable and deduplicatable).
2. **Ambient snapshot** — power source (AC vs battery), battery percent, CPU governor, thermal state. Energy numbers are only meaningful when the machine is on AC and in a steady thermal state.
3. **The benchmark** — `lemonade bench --json`, which reports per-scenario throughput (TPS), TTFT, duration percentiles (min/mean/p50/p95), and memory peak. We do **not** reimplement performance benchmarking; we wrap Lemonade's.
4. **Power samples** — wall-clock watts sampled at 1-2 Hz for the entire bench.

## How power is sampled

While `lemonade bench` runs, a background thread polls the best available power source for the platform:

| Platform | Sampler | Source |
| --- | --- | --- |
| Linux (AMD Ryzen AI, Radeon iGPU) | `hwmon` | sysfs `power1_average` on every hwmon device, summed |
| Linux (Intel) | `rapl` | `intel-rapl` package `energy_uj`, differentiated |
| Linux (AMD dGPU) | `rocm-smi` | `rocm-smi --showpower --json` |
| macOS | `powermetrics` | first run prompts once and installs a scoped sudoers rule (see below); afterwards it is passwordless |
| Windows | `null` | no reliable real-time source yet — falls back to `null` (see the call below) |
| fallback | `null` | marks `power_available: false`, never fails the run |

On macOS the harness requests `powermetrics` access through the standard system password prompt and installs a **narrow** sudoers rule scoped to your user and the `powermetrics` binary — it cannot run arbitrary commands as root. The rule is validated with `visudo` before being activated. You can skip this entirely with `--no-privileges` (or `LEMONMETRICS_NO_SUDO=1`).

### Docker and virtualized runs

The harness samples power from the **host**, and only the `lemonade` CLI calls are routed into the container (`LEMONADE_DOCKER`). If you instead run the harness *inside* the container, its samplers would read the Linux VM's counters — not the host device — so the harness warns and reports power unavailable rather than shipping numbers that measure the wrong machine.

When no source is detected (e.g. macOS without root), the run still completes and records performance metrics; energy is marked unavailable rather than fabricated.

### Windows power — an open call to the community

On Windows we currently mark power unavailable (`power_available: false`) rather than ship numbers we can't stand behind. Windows has no equivalent to the sysfs `hwmon`/`powercap` hierarchy on Linux or `powermetrics` on macOS, and none of the obvious alternatives yet meet our bar of *reproducible, per-sample, 1–2 Hz watts without privileged vendor tooling*. Here's where things stand:

- **AMD/Intel driver counters** — AMD `uprof` (PMF/aperf driver) and Intel VTune/IPM expose energy counters, but they need admin, vendor-specific installs, and aren't uniformly available.
- **WMI power classes** — `Win32_PowerMeter` and `Win32_PerfFormattedData_PowerMeter_PowerMeter` exist on paper, but are only populated on specific platforms with manufacturer ACPI/PPM support and are frequently empty in practice.
- **Battery-based draw** — `Win32_Battery` can estimate discharge rate, but only on a laptop that's actually draining, which conflicts with our "bench on AC" honesty rule.
- **`powercfg /energy`** — produces a static ~60-second report, not a per-sample stream.
- **Counter-derived estimates** — the most promising portable path (deriving watts from CPU performance counters + TDP coefficients, à la Intel PCM / EnegryRanger), but calibrating across AMD *and* Intel hardware is a real project.

Our rules: never invent power data, and a number we can't reproduce isn't a number. So Windows runs today record full performance metrics with energy marked unavailable. **If you have a reliable, reproducible way to sample real-time watts on Windows** — 1–2 s cadence over a 1–10 minute bench, ideally without admin — open an issue or PR; we'd love a first-class `windows` sampler and Windows rows on the leaderboard.

## How energy metrics are computed

Let `P` be the mean sampled power (watts) and `T_wall` the wall duration of the bench in seconds.

- **Wall energy**: `E_wall = P × T_wall` (joules)
- **J/token**: `E_wall / total_tokens`, where `total_tokens` sums the input and output tokens across all scenarios.
- **J/output token**: `E_wall / total_output_tokens` — the cost of *generating* (the token that inference is actually producing).
- **tokens/kWh**: `3.6e6 × total_tokens / E_wall`.

Per-scenario estimates use `P × scenario_mean_duration` and are labelled
`estimated_` because `lemonade bench` spends wall time loading/reloading models between scenarios that the mean duration does not include.

### Idle baseline correction

Before the bench starts, the harness samples `--baseline-duration` seconds
(default 10) of **idle** power with the same sampler. It then reports two views:

- **Wall energy** (`E_wall = P × T_wall`) and the headline **J/token** — the
  measured, authoritative numbers, including whatever the machine was doing while the bench ran.
- **Incremental metrics** (`incremental_watts = max(P − baseline_watts, 0)`, then the same joules/token/kWh formulas on that delta) — labelled `incremental_*` and described as estimates, because they subtract an idle baseline measured minutes earlier on the same machine. These estimate the cost of inference itself, isolating it from background/OS idle draw.

Both are always reported together; a run that hides its baseline cannot claim an incremental number. Raw baseline samples are written to `baseline.jsonl`.

## Honesty rules

- Never invent power data. If a source is missing, report `power_available: false`.
- Always report the environment (`battery_percent`, `power_source`) so readers can reject runs done on battery if necessary.
- Report raw samples as JSONL alongside the summary so anyone can recompute.
- Per-scenario energy is an estimate and says so; only wall-level energy is authoritative. Incremental (baseline-corrected) numbers are also estimates and are labelled `incremental_*`.
- The `device_id` is derived from hardware, so merging community results from the same machine type is safe.

## Reproducibility

Each run directory contains `report.json` (everything), `power.jsonl` (raw samples), `baseline.jsonl` (raw idle samples, when measured), `bench.json` (raw Lemonade output), and `summary.md`. The full `lemonade bench` command is recorded verbatim in `report.json.lemonade.command`, so runs can be re-executed identically.
