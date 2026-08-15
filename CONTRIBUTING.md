# Contributing to Lemon Metrics

Thank you for your interest in contributing to Lemon Metrics! This guide covers two main contribution paths:

1. **Benchmark Results** — Running the harness and submitting measurements
2. **Core Development** — Improvements to the harness, website, or infrastructure

---

## Running the Harness (Benchmark Results)

### Prerequisites

- Python 3.10+
- A working [Lemonade](https://github.com/lemonade-sdk/lemonade) CLI or Docker container
- A running Lemonade server (HTTP)
- On macOS: `powermetrics` access (the harness will prompt you to set this up)
- On Windows: Performance metrics will be unavailable (see [Methodology](docs/methodology.md))

### Quick Start

```bash
# Install the harness
git clone https://github.com/lemonmetrics/lemonmetrics.git
cd lemonmetrics
python3 -m pip install -e ".[dev]"

# Probe your machine to see what can be measured
lemonmetrics probe

# Run a benchmark (requires a Lemonade server and a model)
lemonmetrics run --model Qwen3-0.6B-GGUF --backend cpu --runs 3
```

See [run-it-yourself.md](docs/run-it-yourself.md) for full documentation on environment variables, Docker setup, and output formats.

### Output

Each `lemonmetrics run` produces a timestamped directory under `data/results/<device_id>/<run_id>/`:

```
data/results/<device_id>/<run_id>/
  report.json       # Full normalized report (schema v1)
  power.jsonl       # Raw power samples (one JSON per line)
  baseline.jsonl    # Raw idle baseline samples
  bench.json        # Raw lemonade bench --json output
  summary.md        # Human-readable summary
```

---

## Data Honesty Pledge

Before submitting results, please commit to the following principles:

✅ **Always run on AC power** — Battery results are not comparable across machines.

✅ **Use `--runs 3` or more** — Single runs are too noisy; we recommend 3–5 runs per model/backend combo.

✅ **Same model, same machine, multiple backends** — Honest comparisons happen when you test the same model across backends on a single device (e.g., CPU vs iGPU vs NPU).

✅ **Don't cherry-pick runs** — Submit what you measured. If a run looks odd, it's okay to document why in your PR description, but don't hide results.

✅ **Report the environment** — Mention your device, CPU governor (if Linux), thermal state, whether you were running other workloads, etc. The report captures this automatically; your PR description can add context.

✅ **Keep raw data** — The `power.jsonl`, `baseline.jsonl`, and `bench.json` files are the point. They're what makes results verifiable. Don't delete them.

✅ **If power is unavailable, say so** — On Windows, energy will be marked `power_available: false`. That's okay; performance metrics still count. Just don't invent power numbers.

---

## Expected Report Structure

Here's what a valid `report.json` looks like:

```json
{
  "schema_version": "1.0",
  "lemonmetrics_version": "1.0.0",
  "generated_at": "2026-08-09T11:37:46+00:00",
  "device": {
    "device_id": "auto-7831edf654a6",
    "fingerprint": "7831edf654a6",
    "os": "Darwin",
    "os_release": "25.5.0",
    "cpu": {
      "model": "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz",
      "physical_cores": 6,
      "logical_cores": 12
    },
    "memory_gb": 32.0,
    "gpu": ["Intel UHD Graphics 630", "AMD Radeon Pro 5300M"],
    "npu": []
  },
  "environment": {
    "power_source": "ac",
    "battery_percent": 100,
    "cpu_governor": null,
    "thermal_celsius": 45.5,
    "recorded_at": "2026-08-09T11:37:47+00:00"
  },
  "power": {
    "available": false,
    "sampler": "null",
    "samples": 0
  },
  "efficiency": {
    "available": false,
    "note": "no power source available"
  },
  "lemonade": {
    "command": ["bench", "--model", "Qwen3-0.6B-GGUF", "--backend", "cpu", "--runs", "3"],
    "bench_output": {
      "models": [
        {
          "model": "Qwen3-0.6B-GGUF",
          "results": [
            {
              "backend": "cpu",
              "recipe": "llamacpp",
              "scenarios": [
                {
                  "name": "chat-short",
                  "category": "chat",
                  "input_tokens": 27,
                  "output_tokens": 20,
                  "tps": { "mean": 44.3, "min": 44.1, "max": 44.5 },
                  "ttft_ms": { "mean": 104.7, "min": 96.7, "max": 113.9 },
                  "duration_ms": { "mean": 572.9, "min": 565.1, "max": 584.1 },
                  "memory_peak_gb": 1.7
                }
              ]
            }
          ]
        }
      ]
    }
  }
}
```

**Key fields to verify:**
- `schema_version`: Must be `"1.0"`
- `device.device_id`: Stable fingerprint (auto-generated)
- `power.available`: Boolean; can be `false` on Windows
- `lemonade.command`: Array starting with `"bench"`
- All reported power numbers must be ≥ 0 (or null if unavailable)

Run the validator locally before submitting:

```bash
python3 scripts/validate_results.py data/results
```

---

## Submitting Results

Results live in the [**lemonmetrics-site**](https://github.com/lemonmetrics/lemonmetrics-site) repository, not in this one.

### Workflow

1. **Run the harness** on AC power with `--runs 3` (or more).
   ```bash
   lemonmetrics run --model Qwen3-0.6B-GGUF --backend cpu --runs 3
   ```

2. **Review your results** locally and validate them.
   ```bash
   python3 scripts/validate_results.py data/results
   ```

3. **Fork** [lemonmetrics/lemonmetrics-site](https://github.com/lemonmetrics/lemonmetrics-site) on GitHub.

4. **Create a branch** and commit your `data/results/<device_id>/` directory.
   ```bash
   git checkout -b add-results-<your-device-id>
   git add data/results/<device_id>
   git commit -m "Add benchmark results for <your-device-id>"
   ```

5. **Push and open a PR** against the main branch of lemonmetrics-site.
   - Use the **Results PR Template** (auto-filled if you use GitHub's web UI)
   - Include context: device, OS, thermals, whether you were running other workloads
   - Link to this CONTRIBUTING.md section if needed

6. **CI validation** runs automatically (`scripts/validate_results.py`).
   - If validation fails, fix the report (re-run the harness if needed) and push again.
   - If validation passes, a maintainer will merge your results onto the leaderboard.

### Example Results PR Description

```
## Device

- **Device ID**: `auto-7831edf654a6`
- **CPU**: Intel i7-9750H
- **Memory**: 32 GB
- **OS**: macOS 25.5

## Runs

- Model: Qwen3-0.6B-GGUF
- Backends: `cpu`, `vulkan`, `flm_npu`
- 3 runs per backend, AC power only
- Thermal state: Stable (45°C), no other workloads

## Notes

Power metrics unavailable on this Intel Mac (host Mac, Lemonade in Docker).
Performance metrics are authoritative.
```

---

## Contributing to Core Code

Contributions to the harness itself, the website, validation logic, or infrastructure are welcome!

### Before You Start

- Check [existing issues](https://github.com/lemonmetrics/lemonmetrics/issues) to avoid duplicates
- For large changes, open an issue first to discuss approach
- Follow the style: Python 3.10+ with type hints, 100-char line length

### Development Setup

```bash
git clone https://github.com/lemonmetrics/lemonmetrics.git
cd lemonmetrics
python3 -m pip install -e ".[dev]"

# Run tests
python3 -m pytest tests/ -v

# Lint
ruff check lemonmetrics tests
ruff format lemonmetrics tests
```

### PR Checklist

- [ ] Tests pass: `python3 -m pytest tests/`
- [ ] Linter passes: `ruff check && ruff format`
- [ ] Docstrings added for new functions
- [ ] Type hints on all parameters and returns
- [ ] Changelog note (if user-facing) in PR description

### Example Core PR Description

```
## What

Add Windows power sampler logging for clearer UX when power unavailable.

## Why

Users on Windows see a silent fallthrough to null sampler.
This adds a dedicated `windows` sampler that logs an actionable message
pointing them to methodology.md.

## Changes

- New `WindowsSampler` class in `lemonmetrics/power/samplers.py`
- Updated sampler priority in `SAMPLER_CLASSES`
- Tests in `tests/test_power.py`

## Testing

- `test_windows_sampler_detect()` verifies detection
- `test_windows_sampler_logs_guidance()` verifies message
- Manual test on Windows: [link to screenshot]
```

---

## Questions?

- **Methodology questions**: See [methodology.md](docs/methodology.md)
- **Harness usage**: See [run-it-yourself.md](docs/run-it-yourself.md)
- **Issues**: Open an [Issue](https://github.com/lemonmetrics/lemonmetrics/issues)
- **Discussions**: Use [Discussions](https://github.com/lemonmetrics/lemonmetrics/discussions) for ideas and questions

---

## Code of Conduct

Be respectful and constructive. We're building a community of honest benchmark contributors.

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

Thank you for running Lemon Metrics and helping the community understand energy efficiency in local AI! 🍋
