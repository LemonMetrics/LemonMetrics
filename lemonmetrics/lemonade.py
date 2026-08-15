"""Lemonade CLI + HTTP API interaction for Lemon Metrics.

Lemonade can run natively (Windows, Linux, Apple Silicon) or inside a Docker container.

For intel macos docker is required:
    Set ``LEMONADE_DOCKER=<container>`` to route CLI calls through ``docker exec`` and ``LEMONADE_SERVER`` to point at the published HTTP port.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any

DEFAULT_SERVER_ROOT = "http://localhost:13305"
DEFAULT_API_BASE = "http://localhost:13305/api/v1"
CONTAINER_BENCH_OUTPUT = "/tmp/lemonmetrics-bench.json"


def server_root() -> str:
    return os.environ.get("LEMONADE_SERVER", DEFAULT_SERVER_ROOT).rstrip("/")


def api_base() -> str:
    return os.environ.get("LEMONADE_API_BASE", DEFAULT_API_BASE).rstrip("/")


def cli_path() -> str:
    return os.environ.get("LEMONADE_BIN", "lemonade")


def docker_container() -> str | None:
    return os.environ.get("LEMONADE_DOCKER") or None


def in_docker() -> bool:
    return docker_container() is not None


def docker_available() -> bool:
    container = docker_container()
    if not container:
        return False
    if not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "ps", "--filter", f"name={container}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return container in proc.stdout.split()


def cli_available() -> bool:
    if in_docker():
        return docker_available()
    if shutil.which(cli_path()) is None:
        return False
    try:
        proc = run_cli(["--version"], timeout=30)
    except OSError:
        return False
    return proc.returncode == 0


def run_cli(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    container = docker_container()
    cmd: list[str] = (
        ["docker", "exec", container, cli_path(), *args] if container else [cli_path(), *args]
    )
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def cli_version() -> str | None:
    if not cli_available():
        return None
    proc = run_cli(["--version"], timeout=30)
    if proc.returncode != 0:
        return None
    first = proc.stdout.strip().splitlines()
    return first[0] if first else None


def container_read_file(path: str) -> str:
    """Cat a file out of the Lemonade container (used for --output results)."""
    container = docker_container()
    if not container:
        raise RuntimeError("container_read_file requires LEMONADE_DOCKER")
    proc = subprocess.run(
        ["docker", "exec", container, "cat", path],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"failed to read {path} from container: {proc.stderr.strip()}")
    return proc.stdout


def server_healthy(timeout: int = 5) -> bool:
    try:
        req = urllib.request.Request(server_root() + "/live", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def http_get_json(path: str, timeout: int = 10) -> Any:
    req = urllib.request.Request(api_base() + path, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def list_models() -> list[dict]:
    try:
        body = http_get_json("/models")
    except (urllib.error.URLError, OSError):
        return []
    return body.get("data", []) if isinstance(body, dict) else []


def backends_text() -> str | None:
    if not cli_available():
        return None
    proc = run_cli(["backends"], timeout=120)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def bench_command(
    model: str,
    *,
    backend: str | None = None,
    ctx_size: int | None = None,
    runs: int = 3,
    warmup: int = 0,
    output: str | None = None,
    no_reload: bool = False,
    auto_pull: bool = False,
    extra_args: list[str] | None = None,
) -> list[str]:
    cmd = ["bench", model]
    if backend:
        cmd += ["--backend", backend]
    if ctx_size:
        cmd += ["--ctx-size", str(ctx_size)]
    cmd += ["--runs", str(runs)]
    if warmup:
        cmd += ["--warmup", str(warmup)]
    cmd += ["--json"]
    if output:
        cmd += ["--output", output]
    if no_reload:
        cmd += ["--no-reload"]
    if auto_pull:
        cmd += ["--auto-pull"]
    if extra_args:
        cmd += extra_args
    return cmd
