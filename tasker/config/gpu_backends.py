"""
tasker.config.gpu_backends
----------------------------
GPUBackend abstract base, GPUInfo data model, and the detection chain.

Phase 7.5.2 implemented the ABC, the data model, and NoGpuBackend.
Phase 7.5.3 added NvidiaBackend (detect + verify_live).
Phase 7.5.4-7.5.6 (this revision) adds AmdApuBackend (detect + verify_live),
Vulkan-based since AMD integrated graphics has no practical ROCm support.

See SDD_ADDENDUM_7.5.md A.4.
"""
from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import psutil

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


class AmdApuBackend(GPUBackend):
    """
    AMD integrated GPU (APU) detection via Vulkan (Mesa RADV). See A.4.4.

    AMD APUs are not practically supported by ROCm (see
    docs/Ollama_AMD_APU_Install_Guide.md Section 1 and
    docs/ollama-amd-igpu-config-guide.md Section 1) -- the correct path is
    Ollama's Vulkan compute backend, controlled by three env vars this
    backend inspects but does not set (setting them is an operator/systemd
    concern, not this backend's -- see the two AMD guides for the fix).

    detect() is fast and side-effect-free (lspci/CIM query, env var reads,
    grp module lookups -- no running-Ollama dependency). verify_live() is a
    separate, slower method requiring a running Ollama with a loaded model,
    called only by `tasker-hardware verify`.
    """

    def detect(self) -> GPUInfo | None:
        try:
            if platform.system() == "Windows":
                present, name = self._windows_amd_present()
            else:
                if shutil.which("lspci") is None:
                    return None
                present, name = self._linux_amd_present()

            if not present:
                return None

            self._vulkan_tooling_check()  # informational only, logged

            vulkan_enabled = os.environ.get("OLLAMA_VULKAN") == "1"
            rocm_disabled = (
                os.environ.get("ROCR_VISIBLE_DEVICES") == "-1"
                and os.environ.get("HIP_VISIBLE_DEVICES") == "-1"
            )

            if vulkan_enabled and not rocm_disabled:
                vulkan_warning = (
                    "OLLAMA_VULKAN=1 is set but ROCR_VISIBLE_DEVICES/"
                    "HIP_VISIBLE_DEVICES are not both '-1' -- on gfx902-class "
                    "chips (e.g. TASKER-P1's Ryzen 5 3500U) this risks a "
                    "silent runner crash via ROCm enumeration during GPU "
                    "discovery. See docs/ollama-amd-igpu-config-guide.md "
                    "Section 4."
                )
            elif not vulkan_enabled:
                vulkan_warning = (
                    "OLLAMA_VULKAN is not set to '1' -- Ollama will fall "
                    "back to CPU-only inference on this AMD GPU. See "
                    "docs/Ollama_AMD_APU_Install_Guide.md."
                )
            else:
                vulkan_warning = None

            group_warning = self._group_membership_warning()

            # TOTAL SYSTEM RAM, not a sysfs VRAM figure -- see GPUInfo
            # docstring / SDD_ADDENDUM_7.5.md A.4.2 for why the small BIOS
            # UMA carve-out at /sys/class/drm/card*/device/mem_info_vram_total
            # is not representative of the true usable pool under Vulkan/GTT.
            memory_mb = psutil.virtual_memory().total // (1024 * 1024)

            return GPUInfo(
                vendor="amd_apu",
                name=name or "AMD Integrated Graphics",
                memory_mb=memory_mb,
                is_unified_memory=True,
                vulkan_enabled=vulkan_enabled,
                rocm_disabled=rocm_disabled,
                vulkan_warning=vulkan_warning,
                group_warning=group_warning,
            )
        except Exception:
            logger.debug("AmdApuBackend.detect() failed", exc_info=True)
            return None

    def _linux_amd_present(self) -> tuple[bool, str | None]:
        """lspci -nn, vendor ID 1002 on a VGA/Display controller line."""
        try:
            result = subprocess.run(
                ["lspci", "-nn"], capture_output=True, text=True, timeout=5,
            )
        except Exception:
            return False, None
        if result.returncode != 0:
            return False, None
        for line in result.stdout.splitlines():
            lowered = line.lower()
            if ("vga" in lowered or "display" in lowered) and "[1002:" in line:
                name = line.split("]: ", 1)[-1].strip() if "]: " in line else line.strip()
                return True, name
        return False, None

    def _windows_amd_present(self) -> tuple[bool, str | None]:
        """Get-CimInstance Win32_VideoController, "AMD"/"Radeon" in name."""
        try:
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | "
                    "Select-Object -ExpandProperty Name",
                ],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            return False, None
        if result.returncode != 0:
            return False, None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped and ("amd" in stripped.lower() or "radeon" in stripped.lower()):
                return True, stripped
        return False, None

    def _vulkan_tooling_check(self) -> None:
        """Informational only -- never gates detect()'s return value."""
        if platform.system() == "Windows":
            return
        if shutil.which("vulkaninfo") is None:
            return
        try:
            result = subprocess.run(
                ["vulkaninfo", "--summary"], capture_output=True, text=True, timeout=5,
            )
            if "amd" not in result.stdout.lower():
                logger.debug("vulkaninfo --summary did not list an AMD device")
        except Exception:
            logger.debug("vulkaninfo --summary check failed", exc_info=True)

    def _group_membership_warning(self) -> str | None:
        """
        Linux-only, informational. Current user's membership in 'video' and
        'render' groups via the grp module (no subprocess) -- both the
        interactive shell user and the ollama service account need these
        for /dev/dri access (docs/ollama-amd-igpu-config-guide.md Section 3).
        Any lookup failure (including a group not existing on this system)
        is swallowed -- this check is advisory, never a hard block.
        """
        if platform.system() == "Windows":
            return None
        try:
            import grp

            current_gids = set(os.getgroups())
            current_gids.add(os.getgid())

            video_gid = grp.getgrnam("video").gr_gid
            render_gid = grp.getgrnam("render").gr_gid

            missing = []
            if video_gid not in current_gids:
                missing.append("video")
            if render_gid not in current_gids:
                missing.append("render")

            if missing:
                return (
                    f"Current user is not a member of required group(s): "
                    f"{', '.join(missing)}. See "
                    "docs/ollama-amd-igpu-config-guide.md Section 3."
                )
            return None
        except (KeyError, OSError, AttributeError):
            return None

    def verify_live(self, ollama_base_url: str) -> VerifyResult:
        """
        Primary: GET {base_url}/api/ps, size_vram field -- same pattern as
        NvidiaBackend.verify_live(). Linux supplementary: journalctl -u
        ollama -n 200 --no-pager, parsed in priority order for the gfx902
        crash signature / offload status -- when found, takes priority over
        the /api/ps-derived result since it can explain a "not engaged"
        state authoritatively. See A.4.4.
        """
        api_result = self._check_api_ps(ollama_base_url)
        journal_result = self._check_journalctl()
        return journal_result if journal_result is not None else api_result

    def _check_api_ps(self, ollama_base_url: str) -> VerifyResult:
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
            return VerifyResult(
                verified=False,
                size_vram_mb=None,
                offload_status="unknown",
                message=(
                    f"Model '{model_name}' is loaded but size_vram is 0 -- "
                    "GPU not engaged for this model."
                ),
            )

        size_vram_mb = size_vram // (1024 * 1024)
        offload_status: Literal["full", "partial", "unknown"] = (
            "partial" if size_total and size_vram < size_total else "full"
        )
        return VerifyResult(
            verified=True,
            size_vram_mb=size_vram_mb,
            offload_status=offload_status,
            message=(
                f"GPU engaged for model '{model_name}': {size_vram_mb} MB "
                f"VRAM ({offload_status} offload)."
            ),
        )

    def _check_journalctl(self) -> VerifyResult | None:
        """Bounded, non-blocking, read-only. Returns None if unavailable or
        nothing recognizable was found -- callers fall back to /api/ps."""
        if platform.system() == "Windows":
            return None
        try:
            result = subprocess.run(
                ["journalctl", "-u", "ollama", "-n", "200", "--no-pager"],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            return None
        if result.returncode != 0 or not result.stdout:
            return None

        log = result.stdout
        if "failure during gpu discovery" in log.lower() and "runner crashed" in log.lower():
            return VerifyResult(
                verified=False,
                size_vram_mb=None,
                offload_status="unknown",
                message=(
                    "journalctl shows 'failure during GPU discovery' / "
                    "'runner crashed' -- this is the gfx902-class "
                    "ROCm-enumeration crash. Ensure all four env vars are "
                    "set: OLLAMA_VULKAN=1, ROCR_VISIBLE_DEVICES=-1, "
                    "HIP_VISIBLE_DEVICES=-1, OLLAMA_FLASH_ATTENTION=1. See "
                    "docs/ollama-amd-igpu-config-guide.md Section 4."
                ),
            )

        matches = re.findall(r"offloaded (\d+)/(\d+) layers to GPU", log)
        if matches:
            n, m = (int(x) for x in matches[-1])
            if n == m:
                return VerifyResult(
                    verified=True,
                    size_vram_mb=None,
                    offload_status="full",
                    message=f"journalctl confirms full GPU offload: {n}/{m} layers.",
                )
            return VerifyResult(
                verified=True,
                size_vram_mb=None,
                offload_status="partial",
                message=(
                    f"journalctl shows partial GPU offload: {n}/{m} layers. "
                    "Consider reducing context length -- see "
                    "docs/ollama-amd-igpu-config-guide.md Section 9."
                ),
            )
        return None


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
    """
    result = NvidiaBackend().detect()
    if result is not None:
        return result

    result = AmdApuBackend().detect()
    if result is not None:
        return result

    return NoGpuBackend().detect()
