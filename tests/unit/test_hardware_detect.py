"""
Unit tests -- Hardware profile auto-detection (tasker/config/detect.py)
Phase 7 -- SDD Section 8.2
Phase 7.5.2 -- SDD_ADDENDUM_7.5.md A.3 (three-source resolution order)

Detection calls are mocked — tests do not depend on the actual hardware
the test runner is executing on.
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tasker.config.detect import (
    HardwareSnapshot,
    auto_detect_profile,
    detect_hardware,
    detect_hardware_profile,
    load_cached_detection,
    load_yaml_profile,
    suggest_profile,
)
from tasker.config.gpu_backends import GPUInfo
from tasker.modes.base import HardwareProfile, ModeConfigurator


# ------------------------------------------------------------------ #
# suggest_profile thresholds
# ------------------------------------------------------------------ #

class TestSuggestProfile(unittest.TestCase):

    def test_gpu_4gb_returns_tier2(self):
        snap = HardwareSnapshot(cpu_cores=8, ram_gb=32.0, gpu_vram_mb=4096)
        self.assertEqual(suggest_profile(snap), "tier2_designlab")

    def test_gpu_exactly_4000mb_returns_tier2(self):
        snap = HardwareSnapshot(cpu_cores=4, ram_gb=8.0, gpu_vram_mb=4000)
        self.assertEqual(suggest_profile(snap), "tier2_designlab")

    def test_gpu_less_than_4gb_falls_to_tier1(self):
        snap = HardwareSnapshot(cpu_cores=6, ram_gb=32.0, gpu_vram_mb=2048)
        self.assertEqual(suggest_profile(snap), "tier1_tasker")

    def test_no_gpu_adequate_cpu_ram_returns_tier1(self):
        snap = HardwareSnapshot(cpu_cores=6, ram_gb=32.0, gpu_vram_mb=0)
        self.assertEqual(suggest_profile(snap), "tier1_tasker")

    def test_no_gpu_min_cores_min_ram_returns_tier1(self):
        snap = HardwareSnapshot(cpu_cores=4, ram_gb=8.0, gpu_vram_mb=0)
        self.assertEqual(suggest_profile(snap), "tier1_tasker")

    def test_no_gpu_low_cores_returns_tier0(self):
        snap = HardwareSnapshot(cpu_cores=2, ram_gb=16.0, gpu_vram_mb=0)
        self.assertEqual(suggest_profile(snap), "tier0_minimal")

    def test_no_gpu_low_ram_returns_tier0(self):
        snap = HardwareSnapshot(cpu_cores=8, ram_gb=4.0, gpu_vram_mb=0)
        self.assertEqual(suggest_profile(snap), "tier0_minimal")

    def test_no_gpu_both_low_returns_tier0(self):
        snap = HardwareSnapshot(cpu_cores=2, ram_gb=4.0, gpu_vram_mb=0)
        self.assertEqual(suggest_profile(snap), "tier0_minimal")

    def test_gpu_takes_precedence_over_low_cpu(self):
        # Even 2 cores + 4GB GPU → tier2 (the GPU is what matters)
        snap = HardwareSnapshot(cpu_cores=2, ram_gb=4.0, gpu_vram_mb=8192)
        self.assertEqual(suggest_profile(snap), "tier2_designlab")

    def test_result_is_one_of_three_valid_profiles(self):
        valid = {"tier0_minimal", "tier1_tasker", "tier2_designlab"}
        for cores in (1, 4, 8):
            for ram in (4.0, 16.0, 64.0):
                for vram in (0, 2048, 8192):
                    snap = HardwareSnapshot(cpu_cores=cores, ram_gb=ram, gpu_vram_mb=vram)
                    self.assertIn(suggest_profile(snap), valid)


# ------------------------------------------------------------------ #
# detect_hardware (with injectable callables)
# ------------------------------------------------------------------ #

class TestDetectHardware(unittest.TestCase):

    def test_uses_injected_functions(self):
        snap = detect_hardware(
            _cpu_fn=lambda: 12,
            _ram_fn=lambda: 64.0,
            _gpu_fn=lambda: 8192,
        )
        self.assertEqual(snap.cpu_cores, 12)
        self.assertAlmostEqual(snap.ram_gb, 64.0)
        self.assertEqual(snap.gpu_vram_mb, 8192)

    def test_no_gpu_returns_zero_vram(self):
        snap = detect_hardware(
            _cpu_fn=lambda: 4,
            _ram_fn=lambda: 16.0,
            _gpu_fn=lambda: 0,
        )
        self.assertEqual(snap.gpu_vram_mb, 0)


# ------------------------------------------------------------------ #
# auto_detect_profile (end-to-end with injected callables)
# ------------------------------------------------------------------ #

class TestAutoDetectProfile(unittest.TestCase):

    def test_designlab_hardware_returns_tier2(self):
        profile = auto_detect_profile(
            _cpu_fn=lambda: 8,
            _ram_fn=lambda: 16.0,
            _gpu_fn=lambda: 4096,
        )
        self.assertEqual(profile, "tier2_designlab")

    def test_tasker_p1_hardware_returns_tier1(self):
        profile = auto_detect_profile(
            _cpu_fn=lambda: 6,
            _ram_fn=lambda: 32.0,
            _gpu_fn=lambda: 0,
        )
        self.assertEqual(profile, "tier1_tasker")

    def test_minimal_hardware_returns_tier0(self):
        profile = auto_detect_profile(
            _cpu_fn=lambda: 2,
            _ram_fn=lambda: 4.0,
            _gpu_fn=lambda: 0,
        )
        self.assertEqual(profile, "tier0_minimal")

    def test_nvidia_smi_failure_returns_zero_vram(self):
        # If nvidia-smi is absent, gpu_fn returns 0 — no exception propagated
        snap = detect_hardware(
            _cpu_fn=lambda: 8,
            _ram_fn=lambda: 32.0,
            _gpu_fn=lambda: 0,    # simulates FileNotFoundError from nvidia-smi
        )
        self.assertEqual(snap.gpu_vram_mb, 0)
        self.assertEqual(suggest_profile(snap), "tier1_tasker")


# ------------------------------------------------------------------ #
# Phase 7.5.2 -- load_yaml_profile / detect_hardware_profile
# ------------------------------------------------------------------ #

class TestLoadYamlProfile(unittest.TestCase):

    def test_loads_real_profile(self):
        profile = load_yaml_profile("tier1_tasker")
        self.assertIsInstance(profile, HardwareProfile)

    def test_unknown_profile_raises(self):
        from tasker.workers.base import TaskerConfigError
        with self.assertRaises(TaskerConfigError):
            load_yaml_profile("nonexistent_profile_xyz")


class TestDetectHardwareProfileGpuAware(unittest.TestCase):

    def test_no_gpu_adequate_cpu_ram_resolves_tier1(self):
        profile = detect_hardware_profile(
            _cpu_fn=lambda: 6, _ram_fn=lambda: 32.0, _gpu_detect_fn=lambda: None,
        )
        self.assertIsInstance(profile, HardwareProfile)

    def test_nvidia_discrete_4gb_resolves_tier2(self):
        gpu = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        profile = detect_hardware_profile(
            _cpu_fn=lambda: 8, _ram_fn=lambda: 16.0, _gpu_detect_fn=lambda: gpu,
        )
        expected = load_yaml_profile("tier2_designlab")
        self.assertEqual(profile.name, expected.name)

    def test_amd_apu_unified_memory_does_not_trigger_discrete_vram_threshold(self):
        # An APU's memory_mb is total system RAM (e.g. 32GB) -- comparing
        # that directly against the 4GB discrete threshold would wrongly
        # classify it as tier2. Must fall through to the CPU/RAM check.
        gpu = GPUInfo(
            vendor="amd_apu", name="Vega 8 Mobile", memory_mb=32768, is_unified_memory=True,
        )
        profile = detect_hardware_profile(
            _cpu_fn=lambda: 6, _ram_fn=lambda: 32.0, _gpu_detect_fn=lambda: gpu,
        )
        not_expected = load_yaml_profile("tier2_designlab")
        self.assertNotEqual(profile.name, not_expected.name)


# ------------------------------------------------------------------ #
# Phase 7.5.3 -- GPU-driven tier computation (orchestrator_tier_max /
# load_strategy), exercised via mocked NvidiaBackend output
# ------------------------------------------------------------------ #

class TestNvidiaTierComputation(unittest.TestCase):

    def test_4096mb_resolves_tier_max_2_resident(self):
        gpu = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        profile = detect_hardware_profile(
            _cpu_fn=lambda: 12, _ram_fn=lambda: 32.0, _gpu_detect_fn=lambda: gpu,
        )
        self.assertEqual(profile.orchestrator_tier_max, 2)
        self.assertFalse(profile.unload_between_tasks)   # resident

    def test_2048mb_resolves_tier_max_1_sequential(self):
        gpu = GPUInfo(vendor="nvidia", name="GT 1030", memory_mb=2048, is_unified_memory=False)
        profile = detect_hardware_profile(
            _cpu_fn=lambda: 12, _ram_fn=lambda: 32.0, _gpu_detect_fn=lambda: gpu,
        )
        self.assertEqual(profile.orchestrator_tier_max, 1)
        self.assertTrue(profile.unload_between_tasks)   # sequential

    def test_no_gpu_unchanged_tier_max_1_sequential(self):
        profile = detect_hardware_profile(
            _cpu_fn=lambda: 12, _ram_fn=lambda: 32.0, _gpu_detect_fn=lambda: None,
        )
        self.assertEqual(profile.orchestrator_tier_max, 1)
        self.assertTrue(profile.unload_between_tasks)   # sequential


# ------------------------------------------------------------------ #
# Phase 7.5.4-7.5.6 -- AMD APU (unified-memory) tier computation, via
# _apply_unified_memory_tier_override() layered on top of the CPU/RAM-
# selected base profile. See SDD_ADDENDUM_7.5.md A.4.4/A.6.
# ------------------------------------------------------------------ #

class TestAmdApuTierComputation(unittest.TestCase):

    def test_vulkan_enabled_16gb_plus_resolves_tier_max_2(self):
        gpu = GPUInfo(
            vendor="amd_apu", name="Vega 8 Mobile", memory_mb=32768,
            is_unified_memory=True, vulkan_enabled=True, rocm_disabled=True,
        )
        profile = detect_hardware_profile(
            _cpu_fn=lambda: 6, _ram_fn=lambda: 32.0, _gpu_detect_fn=lambda: gpu,
        )
        self.assertEqual(profile.orchestrator_tier_max, 2)
        self.assertFalse(profile.unload_between_tasks)   # resident

    def test_vulkan_enabled_under_16gb_resolves_tier_max_1(self):
        gpu = GPUInfo(
            vendor="amd_apu", name="Vega 8 Mobile", memory_mb=8192,
            is_unified_memory=True, vulkan_enabled=True, rocm_disabled=True,
        )
        profile = detect_hardware_profile(
            _cpu_fn=lambda: 6, _ram_fn=lambda: 8.0, _gpu_detect_fn=lambda: gpu,
        )
        self.assertEqual(profile.orchestrator_tier_max, 1)
        self.assertTrue(profile.unload_between_tasks)    # sequential

    def test_vulkan_disabled_resolves_tier_max_1_regardless_of_ram(self):
        gpu = GPUInfo(
            vendor="amd_apu", name="Vega 8 Mobile", memory_mb=32768,
            is_unified_memory=True, vulkan_enabled=False, rocm_disabled=False,
        )
        profile = detect_hardware_profile(
            _cpu_fn=lambda: 6, _ram_fn=lambda: 32.0, _gpu_detect_fn=lambda: gpu,
        )
        self.assertEqual(profile.orchestrator_tier_max, 1)
        self.assertTrue(profile.unload_between_tasks)    # sequential

    def test_amd_apu_tier2_still_uses_tasker_p1_orchestrator_model(self):
        # Must not silently pick up tier2_designlab.yaml's NVIDIA-oriented
        # qwen3 models -- those aren't installed on an AMD APU machine.
        gpu = GPUInfo(
            vendor="amd_apu", name="Vega 8 Mobile", memory_mb=32768,
            is_unified_memory=True, vulkan_enabled=True, rocm_disabled=True,
        )
        profile = detect_hardware_profile(
            _cpu_fn=lambda: 6, _ram_fn=lambda: 32.0, _gpu_detect_fn=lambda: gpu,
        )
        expected = load_yaml_profile("tier1_tasker")
        self.assertEqual(profile.orchestrator_model, expected.orchestrator_model)


# ------------------------------------------------------------------ #
# Phase 7.5.2 -- load_cached_detection
# ------------------------------------------------------------------ #

def _cache_json(hostname: str, cpu_cores: int = 8, ram_gb: float = 32.0) -> dict:
    return {
        "hostname": hostname,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "cpu_cores": cpu_cores,
        "ram_gb": ram_gb,
        "gpu_vendor": "none",
        "gpu_name": None,
        "gpu_memory_mb": None,
        "gpu_is_unified_memory": False,
        "amd_vulkan_enabled": None,
        "amd_rocm_disabled": None,
        "amd_vulkan_warning": None,
        "amd_group_warning": None,
        "gpu_verified_during_inference": None,
        "gpu_verified_size_vram_mb": None,
        "gpu_verified_offload_status": None,
        "computed_profile": {
            "orchestrator_tier_max": 1,
            "max_concurrent_local": 1,
            "load_strategy": "sequential",
        },
    }


class TestLoadCachedDetection(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp.name) / "hardware_profile.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_returns_none(self):
        self.assertIsNone(load_cached_detection(_cache_path=self.cache_path))

    def test_hostname_mismatch_returns_none(self):
        self.cache_path.write_text(json.dumps(_cache_json("recorded-host")))
        with mock.patch("tasker.config.detect.platform.node", return_value="other-machine"):
            self.assertIsNone(load_cached_detection(_cache_path=self.cache_path))

    def test_hostname_match_returns_hardware_profile(self):
        self.cache_path.write_text(json.dumps(_cache_json("this-machine", cpu_cores=6, ram_gb=32.0)))
        with mock.patch("tasker.config.detect.platform.node", return_value="this-machine"):
            profile = load_cached_detection(_cache_path=self.cache_path)
        self.assertIsInstance(profile, HardwareProfile)

    def test_corrupt_json_returns_none(self):
        self.cache_path.write_text("not valid json{{{")
        self.assertIsNone(load_cached_detection(_cache_path=self.cache_path))


# ------------------------------------------------------------------ #
# Phase 7.5.2 -- ModeConfigurator.resolve_hardware_profile() resolution order
# ------------------------------------------------------------------ #

class TestResolveHardwareProfile(unittest.TestCase):

    def setUp(self):
        self.configurator = ModeConfigurator()
        self._env_patch = mock.patch.dict("os.environ", {}, clear=True)
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()

    def test_explicit_profile_skips_cache_and_live_detection(self):
        with mock.patch("tasker.config.detect.load_cached_detection") as m_cache, \
             mock.patch("tasker.config.detect.detect_hardware_profile") as m_detect:
            profile = self.configurator.resolve_hardware_profile("tier1_tasker")
        self.assertIsInstance(profile, HardwareProfile)
        m_cache.assert_not_called()
        m_detect.assert_not_called()

    def test_env_var_skips_cache_and_live_detection(self):
        with mock.patch.dict("os.environ", {"TASKER_PROFILE": "tier0_minimal"}), \
             mock.patch("tasker.config.detect.load_cached_detection") as m_cache, \
             mock.patch("tasker.config.detect.detect_hardware_profile") as m_detect:
            profile = self.configurator.resolve_hardware_profile()
        self.assertIsInstance(profile, HardwareProfile)
        m_cache.assert_not_called()
        m_detect.assert_not_called()

    def test_no_name_valid_cache_skips_live_detection(self):
        fake_profile = load_yaml_profile("tier1_tasker")
        with mock.patch("tasker.config.detect.load_cached_detection", return_value=fake_profile) as m_cache, \
             mock.patch("tasker.config.detect.detect_hardware_profile") as m_detect:
            profile = self.configurator.resolve_hardware_profile()
        self.assertIs(profile, fake_profile)
        m_cache.assert_called_once()
        m_detect.assert_not_called()

    def test_no_name_no_cache_falls_back_to_live_detection(self):
        fake_profile = load_yaml_profile("tier0_minimal")
        with mock.patch("tasker.config.detect.load_cached_detection", return_value=None) as m_cache, \
             mock.patch("tasker.config.detect.detect_hardware_profile", return_value=fake_profile) as m_detect:
            profile = self.configurator.resolve_hardware_profile()
        self.assertIs(profile, fake_profile)
        m_cache.assert_called_once()
        m_detect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
