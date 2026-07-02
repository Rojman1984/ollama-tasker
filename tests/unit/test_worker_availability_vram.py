"""
Unit tests -- Worker VRAM cross-check (WorkerRegistry.apply_gpu_availability())
Phase 7.5.6 -- SDD_ADDENDUM_7.5.md A.3.4

Mocked GPUInfo throughout -- no live hardware needed.
"""
import unittest

from tasker.config.gpu_backends import GPUInfo
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
)
from tasker.workers.registry import WorkerRegistry


def _manifest(
    worker_id: str,
    requires_gpu: bool = False,
    vram_mb: int | None = None,
    available: bool = True,
) -> WorkerManifest:
    return WorkerManifest(
        id=worker_id,
        provider=ProviderType.OLLAMA,
        model_id="some-model:latest",
        compute_location=ComputeLocation.LOCAL_HARDWARE,
        capabilities={Capability.TOOL_USE, Capability.CODE},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=available,
        requires_gpu=requires_gpu,
        vram_mb=vram_mb,
    )


class TestNonGpuWorkersUntouched(unittest.TestCase):

    def test_requires_gpu_false_never_marked_unavailable(self):
        registry = WorkerRegistry()
        registry.register(_manifest("cpu-worker", requires_gpu=False))
        registry.apply_gpu_availability(None)
        self.assertTrue(registry.get("cpu-worker").available)

    def test_requires_gpu_false_untouched_even_with_gpu_present(self):
        gpu = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        registry = WorkerRegistry()
        registry.register(_manifest("cpu-worker", requires_gpu=False, available=True))
        registry.apply_gpu_availability(gpu)
        self.assertTrue(registry.get("cpu-worker").available)


class TestNoGpuDetected(unittest.TestCase):

    def test_gpu_none_marks_all_gpu_workers_unavailable(self):
        registry = WorkerRegistry()
        registry.register(_manifest("gpu-worker", requires_gpu=True, vram_mb=2048))
        registry.apply_gpu_availability(None)
        self.assertFalse(registry.get("gpu-worker").available)


class TestNvidiaDiscreteVram(unittest.TestCase):

    def test_worker_fits_within_discrete_vram_stays_available(self):
        gpu = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        registry = WorkerRegistry()
        registry.register(_manifest("small-gpu-worker", requires_gpu=True, vram_mb=2048))
        registry.apply_gpu_availability(gpu)
        self.assertTrue(registry.get("small-gpu-worker").available)

    def test_worker_exceeds_discrete_vram_marked_unavailable(self):
        gpu = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        registry = WorkerRegistry()
        registry.register(_manifest("big-gpu-worker", requires_gpu=True, vram_mb=8192))
        registry.apply_gpu_availability(gpu)
        self.assertFalse(registry.get("big-gpu-worker").available)

    def test_no_reserve_applied_for_discrete_vram(self):
        # Discrete VRAM is checked directly -- no unified-memory reserve
        # subtracted, unlike the AMD APU case below.
        gpu = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        registry = WorkerRegistry()
        registry.register(_manifest("exact-fit-worker", requires_gpu=True, vram_mb=4096))
        registry.apply_gpu_availability(gpu)
        self.assertTrue(registry.get("exact-fit-worker").available)


class TestAmdApuUnifiedMemoryReserve(unittest.TestCase):

    def test_worker_fits_within_ram_minus_reserve_stays_available(self):
        # 32GB total - 6GB default reserve = 26624MB usable
        gpu = GPUInfo(vendor="amd_apu", name="Vega 8 Mobile", memory_mb=32768, is_unified_memory=True)
        registry = WorkerRegistry()
        registry.register(_manifest("apu-worker", requires_gpu=True, vram_mb=2048))
        registry.apply_gpu_availability(gpu)
        self.assertTrue(registry.get("apu-worker").available)

    def test_worker_exceeds_ram_minus_reserve_marked_unavailable(self):
        # 8GB total - 6GB default reserve = 2048MB usable
        gpu = GPUInfo(vendor="amd_apu", name="Vega 8 Mobile", memory_mb=8192, is_unified_memory=True)
        registry = WorkerRegistry()
        registry.register(_manifest("apu-worker-big", requires_gpu=True, vram_mb=4096))
        registry.apply_gpu_availability(gpu)
        self.assertFalse(registry.get("apu-worker-big").available)

    def test_worker_fits_raw_total_but_not_after_reserve_marked_unavailable(self):
        # Would fit against raw 8192MB total, but not against the
        # reserve-adjusted 2048MB usable -- proves the reserve is actually
        # being subtracted, not just a no-op.
        gpu = GPUInfo(vendor="amd_apu", name="Vega 8 Mobile", memory_mb=8192, is_unified_memory=True)
        registry = WorkerRegistry()
        registry.register(_manifest("apu-worker-mid", requires_gpu=True, vram_mb=6000))
        registry.apply_gpu_availability(gpu)
        self.assertFalse(registry.get("apu-worker-mid").available)

    def test_custom_reserve_mb_respected(self):
        gpu = GPUInfo(vendor="amd_apu", name="Vega 8 Mobile", memory_mb=16384, is_unified_memory=True)
        registry = WorkerRegistry()
        registry.register(_manifest("apu-worker-custom", requires_gpu=True, vram_mb=15000))
        registry.apply_gpu_availability(gpu, reserve_mb=1024)
        self.assertTrue(registry.get("apu-worker-custom").available)

    def test_usable_memory_never_goes_negative(self):
        gpu = GPUInfo(vendor="amd_apu", name="Vega 8 Mobile", memory_mb=2048, is_unified_memory=True)
        registry = WorkerRegistry()
        registry.register(_manifest("apu-worker-tiny", requires_gpu=True, vram_mb=1))
        # reserve (6144) > total memory (2048) -- must not raise or wrap negative
        registry.apply_gpu_availability(gpu)
        self.assertFalse(registry.get("apu-worker-tiny").available)


class TestPreviouslyAvailableWorkerCanBeRevoked(unittest.TestCase):

    def test_worker_available_true_flipped_to_false_when_it_does_not_fit(self):
        gpu = GPUInfo(vendor="nvidia", name="GT 1030", memory_mb=2048, is_unified_memory=False)
        registry = WorkerRegistry()
        registry.register(_manifest("was-available", requires_gpu=True, vram_mb=8192, available=True))
        registry.apply_gpu_availability(gpu)
        self.assertFalse(registry.get("was-available").available)

    def test_worker_still_listed_via_list_all_after_being_marked_unavailable(self):
        # Never silently dropped from the registry / `tasker workers` output.
        registry = WorkerRegistry()
        registry.register(_manifest("dropped-worker", requires_gpu=True, vram_mb=8192))
        registry.apply_gpu_availability(None)
        ids = [w.id for w in registry.list_all()]
        self.assertIn("dropped-worker", ids)


if __name__ == "__main__":
    unittest.main()
