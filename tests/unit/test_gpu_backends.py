"""
Unit tests -- GPUBackend ABC, GPUInfo, NoGpuBackend, NvidiaBackend, detect_gpu()
Phase 7.5.2 -- SDD_ADDENDUM_7.5.md A.4
Phase 7.5.3 -- NvidiaBackend (A.4.1, A.4.3)

All subprocess/network calls are mocked -- tests do not depend on real
nvidia-smi or a running Ollama.
"""
import json
import subprocess
import unittest
from unittest import mock

from tasker.config.gpu_backends import (
    GPUBackend,
    GPUInfo,
    NoGpuBackend,
    NvidiaBackend,
    VerifyResult,
    detect_gpu,
)


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class _MockHttpResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


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

    def test_falls_through_to_no_gpu_when_nvidia_absent(self):
        with mock.patch.object(NvidiaBackend, "detect", return_value=None):
            self.assertIsNone(detect_gpu())

    def test_nvidia_wins_chain_when_present(self):
        info = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        with mock.patch.object(NvidiaBackend, "detect", return_value=info) as m_detect:
            result = detect_gpu()
        self.assertIs(result, info)
        m_detect.assert_called_once()


# ------------------------------------------------------------------ #
# NvidiaBackend.detect()
# ------------------------------------------------------------------ #

class TestNvidiaBackendDetect(unittest.TestCase):

    def test_nvidia_smi_not_on_path_returns_none_without_subprocess(self):
        with mock.patch("tasker.config.gpu_backends.shutil.which", return_value=None), \
             mock.patch("tasker.config.gpu_backends.subprocess.run") as m_run:
            result = NvidiaBackend().detect()
        self.assertIsNone(result)
        m_run.assert_not_called()

    def test_parses_well_formed_output(self):
        out = "NVIDIA GeForce GTX 1050 Ti, 4096\n"
        with mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/nvidia-smi"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, out)):
            result = NvidiaBackend().detect()
        self.assertIsNotNone(result)
        self.assertEqual(result.vendor, "nvidia")
        self.assertEqual(result.name, "NVIDIA GeForce GTX 1050 Ti")
        self.assertEqual(result.memory_mb, 4096)
        self.assertFalse(result.is_unified_memory)
        self.assertIsNone(result.vulkan_enabled)

    def test_nonzero_exit_code_returns_none(self):
        with mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/nvidia-smi"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(1, "")):
            result = NvidiaBackend().detect()
        self.assertIsNone(result)

    def test_malformed_output_returns_none(self):
        for bad_output in ("", "not csv at all", "NVIDIA GeForce GTX 1050 Ti\n"):
            with mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/nvidia-smi"), \
                 mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, bad_output)):
                self.assertIsNone(NvidiaBackend().detect(), f"expected None for {bad_output!r}")

    def test_subprocess_raises_returns_none(self):
        with mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/nvidia-smi"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", side_effect=OSError("boom")):
            result = NvidiaBackend().detect()
        self.assertIsNone(result)

    def test_timeout_returns_none(self):
        with mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/nvidia-smi"), \
             mock.patch(
                 "tasker.config.gpu_backends.subprocess.run",
                 side_effect=subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=5),
             ):
            result = NvidiaBackend().detect()
        self.assertIsNone(result)


# ------------------------------------------------------------------ #
# NvidiaBackend.verify_live()
# ------------------------------------------------------------------ #

class TestNvidiaBackendVerifyLive(unittest.TestCase):

    def _patch_utilization_sample(self):
        # Supplementary nvidia-smi call inside verify_live -- keep it inert
        # for tests that aren't specifically exercising it.
        return mock.patch(
            "tasker.config.gpu_backends.subprocess.run",
            side_effect=OSError("nvidia-smi not mocked for this test"),
        )

    def test_size_vram_positive_verifies_true(self):
        payload = {"models": [{"name": "lfm2.5-thinking:latest", "size": 2_000_000_000, "size_vram": 2_000_000_000}]}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             self._patch_utilization_sample():
            result = NvidiaBackend().verify_live("http://localhost:11434")
        self.assertIsInstance(result, VerifyResult)
        self.assertTrue(result.verified)
        self.assertEqual(result.size_vram_mb, 2_000_000_000 // (1024 * 1024))
        self.assertEqual(result.offload_status, "full")

    def test_size_vram_zero_verifies_false(self):
        payload = {"models": [{"name": "lfm2.5-thinking:latest", "size": 2_000_000_000, "size_vram": 0}]}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             self._patch_utilization_sample():
            result = NvidiaBackend().verify_live("http://localhost:11434")
        self.assertFalse(result.verified)
        self.assertIsNone(result.size_vram_mb)

    def test_partial_offload_detected(self):
        payload = {"models": [{"name": "big-model", "size": 8_000_000_000, "size_vram": 3_000_000_000}]}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             self._patch_utilization_sample():
            result = NvidiaBackend().verify_live("http://localhost:11434")
        self.assertTrue(result.verified)
        self.assertEqual(result.offload_status, "partial")

    def test_no_models_loaded(self):
        payload = {"models": []}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             self._patch_utilization_sample():
            result = NvidiaBackend().verify_live("http://localhost:11434")
        self.assertFalse(result.verified)
        self.assertIn("No model currently loaded", result.message)

    def test_connection_error_returns_could_not_reach(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            result = NvidiaBackend().verify_live("http://localhost:11434")
        self.assertFalse(result.verified)
        self.assertIn("could not reach", result.message.lower())

    def test_utilization_sample_failure_does_not_affect_verified(self):
        payload = {"models": [{"name": "m", "size": 1000, "size_vram": 1000}]}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", side_effect=OSError("no nvidia-smi")):
            result = NvidiaBackend().verify_live("http://localhost:11434")
        self.assertTrue(result.verified)

    def test_utilization_sample_success_confirms_but_does_not_flip(self):
        payload = {"models": [{"name": "m", "size": 1000, "size_vram": 1000}]}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, "45 %\n")):
            result = NvidiaBackend().verify_live("http://localhost:11434")
        self.assertTrue(result.verified)
        self.assertIn("utilization sample", result.message)

    def test_utilization_sample_via_timeout_path_decodes_bytes(self):
        # `-l 1` never exits on its own -- every real call hits
        # TimeoutExpired, whose .stdout is raw bytes even with text=True on
        # the original call (observed live on this machine). Must decode,
        # not leak a "b'...'" repr into the user-facing message.
        payload = {"models": [{"name": "m", "size": 1000, "size_vram": 1000}]}
        timeout_exc = subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=1.5)
        timeout_exc.stdout = b"0 %\n0 %\n"
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", side_effect=timeout_exc):
            result = NvidiaBackend().verify_live("http://localhost:11434")
        self.assertTrue(result.verified)
        self.assertIn("0 %", result.message)
        self.assertNotIn("b'", result.message)


if __name__ == "__main__":
    unittest.main()
