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
    AmdApuBackend,
    GPUBackend,
    GPUInfo,
    NoGpuBackend,
    NvidiaBackend,
    VerifyResult,
    detect_gpu,
)


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


_LSPCI_AMD = (
    "00:02.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. "
    "[AMD/ATI] Picasso/Raven2 [1002:15d8]\n"
)
_LSPCI_INTEL = (
    "00:02.0 VGA compatible controller [0300]: Intel Corporation "
    "UHD Graphics [8086:9bc8]\n"
)


def _mem(total_gb: float):
    return mock.Mock(total=int(total_gb * 1024 ** 3))


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
        # Must also mock AmdApuBackend -- on a machine with real AMD
        # hardware (e.g. TASKER-P1), an unmocked AmdApuBackend.detect()
        # returns a genuine GPUInfo, breaking this test's "no GPU at all"
        # assumption. Caught live running the suite on TASKER-P1.
        with mock.patch.object(NvidiaBackend, "detect", return_value=None), \
             mock.patch.object(AmdApuBackend, "detect", return_value=None):
            self.assertIsNone(detect_gpu())

    def test_nvidia_wins_chain_when_present(self):
        info = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        with mock.patch.object(NvidiaBackend, "detect", return_value=info) as m_detect:
            result = detect_gpu()
        self.assertIs(result, info)
        m_detect.assert_called_once()

    def test_amd_apu_wins_chain_when_nvidia_absent(self):
        info = GPUInfo(vendor="amd_apu", name="Vega 8 Mobile", memory_mb=32768, is_unified_memory=True)
        with mock.patch.object(NvidiaBackend, "detect", return_value=None), \
             mock.patch.object(AmdApuBackend, "detect", return_value=info) as m_detect:
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


# ------------------------------------------------------------------ #
# AmdApuBackend.detect() -- presence check
# ------------------------------------------------------------------ #

class TestAmdApuBackendPresence(unittest.TestCase):

    def test_lspci_not_on_path_returns_none_without_subprocess(self):
        with mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.shutil.which", return_value=None), \
             mock.patch("tasker.config.gpu_backends.subprocess.run") as m_run:
            result = AmdApuBackend().detect()
        self.assertIsNone(result)
        m_run.assert_not_called()

    def test_lspci_present_amd_vendor_found(self):
        with mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/lspci"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, _LSPCI_AMD)), \
             mock.patch("tasker.config.gpu_backends.psutil.virtual_memory", return_value=_mem(32)), \
             mock.patch.dict("os.environ", {}, clear=True):
            result = AmdApuBackend().detect()
        self.assertIsNotNone(result)
        self.assertEqual(result.vendor, "amd_apu")

    def test_lspci_present_no_amd_vendor_returns_none(self):
        with mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/lspci"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, _LSPCI_INTEL)):
            result = AmdApuBackend().detect()
        self.assertIsNone(result)


# ------------------------------------------------------------------ #
# AmdApuBackend.detect() -- env var check
# ------------------------------------------------------------------ #

class TestAmdApuBackendEnvVars(unittest.TestCase):

    def _detect_with_env(self, env: dict):
        with mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/lspci"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, _LSPCI_AMD)), \
             mock.patch("tasker.config.gpu_backends.psutil.virtual_memory", return_value=_mem(32)), \
             mock.patch.dict("os.environ", env, clear=True):
            return AmdApuBackend().detect()

    def test_vulkan_only_warns_gfx902_risk(self):
        result = self._detect_with_env({"OLLAMA_VULKAN": "1"})
        self.assertTrue(result.vulkan_enabled)
        self.assertFalse(result.rocm_disabled)
        self.assertIn("gfx902", result.vulkan_warning)
        self.assertIn("ollama-amd-igpu-config-guide.md", result.vulkan_warning)

    def test_all_three_vars_correct_no_warning(self):
        result = self._detect_with_env({
            "OLLAMA_VULKAN": "1",
            "ROCR_VISIBLE_DEVICES": "-1",
            "HIP_VISIBLE_DEVICES": "-1",
        })
        self.assertTrue(result.vulkan_enabled)
        self.assertTrue(result.rocm_disabled)
        self.assertIsNone(result.vulkan_warning)

    def test_vulkan_unset_warns_general_guide(self):
        result = self._detect_with_env({})
        self.assertFalse(result.vulkan_enabled)
        self.assertIsNotNone(result.vulkan_warning)
        self.assertIn("Ollama_AMD_APU_Install_Guide.md", result.vulkan_warning)


# ------------------------------------------------------------------ #
# AmdApuBackend.detect() -- group membership check
# ------------------------------------------------------------------ #

class TestAmdApuBackendGroupCheck(unittest.TestCase):

    def _detect_with_groups(self, getgrnam_side_effect, getgroups_return, getgid_return=100):
        with mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/lspci"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, _LSPCI_AMD)), \
             mock.patch("tasker.config.gpu_backends.psutil.virtual_memory", return_value=_mem(32)), \
             mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch("os.getgroups", return_value=getgroups_return), \
             mock.patch("os.getgid", return_value=getgid_return), \
             mock.patch("grp.getgrnam", side_effect=getgrnam_side_effect):
            return AmdApuBackend().detect()

    def test_user_in_both_groups_no_warning(self):
        def side_effect(name):
            return {"video": mock.Mock(gr_gid=44), "render": mock.Mock(gr_gid=109)}[name]
        result = self._detect_with_groups(side_effect, getgroups_return=[44, 109], getgid_return=1000)
        self.assertIsNone(result.group_warning)

    def test_user_missing_render_warns_section3(self):
        def side_effect(name):
            return {"video": mock.Mock(gr_gid=44), "render": mock.Mock(gr_gid=109)}[name]
        result = self._detect_with_groups(side_effect, getgroups_return=[44], getgid_return=1000)
        self.assertIsNotNone(result.group_warning)
        self.assertIn("render", result.group_warning)
        self.assertIn("Section 3", result.group_warning)

    def test_group_does_not_exist_no_exception_no_warning(self):
        result = self._detect_with_groups(KeyError("no such group"), getgroups_return=[44, 109], getgid_return=1000)
        self.assertIsNone(result.group_warning)


# ------------------------------------------------------------------ #
# AmdApuBackend.detect() -- memory estimate
# ------------------------------------------------------------------ #

class TestAmdApuBackendMemory(unittest.TestCase):

    def test_memory_mb_is_total_system_ram_not_sysfs(self):
        with mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/lspci"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, _LSPCI_AMD)), \
             mock.patch("tasker.config.gpu_backends.psutil.virtual_memory", return_value=_mem(16)), \
             mock.patch.dict("os.environ", {}, clear=True):
            result = AmdApuBackend().detect()
        self.assertEqual(result.memory_mb, 16 * 1024)

    def test_is_unified_memory_true_unconditionally(self):
        with mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.shutil.which", return_value="/usr/bin/lspci"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, _LSPCI_AMD)), \
             mock.patch("tasker.config.gpu_backends.psutil.virtual_memory", return_value=_mem(32)), \
             mock.patch.dict("os.environ", {}, clear=True):
            result = AmdApuBackend().detect()
        self.assertTrue(result.is_unified_memory)


# ------------------------------------------------------------------ #
# AmdApuBackend.verify_live()
# ------------------------------------------------------------------ #

class TestAmdApuBackendVerifyLive(unittest.TestCase):

    def test_api_ps_size_vram_positive_verifies_true(self):
        payload = {"models": [{"name": "lfm2.5-thinking:latest", "size": 900_000_000, "size_vram": 900_000_000}]}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", side_effect=FileNotFoundError("no journalctl")):
            result = AmdApuBackend().verify_live("http://localhost:11434")
        self.assertTrue(result.verified)
        self.assertEqual(result.offload_status, "full")

    def test_journalctl_crash_signature_verified_false(self):
        journal_out = 'level=INFO msg="failure during GPU discovery" error="runner crashed"\n'
        payload = {"models": []}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, journal_out)):
            result = AmdApuBackend().verify_live("http://localhost:11434")
        self.assertFalse(result.verified)
        self.assertIn("Section 4", result.message)

    def test_journalctl_full_offload(self):
        journal_out = 'msg="offloaded 17/17 layers to GPU"\n'
        payload = {"models": []}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, journal_out)):
            result = AmdApuBackend().verify_live("http://localhost:11434")
        self.assertEqual(result.offload_status, "full")
        self.assertTrue(result.verified)

    def test_journalctl_partial_offload(self):
        journal_out = 'msg="offloaded 12/17 layers to GPU"\n'
        payload = {"models": []}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", return_value=_completed(0, journal_out)):
            result = AmdApuBackend().verify_live("http://localhost:11434")
        self.assertEqual(result.offload_status, "partial")
        self.assertTrue(result.verified)
        self.assertIn("Section 9", result.message)

    def test_journalctl_unavailable_falls_back_to_api_ps(self):
        payload = {"models": [{"name": "m", "size": 1000, "size_vram": 1000}]}
        with mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)), \
             mock.patch("tasker.config.gpu_backends.platform.system", return_value="Linux"), \
             mock.patch("tasker.config.gpu_backends.subprocess.run", side_effect=FileNotFoundError()):
            result = AmdApuBackend().verify_live("http://localhost:11434")
        self.assertTrue(result.verified)


if __name__ == "__main__":
    unittest.main()
