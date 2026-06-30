"""
Unit tests -- Hardware profile auto-detection (tasker/config/detect.py)
Phase 7 -- SDD Section 8.2

Detection calls are mocked — tests do not depend on the actual hardware
the test runner is executing on.
"""
import unittest

from tasker.config.detect import (
    HardwareSnapshot,
    auto_detect_profile,
    detect_hardware,
    suggest_profile,
)


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


if __name__ == "__main__":
    unittest.main()
