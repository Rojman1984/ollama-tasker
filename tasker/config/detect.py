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

Phase 7.5.2 additions (SDD_ADDENDUM_7.5.md A.3, A.5):
  - detect_hardware_profile() — live detection returning a full
    HardwareProfile, GPU-aware via tasker.config.gpu_backends.detect_gpu()
  - load_yaml_profile() / load_cached_detection() — the three-source
    resolution order's sources 1 and 2
  - cli_main() — the `tasker-hardware` applet entry point
"""
from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

from tasker.config.gpu_backends import GPUInfo, detect_gpu
from tasker.modes.base import HardwareProfile
from tasker.workers.base import TaskerConfigError


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


# --------------------------------------------------------------------------- #
# Phase 7.5.2 — GPU-aware live detection, YAML profile loading, cache
# (SDD_ADDENDUM_7.5.md A.3, A.5)
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).parent.parent.parent
_PROFILES_DIR = _REPO_ROOT / "config" / "profiles"
_CACHE_PATH = Path(".tasker") / "hardware_profile.json"


def load_yaml_profile(name: str) -> HardwareProfile:
    """Read config/profiles/<name>.yaml and return a HardwareProfile."""
    path = _PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        raise TaskerConfigError(f"Hardware profile not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return HardwareProfile.from_dict(yaml.safe_load(fh))


def _suggest_profile_name(cpu_cores: int, ram_gb: float, gpu: GPUInfo | None) -> str:
    """
    GPU-aware tier suggestion. Mirrors suggest_profile()'s thresholds but
    consumes a GPUInfo instead of a raw VRAM int, so it can correctly skip
    the discrete-VRAM comparison for unified-memory (AMD APU) GPUs --
    comparing an APU's memory_mb (total system RAM, see GPUInfo docstring)
    against the discrete-card VRAM threshold would misclassify nearly every
    modern APU machine as GPU-accelerated-tier2. AMD APU detection itself
    isn't implemented until 7.5.4, so this branch is unreachable in
    production this phase, but is written correctly now so it needs no
    revisiting when AmdApuBackend lands.
    """
    if gpu is not None and gpu.vendor == "nvidia" and not gpu.is_unified_memory:
        if (gpu.memory_mb or 0) >= _GPU_VRAM_THRESHOLD_MB:
            return "tier2_designlab"
    if cpu_cores >= _TIER1_MIN_CORES and ram_gb >= _TIER1_MIN_RAM_GB:
        return "tier1_tasker"
    return "tier0_minimal"


def _run_live_detection(
    *,
    _cpu_fn: Callable[[], int] | None = None,
    _ram_fn: Callable[[], float] | None = None,
    _gpu_detect_fn: Callable[[], GPUInfo | None] | None = None,
) -> tuple[int, float, GPUInfo | None, str, HardwareProfile]:
    """
    Shared by detect_hardware_profile() and the `detect`/`verify` CLI
    subcommands, which additionally need the raw facts to build the cache.

    The _*_fn defaults are resolved inside the body (not bound as parameter
    defaults) so that mock.patch on the module-level _detect_cpu_cores /
    _detect_ram_gb / detect_gpu reaches production callers (e.g. the CLI
    subcommands below, which don't take injectable params themselves) —
    a bound default is captured at def-time and wouldn't see a later patch.
    """
    cpu_fn = _cpu_fn or _detect_cpu_cores
    ram_fn = _ram_fn or _detect_ram_gb
    gpu_fn = _gpu_detect_fn or detect_gpu
    cpu_cores = cpu_fn()
    ram_gb = ram_fn()
    gpu = gpu_fn()
    name = _suggest_profile_name(cpu_cores, ram_gb, gpu)
    profile = load_yaml_profile(name)
    return cpu_cores, ram_gb, gpu, name, profile


def detect_hardware_profile(
    *,
    _cpu_fn: Callable[[], int] | None = None,
    _ram_fn: Callable[[], float] | None = None,
    _gpu_detect_fn: Callable[[], GPUInfo | None] | None = None,
) -> HardwareProfile:
    """
    Live detection fallback (source 3 of the A.3.1 resolution order).
    GPU-aware via detect_gpu() rather than the Phase 7 nvidia-smi-only path.
    """
    _, _, _, _, profile = _run_live_detection(
        _cpu_fn=_cpu_fn, _ram_fn=_ram_fn, _gpu_detect_fn=_gpu_detect_fn,
    )
    return profile


def load_cached_detection(*, _cache_path: Path | None = None) -> HardwareProfile | None:
    """
    Machine-local cache (source 2 of the A.3.1 resolution order).

    Returns None if the cache file is missing (not an error), unreadable,
    or its recorded hostname doesn't match this machine's — a hostname
    mismatch falls through to live detection rather than silently applying
    another machine's profile (A.3.1 rationale).
    """
    path = _cache_path or _CACHE_PATH
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None

    if data.get("hostname") != platform.node():
        return None

    gpu_vendor = data.get("gpu_vendor", "none")
    gpu: GPUInfo | None = None
    if gpu_vendor != "none":
        gpu = GPUInfo(
            vendor=gpu_vendor,
            name=data.get("gpu_name"),
            memory_mb=data.get("gpu_memory_mb"),
            is_unified_memory=bool(data.get("gpu_is_unified_memory", False)),
            vulkan_enabled=data.get("amd_vulkan_enabled"),
            rocm_disabled=data.get("amd_rocm_disabled"),
            vulkan_warning=data.get("amd_vulkan_warning"),
            group_warning=data.get("amd_group_warning"),
        )

    name = _suggest_profile_name(
        cpu_cores=int(data.get("cpu_cores", 0)),
        ram_gb=float(data.get("ram_gb", 0.0)),
        gpu=gpu,
    )
    return load_yaml_profile(name)


def _build_cache_dict(
    cpu_cores: int,
    ram_gb: float,
    gpu: GPUInfo | None,
    profile: HardwareProfile,
) -> dict:
    """Schema per SDD_ADDENDUM_7.5.md A.3.3."""
    is_amd = gpu is not None and gpu.vendor == "amd_apu"
    return {
        "hostname": platform.node(),
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "cpu_cores": cpu_cores,
        "ram_gb": ram_gb,
        "gpu_vendor": gpu.vendor if gpu else "none",
        "gpu_name": gpu.name if gpu else None,
        "gpu_memory_mb": gpu.memory_mb if gpu else None,
        "gpu_is_unified_memory": gpu.is_unified_memory if gpu else False,
        "amd_vulkan_enabled": gpu.vulkan_enabled if is_amd else None,
        "amd_rocm_disabled": gpu.rocm_disabled if is_amd else None,
        "amd_vulkan_warning": gpu.vulkan_warning if is_amd else None,
        "amd_group_warning": gpu.group_warning if is_amd else None,
        # Populated only by `tasker-hardware verify` once a backend's
        # verify_live() exists (7.5.3 NVIDIA / 7.5.5 AMD APU) -- detect()
        # alone always leaves these null.
        "gpu_verified_during_inference": None,
        "gpu_verified_size_vram_mb": None,
        "gpu_verified_offload_status": None,
        "computed_profile": {
            "orchestrator_tier_max": profile.orchestrator_tier_max,
            "max_concurrent_local": profile.max_concurrent_local,
            "load_strategy": "sequential" if profile.unload_between_tasks else "resident",
        },
    }


def _format_report(cache: dict, profile_name: str) -> str:
    lines = [
        "=== Ollama Tasker Hardware Detection ===",
        f"Hostname:          {cache['hostname']}",
        f"CPU cores:         {cache['cpu_cores']}",
        f"RAM:               {cache['ram_gb']:.1f} GB",
        f"GPU vendor:        {cache['gpu_vendor']}",
    ]
    if cache["gpu_vendor"] != "none":
        unified_note = (
            " (unified -- total system RAM, not dedicated VRAM)"
            if cache["gpu_is_unified_memory"] else ""
        )
        lines.append(f"GPU name:          {cache['gpu_name']}")
        lines.append(f"GPU memory:        {cache['gpu_memory_mb']} MB{unified_note}")
    cp = cache["computed_profile"]
    lines.append(f"Suggested profile: {profile_name}")
    lines.append(f"  orchestrator_tier_max: {cp['orchestrator_tier_max']}")
    lines.append(f"  max_concurrent_local:  {cp['max_concurrent_local']}")
    lines.append(f"  load_strategy:         {cp['load_strategy']}")
    return "\n".join(lines)


def _cmd_detect(*, _cache_path: Path | None = None) -> None:
    path = _cache_path or _CACHE_PATH
    cpu_cores, ram_gb, gpu, profile_name, profile = _run_live_detection()
    cache = _build_cache_dict(cpu_cores, ram_gb, gpu, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2)
    print(_format_report(cache, profile_name))
    print(f"\nCached to {path}")


def _cmd_verify(*, _cache_path: Path | None = None) -> None:
    path = _cache_path or _CACHE_PATH
    cpu_cores, ram_gb, gpu, profile_name, profile = _run_live_detection()
    cache = _build_cache_dict(cpu_cores, ram_gb, gpu, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2)
    print(_format_report(cache, profile_name))
    print()
    if cache["gpu_vendor"] == "nvidia":
        print(
            "Live GPU verification for NVIDIA requires Phase 7.5.3 "
            "(NvidiaBackend.verify_live()) -- not yet implemented this "
            "phase. Static detection above is all that's available."
        )
    elif cache["gpu_vendor"] == "amd_apu":
        print(
            "Live GPU verification for AMD APU requires Phase 7.5.5 "
            "(AmdApuBackend.verify_live()) -- not yet implemented this "
            "phase. Static detection above is all that's available."
        )
    else:
        print("No GPU detected -- nothing to verify.")


def _cmd_show(*, _cache_path: Path | None = None) -> None:
    path = _cache_path or _CACHE_PATH
    if not path.exists():
        print(f"No cache found at {path}. Run `tasker-hardware detect` first.")
        return
    with path.open(encoding="utf-8") as fh:
        cache = json.load(fh)
    print(json.dumps(cache, indent=2))


def _cmd_clear(*, _cache_path: Path | None = None) -> None:
    path = _cache_path or _CACHE_PATH
    if path.exists():
        path.unlink()
        print(f"Deleted {path}")
    else:
        print(f"No cache found at {path} -- nothing to clear.")


def cli_main(argv: list[str] | None = None, *, _cache_path: Path | None = None) -> None:
    """Entry point for the `tasker-hardware` console script (A.5)."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="tasker-hardware",
        description="Hardware detection applet for Ollama Tasker.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("detect", help="Run live detection, print a report, cache the result")
    sub.add_parser("verify", help="Detect, then attempt live GPU verification against Ollama")
    sub.add_parser("show", help="Print the cached detection result without re-detecting")
    sub.add_parser("clear", help="Delete the cached detection result")
    args = parser.parse_args(argv)

    if args.command == "detect":
        _cmd_detect(_cache_path=_cache_path)
    elif args.command == "verify":
        _cmd_verify(_cache_path=_cache_path)
    elif args.command == "show":
        _cmd_show(_cache_path=_cache_path)
    elif args.command == "clear":
        _cmd_clear(_cache_path=_cache_path)
