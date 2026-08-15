"""Command-line interface for Lemon Metrics.

Commands:

* ``probe``        -- report what this host can measure (CLI, server, power)
* ``run``          -- run ``lemonade bench`` with concurrent power sampling
* ``detect``       -- print the best available power sampler (debugging)
* ``setup``        -- grant the harness powermetrics access (macOS, one-time)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

from lemonmetrics import core, environment, fingerprint, lemonade
from lemonmetrics.power import detect_sampler


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def _ensure_power(args: argparse.Namespace) -> None:
    """Auto-configure macOS powermetrics access unless explicitly disabled."""
    if args.no_privileges or os.environ.get("LEMONMETRICS_NO_SUDO"):
        return
    from lemonmetrics.power.privileges import ensure_powermetrics_access

    ensure_powermetrics_access()


def cmd_probe(args: argparse.Namespace) -> int:
    info: dict[str, Any] = {
        "device": fingerprint.collect(),
        "lemonade": {
            "cli_available": lemonade.cli_available(),
            "cli_version": lemonade.cli_version(),
            "server_root": lemonade.server_root(),
            "server_healthy": lemonade.server_healthy(),
            "api_base": lemonade.api_base(),
            "models_available": [m.get("id") for m in lemonade.list_models()],
        },
    }
    if info["lemonade"]["cli_available"]:
        backends = lemonade.backends_text()
        if backends:
            info["lemonade"]["backends"] = backends.splitlines()
    _ensure_power(args)
    sampler = detect_sampler(interval=args.power_interval)
    info["power"] = {
        "sampler": sampler.name,
        "available": sampler.name != "null",
    }
    sampler.close()
    if args.json:
        _print_json(info)
    else:
        _print_probe_human(info)
    return 0


def _print_probe_human(info: dict[str, Any]) -> None:
    device = info["device"]
    print(f"device_id : {device['device_id']}")
    print(f"os        : {device['os']} {device['os_release']} ({device['machine']})")
    print(f"cpu       : {device['cpu']['model']}")
    lemon = info["lemonade"]
    print(f"cli       : {'available' if lemon['cli_available'] else 'MISSING'}")
    if lemon.get("cli_version"):
        print(f"cli_ver   : {lemon['cli_version']}")
    print(
        f"server    : {'healthy' if lemon['server_healthy'] else 'unreachable'} "
        f"({lemon['server_root']})"
    )
    if lemon.get("models_available"):
        print(f"models    : {', '.join(lemon['models_available'])}")
    print(
        f"power     : {info['power']['sampler']} "
        f"({'available' if info['power']['available'] else 'unavailable'})"
    )


def cmd_run(args: argparse.Namespace) -> int:
    models = args.model or []
    if not models:
        print("error: --model is required", file=sys.stderr)
        return 2

    if not lemonade.cli_available():
        print("error: lemonade CLI not found (set LEMONADE_BIN)", file=sys.stderr)
        return 2
    if not lemonade.server_healthy():
        print(
            f"warning: lemonade server at {lemonade.server_root()} is not healthy",
            file=sys.stderr,
        )

    _ensure_power(args)
    sampler = detect_sampler(interval=args.power_interval)
    if sampler.name == "null":
        if environment.containerized():
            print(
                "warning: the harness is running inside a container; power samples would "
                "reflect the Linux VM, not your host laptop. Run the harness on the host "
                "machine instead (see docs/run-it-yourself.md).",
                file=sys.stderr,
            )
        else:
            print(
                "warning: no power source detected; energy metrics will be marked unavailable",
                file=sys.stderr,
            )
    elif sampler.name == "windows":
        print(
            "warning: Windows does not expose real-time power APIs; energy metrics will be marked unavailable. "
            "For power measurements, run the harness on macOS or Linux (see docs/methodology.md).",
            file=sys.stderr,
        )
    sampler.close()

    for model in models:
        try:
            report = core.run_bench(
                model,
                backend=args.backend,
                ctx_size=args.ctx_size,
                runs=args.runs,
                warmup=args.warmup,
                extra_args=args.extra_args,
                power_interval=args.power_interval,
                baseline_duration=args.baseline_duration,
                no_reload=args.no_reload,
                auto_pull=args.auto_pull,
            )
        except (RuntimeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\ninterrupted", file=sys.stderr)
            return 130

        paths = core_report_writer(report, args.output_dir)
        if args.json:
            _print_json({"model": model, "files": paths, "report": report})
        else:
            print(f"wrote {model}:")
            for key, path in paths.items():
                print(f"  {key:8} {path}")

    return 0


def core_report_writer(report: dict[str, Any], output_dir: str) -> dict[str, str]:
    """Write a report to disk via :mod:`lemonmetrics.report`."""
    from lemonmetrics import report as report_mod

    return report_mod.write_report(report, output_dir)


def cmd_detect(args: argparse.Namespace) -> int:
    _ensure_power(args)
    sampler = detect_sampler(interval=args.power_interval)
    result = {"sampler": sampler.name, "available": sampler.name != "null"}
    if args.json:
        _print_json(result)
    else:
        print(f"{sampler.name} ({'available' if result['available'] else 'unavailable'})")
    sampler.close()
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    from lemonmetrics.power.privileges import ensure_powermetrics_access

    ok = ensure_powermetrics_access(allow_prompt=not args.no_privileges)
    if args.json:
        _print_json({"configured": ok})
    else:
        print("powermetrics access: " + ("configured" if ok else "NOT configured"))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lemonmetrics",
        description="Benchmark + energy harness for Lemonade local AI servers.",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="report what this host can measure")
    probe.add_argument(
        "--power-interval", type=float, default=1.0, help="power sample interval (s)"
    )
    probe.add_argument(
        "--no-privileges",
        action="store_true",
        help="skip the powermetrics access prompt (also: LEMONMETRICS_NO_SUDO=1)",
    )
    probe.set_defaults(func=cmd_probe)

    run = sub.add_parser("run", help="run lemonade bench with power sampling")
    run.add_argument("--model", action="append", help="model to bench (repeatable)")
    run.add_argument("--backend", default=None, help="lemonade backend (e.g. cpu)")
    run.add_argument("--runs", type=int, default=3, help="measurement runs per scenario")
    run.add_argument("--warmup", type=int, default=0, help="warmup runs per scenario")
    run.add_argument("--ctx-size", type=int, default=None, help="context window size")
    run.add_argument("--power-interval", type=float, default=1.0, help="power sample interval (s)")
    run.add_argument(
        "--baseline-duration",
        type=float,
        default=10.0,
        help="seconds of idle power sampled before the bench (use 0 to disable)",
    )
    run.add_argument(
        "--no-privileges",
        action="store_true",
        help="skip the powermetrics access prompt (also: LEMONMETRICS_NO_SUDO=1)",
    )
    run.add_argument(
        "--output-dir",
        default="data/results",
        help="directory for run reports (default: data/results)",
    )
    run.add_argument(
        "--no-reload", action="store_true", help="do not reload model between scenarios"
    )
    run.add_argument("--auto-pull", action="store_true", help="auto-pull missing models")
    run.add_argument(
        "--extra-args",
        action="append",
        default=None,
        help="extra args appended to lemonade bench (repeatable, each is one arg)",
    )
    run.set_defaults(func=cmd_run)

    detect = sub.add_parser("detect", help="print the detected power sampler")
    detect.add_argument(
        "--power-interval", type=float, default=1.0, help="power sample interval (s)"
    )
    detect.add_argument(
        "--no-privileges",
        action="store_true",
        help="skip the powermetrics access prompt (also: LEMONMETRICS_NO_SUDO=1)",
    )
    detect.set_defaults(func=cmd_detect)

    setup = sub.add_parser(
        "setup",
        help="grant the harness powermetrics access (macOS, one-time)",
    )
    setup.add_argument(
        "--no-privileges",
        action="store_true",
        help="do not prompt; report whether access is already configured",
    )
    setup.set_defaults(func=cmd_setup)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
