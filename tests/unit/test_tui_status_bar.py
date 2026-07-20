"""
Unit tests -- tasker/tui/widgets/status_bar.py (HardwareStatusBar)
SDD_ADDENDUM_PHASE8.md B.5.4 / Phase 8.3.

_read_matching_cache/load_cached_gpu_info are mocked -- no real
.tasker/hardware_profile.json filesystem access, no live detection.
"""
import unittest
from unittest import mock

from tasker.config.gpu_backends import GPUInfo
from tasker.tui.widgets.status_bar import HardwareStatusBar, _NOT_DETECTED


def _raw_cache(cpu_cores=8, ram_gb=32.0, tier_max=1, load_strategy="sequential") -> dict:
    return {
        "hostname": "test-host",
        "cpu_cores": cpu_cores,
        "ram_gb": ram_gb,
        "gpu_vendor": "none",
        "computed_profile": {
            "orchestrator_tier_max": tier_max,
            "max_concurrent_local": 1,
            "load_strategy": load_strategy,
        },
    }


class TestHardwareStatusBarRender(unittest.TestCase):

    def test_default_render_includes_placeholders(self):
        bar = HardwareStatusBar()
        text = bar.render()
        self.assertIn(_NOT_DETECTED, text)
        self.assertIn("[Model: none]", text)
        self.assertIn("[Session: READY]", text)

    def test_render_reflects_reactive_updates(self):
        bar = HardwareStatusBar()
        bar.hardware_summary = "[CPU: 4c/32GB]"
        bar.active_model = "lfm2.5-thinking:latest"
        bar.session_state = "RUNNING"
        text = bar.render()
        self.assertIn("[CPU: 4c/32GB]", text)
        self.assertIn("[Model: lfm2.5-thinking:latest]", text)
        self.assertIn("[Session: RUNNING]", text)


class TestRefreshHardware(unittest.TestCase):

    def test_no_cache_shows_not_detected(self):
        bar = HardwareStatusBar()
        with mock.patch("tasker.config.detect._read_matching_cache", return_value=None):
            bar.refresh_hardware()
        self.assertEqual(bar.hardware_summary, _NOT_DETECTED)

    def test_cache_present_no_gpu(self):
        bar = HardwareStatusBar()
        with mock.patch(
            "tasker.config.detect._read_matching_cache",
            return_value=_raw_cache(cpu_cores=4, ram_gb=32.0, tier_max=1, load_strategy="sequential"),
        ), mock.patch("tasker.config.detect.load_cached_gpu_info", return_value=None):
            bar.refresh_hardware()
        self.assertEqual(bar.hardware_summary, "[CPU: 4c/32GB] [GPU: none] [Tier: 1 / sequential]")

    def test_cache_present_with_gpu(self):
        bar = HardwareStatusBar()
        gpu = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        with mock.patch(
            "tasker.config.detect._read_matching_cache",
            return_value=_raw_cache(cpu_cores=12, ram_gb=15.3, tier_max=2, load_strategy="resident"),
        ), mock.patch("tasker.config.detect.load_cached_gpu_info", return_value=gpu):
            bar.refresh_hardware()
        self.assertEqual(
            bar.hardware_summary,
            "[CPU: 12c/15GB] [GPU: nvidia GTX 1050 Ti / 4096MB] [Tier: 2 / resident]",
        )

    def test_ram_gb_rounded_not_raw_float(self):
        """Regression: an unrounded float (e.g. 15.307815551757812) must
        not leak into the display."""
        bar = HardwareStatusBar()
        with mock.patch(
            "tasker.config.detect._read_matching_cache",
            return_value=_raw_cache(ram_gb=15.307815551757812),
        ), mock.patch("tasker.config.detect.load_cached_gpu_info", return_value=None):
            bar.refresh_hardware()
        self.assertIn("15GB", bar.hardware_summary)
        self.assertNotIn("15.3", bar.hardware_summary)

    def test_missing_computed_profile_falls_back_to_unknown_tier(self):
        bar = HardwareStatusBar()
        raw = _raw_cache()
        del raw["computed_profile"]
        with mock.patch("tasker.config.detect._read_matching_cache", return_value=raw), \
             mock.patch("tasker.config.detect.load_cached_gpu_info", return_value=None):
            bar.refresh_hardware()
        self.assertIn("[Tier: ? / ?]", bar.hardware_summary)


if __name__ == "__main__":
    unittest.main()
