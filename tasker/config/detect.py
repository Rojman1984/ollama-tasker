"""
tasker.config.detect
---------------------
Hardware profile auto-detection.

Detects CPU core count, RAM, and GPU VRAM (best-effort via nvidia-smi)
and maps the result to the closest existing hardware profile name:
  - tier0_minimal
  - tier1_tasker   (TASKER-P1 — Ryzen 5 3500U, 32 GB, CPU-only)
  - tier2_designlab (Designlab1 — Ryzen 5/7, GTX 1050 Ti 4 GB)

This is a suggestion mechanism, not an override.  ModeConfigurator accepts
an explicit profile name and only falls back to auto-detection when none is
given.  Detection calls (psutil, subprocess) are injectable for testing.
See SDD Section 8.2.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable


# --------------------------------------------------------------------------- #
# Thresholds (document here since they're a judgment call)
# --------------------------------------------------------------------------- #
#
#   GPU present AND vram_mb >= 4000 MB → tier2_designlab
#     (GTX 1050 Ti has 4 GB; any card with >= 4 GB VRAM implies a meaningful
#     GPU-accelerated setup, matching the Designlab1 profile)
#
#   No GPU (or < 4 GB VRAM) AND cpu_cores >= 4 AND ram_gb >= 8 → tier1_tasker
#     (TASKER-P1 has 6 cores, 32 GB RAM — targeting CPU-only inference with
#     enough RAM to keep a small model + context in memory)
#
#   Everything else → tier0_minimal
#     (< 4 cores or < 8 GB RAM — minimal footprint, smallest models only)
#
_GPU_VRAM_THRESHOLD_MB   = 4_000    # 4 GB
_TIER1_MIN_CORES         = 4
_TIER1_MIN_RAM_GB        = 8.0


@dataclass
class HardwareSnapshot:
    cpu_cores: int          # logical CPU count
    ram_gb: float           # total RAM in GiB
    gpu_vram_mb: int        # 0 if no CUDA-capable GPU found


def _detect_cpu_cores() -> int:
    import psutil
    return psutil.cpu_count(logical=True) or 1


def _detect_ram_gb() -> float:
    import psutil
    return psutil.virtual_memory().total / (1024 ** 3)


def _detect_gpu_vram_mb() -> int:
    """
    Shells out to nvidia-smi to query VRAM.  Returns 0 if the command is not
    found, returns a non-zero exit code, or reports no GPUs.
    No CUDA binding required — nvidia-smi is available on any CUDA-enabled host.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return 0
        # Sum across all GPUs (take the max in multi-GPU setups — orchestrator
        # will use the most capable card).
        vrams = [int(line.strip()) for line in result.stdout.strip().splitlines() if line.strip()]
        return max(vrams) if vrams else 0
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return 0


def detect_hardware(
    *,
    _cpu_fn: Callable[[], int]   = _detect_cpu_cores,
    _ram_fn: Callable[[], float] = _detect_ram_gb,
    _gpu_fn: Callable[[], int]   = _detect_gpu_vram_mb,
) -> HardwareSnapshot:
    """
    Collect hardware information.  The _*_fn parameters are injectable for
    tests — production callers use the defaults.
    """
    return HardwareSnapshot(
        cpu_cores=_cpu_fn(),
        ram_gb=_ram_fn(),
        gpu_vram_mb=_gpu_fn(),
    )


def suggest_profile(snapshot: HardwareSnapshot) -> str:
    """
    Map a HardwareSnapshot to the closest pre-defined profile name.
    Returns one of: "tier0_minimal", "tier1_tasker", "tier2_designlab".
    """
    if snapshot.gpu_vram_mb >= _GPU_VRAM_THRESHOLD_MB:
        return "tier2_designlab"
    if snapshot.cpu_cores >= _TIER1_MIN_CORES and snapshot.ram_gb >= _TIER1_MIN_RAM_GB:
        return "tier1_tasker"
    return "tier0_minimal"


def auto_detect_profile(
    *,
    _cpu_fn: Callable[[], int]   = _detect_cpu_cores,
    _ram_fn: Callable[[], float] = _detect_ram_gb,
    _gpu_fn: Callable[[], int]   = _detect_gpu_vram_mb,
) -> str:
    """
    Convenience wrapper: detect hardware and return the suggested profile name.
    """
    snapshot = detect_hardware(_cpu_fn=_cpu_fn, _ram_fn=_ram_fn, _gpu_fn=_gpu_fn)
    return suggest_profile(snapshot)
