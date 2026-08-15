"""Power sampling for Lemon Metrics.

The harness samples platform power (macOS powermetrics, Linux hwmon/RAPL,
rocm-smi) while ``lemonade bench`` runs, then folds it into J/token and
peak-power metrics.  When no source is available the ``null`` sampler reports
``power_available: false``.
"""

from __future__ import annotations

from lemonmetrics.power.base import BackgroundSampler, PowerSampler, Sample
from lemonmetrics.power.samplers import (
    HwmonSampler,
    NullSampler,
    PowermetricsSampler,
    RaplSampler,
    RocmSmiSampler,
    detect_sampler,
)

__all__ = [
    "BackgroundSampler",
    "PowerSampler",
    "Sample",
    "HwmonSampler",
    "NullSampler",
    "PowermetricsSampler",
    "RaplSampler",
    "RocmSmiSampler",
    "detect_sampler",
]
