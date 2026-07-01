"""
Unit tests -- tasker/setup/environment.py
Phase 8.1 -- SDD_ADDENDUM_PHASE8.md B.3.2 (steps 1-2), B.6 (WSL2 detection)

All filesystem, subprocess, and network calls are mocked.
"""
import unittest
from collections import namedtuple
from unittest import mock

from tasker.setup.environment import (
    check_ollama_binary,
    check_ollama_service,
    check_python,
    is_wsl2,
)
from tasker.setup.wizard import StepStatus

_VersionInfo = namedtuple("version_info", ["major", "minor", "micro", "releaselevel", "serial"])


class TestIsWsl2(unittest.TestCase):

    def test_microsoft_in_proc_version_true(self):
        with mock.patch("tasker.setup.environment.Path") as MockPath:
            MockPath.return_value.read_text.return_value = (
                "Linux version 5.10.0-microsoft-standard-WSL2 ..."
            )
            self.assertTrue(is_wsl2())

    def test_wsl_in_proc_version_true(self):
        with mock.patch("tasker.setup.environment.Path") as MockPath:
            MockPath.return_value.read_text.return_value = "Linux version 5.10.0-WSL-something"
            self.assertTrue(is_wsl2())

    def test_normal_linux_returns_false(self):
        with mock.patch("tasker.setup.environment.Path") as MockPath:
            MockPath.return_value.read_text.return_value = (
                "Linux version 6.8.0-generic (buildd@lcy02-amd64) ..."
            )
            self.assertFalse(is_wsl2())

    def test_proc_version_missing_returns_false(self):
        with mock.patch("tasker.setup.environment.Path") as MockPath:
            MockPath.return_value.read_text.side_effect = FileNotFoundError()
            self.assertFalse(is_wsl2())

    def test_proc_version_permission_error_returns_false(self):
        with mock.patch("tasker.setup.environment.Path") as MockPath:
            MockPath.return_value.read_text.side_effect = PermissionError()
            self.assertFalse(is_wsl2())


class TestCheckPython(unittest.TestCase):

    def test_311_or_newer_is_ok(self):
        vi = _VersionInfo(3, 11, 0, "final", 0)
        with mock.patch("tasker.setup.environment.sys.version_info", vi):
            result = check_python()
        self.assertEqual(result.status, StepStatus.OK)
        self.assertTrue(result.can_continue)

    def test_310_is_error(self):
        vi = _VersionInfo(3, 10, 0, "final", 0)
        with mock.patch("tasker.setup.environment.sys.version_info", vi):
            result = check_python()
        self.assertEqual(result.status, StepStatus.ERROR)
        self.assertFalse(result.can_continue)


class TestCheckOllamaBinary(unittest.TestCase):

    def test_found_is_ok(self):
        with mock.patch("tasker.setup.environment.shutil.which", return_value="/usr/local/bin/ollama"):
            result = check_ollama_binary()
        self.assertEqual(result.status, StepStatus.OK)
        self.assertTrue(result.can_continue)

    def test_not_found_is_error_with_install_action(self):
        with mock.patch("tasker.setup.environment.shutil.which", return_value=None):
            result = check_ollama_binary()
        self.assertEqual(result.status, StepStatus.ERROR)
        self.assertFalse(result.can_continue)
        self.assertIn("install.sh", result.action_required)


class _MockHttpResponse:
    def __init__(self, payload: dict):
        import json
        self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestCheckOllamaService(unittest.TestCase):

    def test_reachable_with_models_is_ok(self):
        payload = {"models": [{"name": "a"}, {"name": "b"}]}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)):
            result = check_ollama_service("http://localhost:11434")
        self.assertEqual(result.status, StepStatus.OK)
        self.assertIn("2 model(s)", result.message)

    def test_connection_refused_wsl2_action(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")), \
             mock.patch("tasker.setup.environment.is_wsl2", return_value=True):
            result = check_ollama_service("http://localhost:11434")
        self.assertEqual(result.status, StepStatus.ERROR)
        self.assertFalse(result.can_continue)
        self.assertIn("ollama serve", result.action_required)

    def test_connection_refused_native_systemd_action(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")), \
             mock.patch("tasker.setup.environment.is_wsl2", return_value=False), \
             mock.patch("tasker.setup.environment.shutil.which", return_value="/usr/bin/systemctl"):
            result = check_ollama_service("http://localhost:11434")
        self.assertEqual(result.status, StepStatus.ERROR)
        self.assertIn("systemctl start ollama", result.action_required)

    def test_connection_refused_native_no_systemd_action(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")), \
             mock.patch("tasker.setup.environment.is_wsl2", return_value=False), \
             mock.patch("tasker.setup.environment.shutil.which", return_value=None):
            result = check_ollama_service("http://localhost:11434")
        self.assertEqual(result.status, StepStatus.ERROR)
        self.assertIn("ollama serve", result.action_required)


if __name__ == "__main__":
    unittest.main()
