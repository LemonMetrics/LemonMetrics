# Lemon Metrics

Measure **energy per token** and peak power for [Lemonade](https://github.com/lemonade-sdk/lemonade) local AI servers — across CPUs, iGPUs, and NPUs.

```
J/token   ← the metric nobody ships
tokens/s  ← the metric everybody ships
```

Lemonade already benchmarks tokens/sec, time-to-first-token, and memory.
Lemon Metrics wraps that benchmark with a power-sampling layer so you can answer the question that actually matters for laptops: **how much battery does this model burn per token?**

Built as an open-source, MIT-licensed harness. Community members run it on their own machines and submit the results to the public site ([LemonMetrics.github.io](https://LemonMetrics.github.io)) by opening a pull request on the [lemonmetrics-site](https://github.com/lemonmetrics/lemonmetrics-site) repository.

## Why energy

Running a model "fast" is one thing. On a laptop — where the CPU, iGPU, and NPU on a chip like the Ryzen AI 9 all sit a few watts apart — the interesting comparison is **work done per joule**. J/token makes cross-backend comparison honest: an NPU that runs 30% slower but uses half the power is the betterlaptop experience.

## What it does

- Wraps `lemonade bench --json` — performance metrics come from Lemonade itself
- Samples platform power (Linux `hwmon` / Intel `rapl` / `rocm-smi`, macOS `powermetrics`, the latter auto-configured via a one-time scoped prompt) in a background thread during the whole benchmark
- Computes wall energy, **J/token**, J/output-token, and tokens/kWh
- Measures an idle baseline and reports **incremental** (baseline-corrected) energy estimates alongside the authoritative wall numbers
- Captures a machine fingerprint + ambient snapshot (AC vs battery, thermals) so results are comparable
- Degrades gracefully: no power source (e.g. Windows, which lacks a reliable real-time source yet) → energy marked unavailable, run still completes
- Writes `report.json`, raw `power.jsonl`, `baseline.jsonl`, raw `bench.json`, and a Markdown summary per run

## Quick start

```bash
pip install -e ".[dev]"

lemonmetrics probe
lemonmetrics run --model Qwen3-0.6B-GGUF --backend cpu --runs 3
```

>Note: On Windows, Lemonade runs natively and the harness works — but Windows has no reliable real-time power source yet, so energy is reported unavailable (`power_available: false`). See the community call in [methodology.md](docs/methodology.md) if you can help change that.
>
>On an Intel Mac, run Lemonade in Docker and point the harness at the container. The harness itself stays on the host so power numbers reflect the laptop, not the VM:
>
>```bash
>docker run -d --name lemonade-server -p 13305:13305 \
>  ghcr.io/lemonade-sdk/lemonade-server:latest
>LEMONADE_DOCKER=lemonade-server lemonmetrics probe
>```

Compare backends on one machine:

```bash
lemonmetrics run --model Qwen3-0.6B-GGUF --backend cpu     --runs 3
lemonmetrics run --model Qwen3-0.6B-GGUF --backend vulkan  --runs 3
lemonmetrics run --model Qwen3-0.6B-GGUF --backend flm_npu --runs 3
```

## Submitting results

Results live in the [lemonmetrics-site](https://github.com/lemonmetrics/lemonmetrics-site) repository, not here. Run the harness, then open a pull request there with the `data/results/<device>/<run>/` directory your run produced. See [run-it-yourself.md](docs/run-it-yourself.md) for the full workflow.

## Documentation

- [Methodology](docs/methodology.md) — how power and energy are measured
- [Run it yourself](docs/run-it-yourself.md) — setup, usage, submitting results

## Project layout

```
lemonmetrics/
  cli.py            # probe / run / detect / setup commands
  core.py           # run lemonade bench while sampling power (baseline-aware)
  lemonade.py       # lemonade CLI + HTTP API wrappers (docker exec support)
  fingerprint.py    # stable machine fingerprint
  environment.py    # AC/battery/governor/thermal snapshot + containerized check
  report.py         # JSON / JSONL / Markdown writers
  power/            # PowerSampler base + hwmon/rapl/rocm-smi/powermetrics + privileges
docs/               # methodology + run-it-yourself
tests/              # pytest suite
```

## License

MIT — see [LICENSE](LICENSE).

## Support

Lemon Metrics is a community project. If it helps you, [buy me a coffee](https://buymeacoffee.com/austincasteel) — contributions help cover hosting and the domain.
