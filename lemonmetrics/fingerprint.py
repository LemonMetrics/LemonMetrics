"""Machine fingerprinting for reproducible benchmark reports."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import socket
import subprocess
from typing import Any


def _run(args: list[str]) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
        return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _powershell(script: str) -> str:
    """Run a PowerShell script, returning trimmed stdout (empty on failure)."""
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])


def _first_line(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    return line
    except OSError:
        return None
    return None


def _grep(path: str, pattern: str) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return [line.strip() for line in fh if re.search(pattern, line)]
    except OSError:
        return []


def cpu_model() -> str:
    if platform.system() == "Darwin":
        return _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    if platform.system() == "Windows":
        name = _powershell("(Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue).Name")
        return name.splitlines()[0] if name else (platform.processor() or "unknown")
    cpuinfo = _first_line("/proc/cpuinfo") or ""
    if "model name" in cpuinfo:
        return cpuinfo.split(":", 1)[1].strip()
    if "Hardware" in cpuinfo:
        return cpuinfo.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def physical_core_count() -> int:
    if platform.system() == "Darwin":
        out = _run(["sysctl", "-n", "hw.physicalcpu"])
        return int(out) if out.isdigit() else os.cpu_count() or 0
    if platform.system() == "Windows":
        out = _powershell(
            "(Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue).NumberOfCores"
        )
        if out:
            cores = sum(int(x) for x in re.findall(r"\d+", out) if x)
            return cores or (os.cpu_count() or 0)
        return os.cpu_count() or 0
    try:
        cores = set()
        for line in _grep("/proc/cpuinfo", "^physical id"):
            cores.add(line.split(":", 1)[1].strip())
        siblings = _grep("/proc/cpuinfo", "^siblings")
        if cores and siblings:
            return len(cores) * max(int(s.split(":", 1)[1].strip()) for s in siblings)
    except OSError:
        pass
    return os.cpu_count() or 0


def memory_gb() -> float:
    system = platform.system()
    if system == "Darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        if out.isdigit():
            return round(int(out) / (1024**3), 2)
    if system == "Windows":
        out = _powershell(
            "(Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).TotalPhysicalMemory"
        )
        if out.isdigit():
            return round(int(out) / (1024**3), 2)
        return 0.0
    if system == "Linux":
        total = _first_line("/proc/meminfo") or ""
        if "MemTotal" in total:
            kb = int(re.sub(r"\D", "", total))
            return round(kb / (1024**2), 2)
    return 0.0


def gpu_list() -> list[str]:
    if platform.system() == "Linux":
        if shutil.which("lspci"):
            out = _run(["lspci", "-nn"])
            return [
                line.split(": ", 1)[1]
                for line in out.splitlines()
                if re.search(r"VGA|3D controller|Display controller", line, re.IGNORECASE)
            ]
        return []
    if platform.system() == "Darwin":
        gpus = []
        for line in _run(["system_profiler", "SPDisplaysDataType"]).splitlines():
            if "Chipset Model" in line:
                gpus.append(line.split(":", 1)[1].strip())
        return gpus
    if platform.system() == "Windows":
        out = _powershell(
            "(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue).Name"
        )
        return [line.strip() for line in out.splitlines() if line.strip()]
    return []


def npu_list() -> list[str]:
    if platform.system() != "Linux":
        return []
    found = []
    if shutil.which("lspci"):
        out = _run(["lspci", "-nn"])
        found += [
            line.split(": ", 1)[1]
            for line in out.splitlines()
            if re.search(r"NPU|Neural|Accelerator|xdna|XDNA", line, re.IGNORECASE)
        ]
    if os.path.isdir("/sys/class/amdxdna"):
        found.append("AMD XDNA NPU (amdxdna)")
    return list(dict.fromkeys(found))


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "device"


def collect(device_name: str | None = None) -> dict[str, Any]:
    system = platform.system()
    machine = platform.machine()
    cpu = cpu_model()
    gpus = gpu_list()
    npus = npu_list()
    identity = "|".join([cpu, "|".join(gpus), "|".join(npus), system, machine])
    fingerprint = hashlib.sha256(identity.encode()).hexdigest()[:12]

    info: dict[str, Any] = {
        "device_id": _slugify(device_name) if device_name else f"auto-{fingerprint}",
        "fingerprint": fingerprint,
        "hostname": socket.gethostname(),
        "os": system,
        "os_release": platform.release(),
        "machine": machine,
        "cpu": {
            "model": cpu,
            "logical_cores": os.cpu_count(),
            "physical_cores": physical_core_count(),
        },
        "memory_gb": memory_gb(),
        "gpu": gpus,
        "npu": npus,
    }
    return info
