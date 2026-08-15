"""Shared fixtures: a minimal but realistic lemonade bench JSON payload."""

import json

BENCH_JSON = {
    "hardware": {
        "backends": {"llamacpp/cpu": "b10241"},
        "cpu": "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz",
        "gpu": [],
        "os": "linux",
        "ram_gb": 15.69,
    },
    "models": [
        {
            "config": {"measurement_runs": 1, "memory_tracking": True, "warmup_runs": 0},
            "model": "Qwen3-0.6B-GGUF",
            "results": [
                {
                    "backend": "cpu",
                    "backend_args": "",
                    "ctx_size": 4096,
                    "recipe": "llamacpp",
                    "scenarios": [
                        {
                            "category": "chat",
                            "duration_ms": {
                                "max": 511.9,
                                "mean": 511.9,
                                "min": 511.9,
                                "p50": 511.9,
                                "p95": 511.9,
                            },
                            "failed_runs": 0,
                            "input_tokens": 27,
                            "memory_peak_gb": 1.6,
                            "name": "chat-short",
                            "output_tokens": 20,
                            "tps": {
                                "max": 50.5,
                                "mean": 50.5,
                                "min": 50.5,
                                "p50": 50.5,
                                "p95": 50.5,
                            },
                            "ttft_ms": {
                                "max": 99.4,
                                "mean": 99.4,
                                "min": 99.4,
                                "p50": 99.4,
                                "p95": 99.4,
                            },
                        },
                        {
                            "category": "chat",
                            "duration_ms": {
                                "max": 5652.8,
                                "mean": 5652.8,
                                "min": 5652.8,
                                "p50": 5652.8,
                                "p95": 5652.8,
                            },
                            "failed_runs": 0,
                            "input_tokens": 44,
                            "memory_peak_gb": 1.6,
                            "name": "chat-long-output",
                            "output_tokens": 256,
                            "tps": {
                                "max": 46.5,
                                "mean": 46.5,
                                "min": 46.5,
                                "p50": 46.5,
                                "p95": 46.5,
                            },
                            "ttft_ms": {
                                "max": 137.6,
                                "mean": 137.6,
                                "min": 137.6,
                                "p50": 137.6,
                                "p95": 137.6,
                            },
                        },
                    ],
                }
            ],
            "timestamp": "2026-08-09T11:14:57Z",
        }
    ],
    "timestamp": "2026-08-09T11:14:57Z",
}

# Mimics real `lemonade bench --json` stdout: human summary then the JSON object.
STDOUT_WITH_PREFIX = (
    "=== [Qwen3-0.6B-GGUF] llamacpp/cpu (ctx=4096) ===\n"
    "  Scenario: chat-short (chat)\n"
    "    Run 1/1... TTFT=99.4ms TPS=50.5\n" + json.dumps(BENCH_JSON)
)
