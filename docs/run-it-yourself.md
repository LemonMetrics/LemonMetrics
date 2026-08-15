# Run it yourself

Install the harness, point it at a Lemonade server, and submit your results as a pull request to the [lemonmetrics-site](https://github.com/lemonmetrics/lemonmetrics-site) repository — results live there, not in this repository.

## Requirements

- Python 3.10+
- A working `lemonade` CLI, either:
  - **native** (Windows x86_64, Linux on x86_64/ARM, or Apple Silicon macOS), or
  - **Docker** (required for Intel Macs): the `ghcr.io/lemonade-sdk/lemonade-server` container.
- A running Lemonade server (HTTP) so the harness can cross-check the API.
- On macOS, power sampling uses `powermetrics`, which requires root. The harness can request that access for you (see below) — no manual sudoers editing.
- On Windows, there is no reliable real-time power source yet, so energy is reported as unavailable (`power_available: false`) while performance metrics still work — see [methodology.md](./methodology.md) for an open call to the community.

> **Docker and power.** The harness always runs on the **host**, never inside the container. When Lemonade is in Docker you set `LEMONADE_DOCKER=<container>` and the harness routes only the `lemonade` CLI calls through `docker exec`; power is still sampled from the host, so the watts reflect the laptop, not the VM.

## Install

```bash
python3 -m pip install -e ".[dev]"
```

## Configure

Environment variables (all optional):

| Variable | Default | Purpose |
| --- | --- | --- |
| `LEMONADE_BIN` | `lemonade` | path to the lemonade CLI |
| `LEMONADE_DOCKER` | *(unset)* | container name to route CLI calls through `docker exec` |
| `LEMONADE_SERVER` | `http://localhost:13305` | HTTP server root |
| `LEMONADE_API_BASE` | `http://localhost:13305/api/v1` | OpenAI-compatible API base |
| `LEMONMETRICS_NO_SUDO` | *(unset)* | set to `1` to skip the powermetrics access prompt |

## macOS power access

On macOS the harness needs `powermetrics`, which requires root. The first time you run `probe`, `detect`, or `run`, it offers to set up a **narrow** sudoers rule limited to `powermetrics` for your user. There is no manual sudoers editing:

```bash
# Explicitly configure access (prompts for your password once)
lemonmetrics setup

# Or just let probe/detect/run prompt you the first time they need it
lemonmetrics detect
```

How it works:

1. It first checks whether passwordless access already works (`sudo -n`).
2. If not, it shows a **standard macOS password dialog** (via AppleScript); the harness never sees your password.
3. If the GUI dialog is unavailable (e.g. over SSH), it falls back to a plain `sudo` prompt on the terminal.
4. The installed rule is scoped to your user and the `powermetrics` binary, and is validated with `visudo` before it is activated.

To run without any elevated access — energy will be reported unavailable — pass `--no-privileges` (or set `LEMONMETRICS_NO_SUDO=1`). The sudoers rule is only needed once; after that, access is passwordless.

## Quick start

```bash
# What can this host measure?
lemonmetrics probe

# Best available power source (hwmon, rapl, rocm-smi, powermetrics, null)?
lemonmetrics detect

# Run the default benchmark with power sampling
lemonmetrics run --model Qwen3-0.6B-GGUF --backend cpu --runs 3
```

Before the benchmark starts, the harness samples ~10 s of idle power (`--baseline-duration`, default `10`; disable with `--baseline-duration 0`). This baseline is subtracted to give **incremental** energy estimates, so the numbers reflect the cost of inference, not your machine idling.

With Docker on an Intel Mac:

```bash
docker run -d --name lemonade-server -p 13305:13305 \
  ghcr.io/lemonade-sdk/lemonade-server:latest
LEMONADE_DOCKER=lemonade-server lemonmetrics probe
```

## Benchmarking the same model across backends

The headline use-case is comparing energy per token across Lemonade backends on one machine (e.g. a Ryzen AI 9 HX 370):

```bash
lemonmetrics run --model Qwen3-0.6B-GGUF --backend cpu      --runs 3
lemonmetrics run --model Qwen3-0.6B-GGUF --backend vulkan   --runs 3
lemonmetrics run --model Qwen3-0.6B-GGUF --backend flm_npu  --runs 3
```

## Output

Each run writes to `data/results/<device_id>/<run_id>/`:

```
report.json     # full normalized report (schema v1)
power.jsonl     # raw power samples (ts, watts) — one JSON object per line
baseline.jsonl  # raw idle baseline samples, when a baseline was measured
bench.json      # raw `lemonade bench --json` output
summary.md      # human-readable summary
```

## Submitting results

1. Run your benchmarks with `--runs 3` (or more) on **AC power**.
2. Commit the new `data/results/...` directories.
3. Open a pull request. CI validates the JSON schema and merges your results into the public leaderboard at [LemonMetrics.github.io](https://LemonMetrics.github.io).

Read [methodology.md](./methodology.md) for how the energy numbers are computed and the honesty rules we ask contributors to follow.
