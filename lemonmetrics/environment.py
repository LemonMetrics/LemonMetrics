"""Ambient/environment snapshot for benchmark reproducibility."""

from __future__ import annotations

import datetime as _dt
import glob
import os
import platform
import re
import subprocess
from typing import Any


def _powershell(script: str) -> str:
    """Run a PowerShell script, returning trimmed stdout (empty on failure)."""
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])


def _run(args: list[str]) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            value = fh.read().strip()
        return value or None
    except OSError:
        return None


def power_source() -> str:
    if os.path.isdir("/sys/class/power_supply"):
        for supply in sorted(glob.glob("/sys/class/power_supply/*")):
            stype = _read(os.path.join(supply, "type")) or ""
            if "Battery" in stype:
                status = _read(os.path.join(supply, "status")) or "unknown"
                if status in ("Discharging", "Not charging"):
                    return "battery"
        return "ac"
    if platform.system() == "Darwin":
        batt = _run(["pmset", "-g", "batt"])
        if "AC Power" in batt:
            return "ac"
        if "Battery Power" in batt:
            return "battery"
    if platform.system() == "Windows":
        status = _powershell(
            "(Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue).BatteryStatus"
        )
        codes = [int(x) for x in re.findall(r"\d+", status)]
        if not codes:
            return "unknown"
        return "battery" if 1 in codes else "ac"
    return "unknown"


def battery_percent() -> int | None:
    if os.path.isdir("/sys/class/power_supply"):
        for supply in sorted(glob.glob("/sys/class/power_supply/*")):
            stype = _read(os.path.join(supply, "type")) or ""
            if "Battery" in stype:
                capacity = _read(os.path.join(supply, "capacity"))
                if capacity and capacity.isdigit():
                    return int(capacity)
    if platform.system() == "Darwin":
        batt = _run(["pmset", "-g", "batt"])
        match = re.search(r"(\d{1,3})%", batt)
        if match:
            return int(match.group(1))
    if platform.system() == "Windows":
        pct = _powershell(
            "(Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue).EstimatedChargeRemaining"
        )
        if pct.isdigit():
            return int(pct)
        return None
    return None


def cpu_governor() -> str | None:
    if os.path.isdir("/sys/devices/system/cpu/cpu0/cpufreq"):
        return _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    return None


def thermal_celsius() -> float | None:
    temps = []
    for zone in sorted(glob.glob("/sys/class/thermal/thermal_zone*/temp")):
        value = _read(zone)
        if value and value.lstrip("-").isdigit():
            temps.append(int(value) / 1000.0)
    if not temps:
        return None
    return round(max(temps), 1)


def containerized() -> bool:
    """True when the harness itself is running inside a container.

    Power sensors are host-local; a containerized harness would read the
    Linux VM's virtualized sysfs instead of the physical machine, so callers
    should warn rather than trust those readings.
    """
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", encoding="utf-8", errors="replace") as fh:
            cgroup = fh.read()
    except OSError:
        return False
    return any(token in cgroup for token in ("docker", "kubepods", "libpod", "containerd"))


def collect(note: str | None = None) -> dict[str, Any]:
    return {
        "recorded_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "power_source": power_source(),
        "battery_percent": battery_percent(),
        "cpu_governor": cpu_governor(),
        "thermal_celsius": thermal_celsius(),
        "note": note,
    }
