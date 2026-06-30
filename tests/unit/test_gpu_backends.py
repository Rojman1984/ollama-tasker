"""
Unit tests -- GPUBackend ABC, GPUInfo, NoGpuBackend, detect_gpu()
Phase 7.5.2 -- SDD_ADDENDUM_7.5.md A.4
"""
import unittest

from tasker.config.gpu_backends import GPUBackend, GPUInfo, NoGpuBackend, detect_gpu


class TestGPUInfo(unittest.TestCase):

    def test_constructs_with_all_fields(self):
        info = GPUInfo(
            vendor="nvidia",
            name="GeForce GTX 1050 Ti",
            memory_mb=4096,
            is_unified_memory=False,
            vulkan_enabled=None,
            rocm_disabled=None,
            vulkan_warning=None,
            group_warning=None,
        )
        self.assertEqual(info.vendor, "nvidia")
        self.assertEqual(info.name, "GeForce GTX 1050 Ti")
        self.assertEqual(info.memory_mb, 4096)
        self.assertFalse(info.is_unified_memory)

    def test_amd_specific_fields_default_to_none(self):
        info = GPUInfo(vendor="nvidia", name="card", memory_mb=4096, is_unified_memory=False)
        self.assertIsNone(info.vulkan_enabled)
        self.assertIsNone(info.rocm_disabled)
        self.assertIsNone(info.vulkan_warning)
        self.assertIsNone(info.group_warning)

    def test_amd_apu_unified_memory_true(self):
        info = GPUInfo(
            vendor="amd_apu",
            name="Vega 8 Mobile",
            memory_mb=32768,   # total system RAM, not dedicated VRAM
            is_unified_memory=True,
            vulkan_enabled=True,
            rocm_disabled=True,
        )
        self.assertTrue(info.is_unified_memory)
        self.assertEqual(info.vendor, "amd_apu")


class TestGPUBackendABC(unittest.TestCase):

    def test_cannot_instantiate_abc_directly(self):
        with self.assertRaises(TypeError):
            GPUBackend()  # type: ignore[abstract]


class TestNoGpuBackend(unittest.TestCase):

    def test_detect_returns_none(self):
        self.assertIsNone(NoGpuBackend().detect())

    def test_is_a_gpu_backend(self):
        self.assertIsInstance(NoGpuBackend(), GPUBackend)


class TestDetectGpuChain(unittest.TestCase):

    def test_returns_none_when_no_real_backend_exists_yet(self):
        # NvidiaBackend/AmdApuBackend aren't implemented until 7.5.3/7.5.4 --
        # this phase's chain always falls through to NoGpuBackend.
        self.assertIsNone(detect_gpu())


if __name__ == "__main__":
    unittest.main()
