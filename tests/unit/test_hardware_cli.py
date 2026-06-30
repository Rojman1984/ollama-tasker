"""
Unit tests -- `tasker-hardware` CLI applet (tasker/config/detect.py cli_main())
Phase 7.5.2 -- SDD_ADDENDUM_7.5.md A.5
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tasker.config.detect import cli_main


def _run(argv: list[str], cache_path: Path) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli_main(argv, _cache_path=cache_path)
    return buf.getvalue()


class TestHardwareCliShow(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp.name) / "hardware_profile.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_show_with_no_cache_reports_cleanly(self):
        # Must not raise (== exit 0 for a console-script entry point).
        output = _run(["show"], self.cache_path)
        self.assertIn("No cache found", output)

    def test_show_with_existing_cache_prints_contents(self):
        data = {"hostname": "test-host", "cpu_cores": 8, "gpu_vendor": "none"}
        self.cache_path.write_text(json.dumps(data))
        output = _run(["show"], self.cache_path)
        self.assertIn("test-host", output)
        self.assertIn('"cpu_cores": 8', output)


class TestHardwareCliClear(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp.name) / "hardware_profile.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_clear_with_no_cache_is_a_clean_noop(self):
        output = _run(["clear"], self.cache_path)
        self.assertIn("nothing to clear", output.lower())
        self.assertFalse(self.cache_path.exists())

    def test_clear_with_existing_cache_deletes_it(self):
        self.cache_path.write_text(json.dumps({"hostname": "h"}))
        self.assertTrue(self.cache_path.exists())
        output = _run(["clear"], self.cache_path)
        self.assertIn("Deleted", output)
        self.assertFalse(self.cache_path.exists())


class TestHardwareCliDetect(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp.name) / "hardware_profile.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_detect_writes_cache_and_prints_report(self):
        with mock.patch("tasker.config.detect._detect_cpu_cores", return_value=6), \
             mock.patch("tasker.config.detect._detect_ram_gb", return_value=32.0), \
             mock.patch("tasker.config.detect.detect_gpu", return_value=None):
            output = _run(["detect"], self.cache_path)
        self.assertTrue(self.cache_path.exists())
        self.assertIn("Hardware Detection", output)
        self.assertIn("Cached to", output)
        data = json.loads(self.cache_path.read_text())
        self.assertEqual(data["cpu_cores"], 6)
        self.assertEqual(data["gpu_vendor"], "none")


class TestHardwareCliVerify(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp.name) / "hardware_profile.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_verify_with_no_gpu_reports_nothing_to_verify(self):
        with mock.patch("tasker.config.detect._detect_cpu_cores", return_value=6), \
             mock.patch("tasker.config.detect._detect_ram_gb", return_value=32.0), \
             mock.patch("tasker.config.detect.detect_gpu", return_value=None):
            output = _run(["verify"], self.cache_path)
        self.assertIn("No GPU detected -- nothing to verify.", output)


if __name__ == "__main__":
    unittest.main()
