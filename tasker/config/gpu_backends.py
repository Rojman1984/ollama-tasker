"""
tasker.config.gpu_backends
----------------------------
GPUBackend abstract base, GPUInfo data model, and the detection chain.

This phase (7.5.2) implements only the ABC, the data model, and
NoGpuBackend. NvidiaBackend (7.5.3) and AmdApuBackend (7.5.4) are future
extension points -- detect_gpu() is structured so each only needs to
uncomment one line when implemented.

See SDD_ADDENDUM_7.5.md A.4.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass
class GPUInfo:
    """
    Detected GPU info, vendor-normalized.

    memory_mb semantics differ sharply by vendor -- this is the single most
    important nuance in this subsystem (SDD_ADDENDUM_7.5.md A.4.2):
      - vendor == "nvidia": memory_mb is true dedicated VRAM reported by
        nvidia-smi.
      - vendor == "amd_apu": memory_mb is set to TOTAL SYSTEM RAM, not any
        GPU-reported figure. AMD APUs dynamically allocate graphics memory
        from system RAM via GTT on top of a small, often misleading, fixed
        BIOS UMA carve-out (typically 512MB-2GB, queryable at
        /sys/class/drm/card*/device/mem_info_vram_total but NOT
        representative of the true usable pool). Treating that sysfs number
        as "the VRAM" would dramatically understate what's actually
        available to Ollama via Vulkan.
    is_unified_memory=True is the flag downstream tier-computation and
    worker-VRAM-cross-check logic must branch on before doing any
    VRAM-vs-system-RAM arithmetic involving memory_mb.
    """
    vendor: Literal["nvidia", "amd_apu", "none"]
    name: str | None
    memory_mb: int | None
    is_unified_memory: bool

    # AMD-APU-specific (None for other vendors)
    vulkan_enabled: bool | None = None
    rocm_disabled: bool | None = None
    vulkan_warning: str | None = None
    group_warning: str | None = None


class GPUBackend(ABC):
    """
    One vendor/strategy's GPU detection logic. See A.4.1.

    detect() contract:
      - MUST NOT raise -- catch all subprocess/filesystem errors internally
        and return None on any failure.
      - MUST check tooling/platform preconditions (shutil.which,
        platform.system()) BEFORE attempting any subprocess call, so
        irrelevant backends short-circuit immediately on the wrong
        platform/hardware.
    """

    @abstractmethod
    def detect(self) -> GPUInfo | None:
        """Return GPUInfo if this backend's hardware/tooling is present on
        this machine, else None."""
        raise NotImplementedError


class NoGpuBackend(GPUBackend):
    """Final fallback in the detection chain -- always returns None."""

    def detect(self) -> GPUInfo | None:
        return None


def detect_gpu() -> GPUInfo | None:
    """
    Run the detection chain in priority order: NvidiaBackend -> AmdApuBackend
    -> NoGpuBackend. On a machine with both an AMD APU and a discrete NVIDIA
    card, NVIDIA wins -- a documented judgment call (A.4.3), not an
    oversight.

    NvidiaBackend (7.5.3) and AmdApuBackend (7.5.4) don't exist yet -- this
    phase (7.5.2) only wires NoGpuBackend, which always returns None. Each
    future sub-phase uncomments its one line below; no other change to this
    function should be needed.
    """
    # from tasker.config.gpu_backends_nvidia import NvidiaBackend
    # result = NvidiaBackend().detect()
    # if result is not None:
    #     return result

    # from tasker.config.gpu_backends_amd import AmdApuBackend
    # result = AmdApuBackend().detect()
    # if result is not None:
    #     return result

    return NoGpuBackend().detect()
