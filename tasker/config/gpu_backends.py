"""
tasker.config.gpu_backends
----------------------------
GPUBackend abstract base, GPUInfo data model, and the detection chain.

Phase 7.5.2 implemented the ABC, the data model, and NoGpuBackend.
Phase 7.5.3 (this revision) adds NvidiaBackend (detect + verify_live).
AmdApuBackend (7.5.4) is still a future extension point -- detect_gpu()
is structured so it only needs to uncomment one block when implemented.

See SDD_ADDENDUM_7.5.md A.4.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


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


@dataclass
class VerifyResult:
    """
    Result of a backend's verify_live() -- confirms GPU engagement during
    *actual inference*, as opposed to detect()'s static hardware presence
    check. Specific to the detection subsystem, not part of the
    WorkerManifest/WorkerResult contract in tasker/workers/base.py.
    """
    verified: bool
    size_vram_mb: int | None
    offload_status: Literal["full", "partial", "unknown"]
    message: str


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


class NvidiaBackend(GPUBackend):
    """
    NVIDIA discrete GPU detection via nvidia-smi. See A.4.3.

    detect() is fast and side-effect-free (one nvidia-smi call, no running
    Ollama dependency). verify_live() is a separate, slower method that
    requires a running Ollama with a loaded model -- called only by
    `tasker-hardware verify`, never as part of the normal startup path.
    """

    def detect(self) -> GPUInfo | None:
        if shutil.which("nvidia-smi") is None:
            return None
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None
            # One GPU expected per A.4.1's contract for this phase -- use
            # the first line if multiple GPUs are present.
            first_line = result.stdout.strip().splitlines()[0]
            name, memory_str = (p.strip() for p in first_line.split(",", 1))
            memory_mb = int(memory_str)
            return GPUInfo(
                vendor="nvidia",
                name=name,
                memory_mb=memory_mb,
                is_unified_memory=False,
                vulkan_enabled=None,    # not applicable for NVIDIA
                rocm_disabled=None,
                vulkan_warning=None,
                group_warning=None,
            )
        except Exception:
            logger.debug("NvidiaBackend.detect() failed", exc_info=True)
            return None

    def verify_live(self, ollama_base_url: str) -> VerifyResult:
        """
        Primary, authoritative check: GET {base_url}/api/ps, read the first
        loaded model's size_vram. The supplementary nvidia-smi utilization
        sample below is best-effort and can only CONFIRM a positive result
        (appended to the message) -- it never flips verified to False, since
        /api/ps is the authoritative source (A.4.4's verify_live() design,
        applied here to NVIDIA).
        """
        import json as _json
        import urllib.error
        import urllib.request

        url = ollama_base_url.rstrip("/") + "/api/ps"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = _json.loads(resp.read())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return VerifyResult(
                verified=False,
                size_vram_mb=None,
                offload_status="unknown",
                message=f"Could not reach Ollama at {ollama_base_url} ({exc}).",
            )

        models = data.get("models") or []
        if not models:
            return VerifyResult(
                verified=False,
                size_vram_mb=None,
                offload_status="unknown",
                message=(
                    "No model currently loaded in Ollama -- load a model "
                    "first, then run tasker-hardware verify"
                ),
            )

        model = models[0]
        size_vram = model.get("size_vram") or 0
        size_total = model.get("size") or 0
        model_name = model.get("name", "unknown")

        if size_vram <= 0:
            result = VerifyResult(
                verified=False,
                size_vram_mb=None,
                offload_status="unknown",
                message=(
                    f"Model '{model_name}' is loaded but size_vram is 0 -- "
                    "GPU not engaged for this model."
                ),
            )
        else:
            size_vram_mb = size_vram // (1024 * 1024)
            # size_total includes the GPU-resident + CPU-resident portions;
            # size_vram < size_total means some layers stayed on CPU.
            offload_status: Literal["full", "partial", "unknown"] = (
                "partial" if size_total and size_vram < size_total else "full"
            )
            result = VerifyResult(
                verified=True,
                size_vram_mb=size_vram_mb,
                offload_status=offload_status,
                message=(
                    f"GPU engaged for model '{model_name}': {size_vram_mb} MB "
                    f"VRAM ({offload_status} offload)."
                ),
            )

        # Supplementary, best-effort utilization sample -- never raises,
        # never changes `verified`/`offload_status`, only enriches message.
        try:
            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader", "-l", "1"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            util_output = proc.stdout
        except subprocess.TimeoutExpired as exc:
            # `-l 1` loops forever and never exits on its own, so this is
            # the path every real call takes. CPython's TimeoutExpired.stdout
            # comes back as raw bytes here even though text=True was passed
            # to the original call -- decode defensively.
            raw = exc.stdout or b""
            util_output = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        except Exception:
            util_output = ""

        if result.verified and util_output.strip():
            sample = util_output.strip().splitlines()[0].strip()
            result = VerifyResult(
                verified=result.verified,
                size_vram_mb=result.size_vram_mb,
                offload_status=result.offload_status,
                message=f"{result.message} nvidia-smi utilization sample: {sample}.",
            )

        return result


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

    AmdApuBackend (7.5.4) doesn't exist yet -- this phase (7.5.3) wires
    NvidiaBackend. 7.5.4 only needs to uncomment its block below; no other
    change to this function should be needed.
    """
    result = NvidiaBackend().detect()
    if result is not None:
        return result

    # from tasker.config.gpu_backends_amd import AmdApuBackend
    # result = AmdApuBackend().detect()
    # if result is not None:
    #     return result

    return NoGpuBackend().detect()
