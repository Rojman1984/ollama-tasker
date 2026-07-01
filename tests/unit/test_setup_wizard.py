"""
Unit tests -- tasker/setup/wizard.py
Phase 8.1 -- SDD_ADDENDUM_PHASE8.md B.3

All environment checks, detect_hardware_profile(), GPU backends, and
WorkerRegistry loading are mocked -- no live Ollama, subprocess, or
filesystem calls against the real project state.
"""
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from tasker.config.gpu_backends import GPUInfo, VerifyResult
from tasker.modes.base import HardwareProfile
from tasker.setup.wizard import (
    StepStatus,
    WizardStepResult,
    _step3_hardware,
    _step4_gpu_verify,
    _step6_worker_registry,
    run_wizard,
)
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    OllamaPlan,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
)


def _profile(name: str = "tier1_local_minimal", tier_max: int = 1, unload: bool = True) -> HardwareProfile:
    return HardwareProfile(
        name=name,
        description="test profile",
        orchestrator_tier_max=tier_max,
        orchestrator_model="lfm2.5-thinking:latest",
        ollama_plan=OllamaPlan.PRO,
        max_concurrent_local=1,
        max_concurrent_ollama_cloud=1,
        unload_between_tasks=unload,
        ollama_base_url="http://localhost:11434",
        session_throttle_at=0.90,
        weekly_throttle_at=0.85,
        mode_constraints={},
    )


def _worker(worker_id: str, model_id: str, protocol: ToolProtocol) -> WorkerManifest:
    return WorkerManifest(
        id=worker_id,
        provider=ProviderType.OLLAMA,
        model_id=model_id,
        compute_location=ComputeLocation.LOCAL_HARDWARE,
        capabilities={Capability.TOOL_USE, Capability.CODE},
        tool_protocol=protocol,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


class _MockHttpResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_all_external(stack: ExitStack, cache_path: Path) -> None:
    """
    Hermetically mock every external touchpoint run_wizard() reaches across
    all 6 steps -- no live Ollama, subprocess, or network calls, and no
    writes outside the given temp cache_path. Per B.9: no live Ollama calls
    in unit tests.
    """
    profile = _profile(name="tier1_local_minimal", tier_max=1, unload=True)

    stack.enter_context(mock.patch(
        "tasker.setup.environment.check_ollama_service",
        return_value=WizardStepResult(
            step_id="2.3", step_name="Ollama service reachability", status=StepStatus.OK,
            message="mocked reachable", detail=None, action_required=None, can_continue=True,
        ),
    ))
    stack.enter_context(mock.patch(
        "tasker.setup.environment.check_ollama_version",
        return_value=WizardStepResult(
            step_id="2.2", step_name="Ollama version check", status=StepStatus.OK,
            message="mocked version", detail=None, action_required=None, can_continue=True,
        ),
    ))
    stack.enter_context(mock.patch("tasker.config.detect.detect_hardware_profile", return_value=profile))
    stack.enter_context(mock.patch("tasker.config.gpu_backends.detect_gpu", return_value=None))
    stack.enter_context(mock.patch(
        "tasker.config.detect._run_live_detection",
        return_value=(8, 32.0, None, "tier1_tasker", profile),
    ))
    stack.enter_context(mock.patch("tasker.config.detect._CACHE_PATH", cache_path))
    mock_registry = mock.Mock()
    mock_registry.list_all.return_value = [
        _worker("lfm2.5-local", "lfm2.5-thinking:latest", ToolProtocol.LFM25),
    ]
    stack.enter_context(mock.patch(
        "tasker.workers.registry.WorkerRegistry.load_from_yaml", return_value=mock_registry,
    ))


class TestRunWizardBasics(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp.name) / "hardware_profile.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_list_of_wizard_step_results(self):
        with ExitStack() as stack:
            _patch_all_external(stack, self.cache_path)
            results = run_wizard()

        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIsInstance(r, WizardStepResult)
        # Confirms the mocked cache path was actually used, not the real one.
        self.assertTrue(self.cache_path.exists())

    def test_all_steps_run_even_when_early_step_errors(self):
        with ExitStack() as stack:
            _patch_all_external(stack, self.cache_path)
            stack.enter_context(mock.patch(
                "tasker.setup.environment.check_ollama_binary",
                return_value=WizardStepResult(
                    step_id="2.1", step_name="Ollama binary detection",
                    status=StepStatus.ERROR, message="not found",
                    detail=None, action_required="install it", can_continue=False,
                ),
            ))
            results = run_wizard()

        step_ids = [r.step_id for r in results]
        # Step 2.1 errored (can_continue=False) but the wizard must still
        # collect results for later steps -- not abort early.
        self.assertIn("2.1", step_ids)
        self.assertIn("3.1", step_ids)
        self.assertIn("7", step_ids)
        error_result = next(r for r in results if r.step_id == "2.1")
        self.assertEqual(error_result.status, StepStatus.ERROR)
        self.assertFalse(error_result.can_continue)


class TestStep3Hardware(unittest.TestCase):

    def test_wraps_detect_hardware_profile_result(self):
        profile = _profile(name="tier2_local_standard", tier_max=2, unload=False)
        gpu = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        with mock.patch("tasker.config.detect.detect_hardware_profile", return_value=profile), \
             mock.patch("tasker.config.gpu_backends.detect_gpu", return_value=gpu):
            results = _step3_hardware()

        step31 = next(r for r in results if r.step_id == "3.1")
        self.assertEqual(step31.status, StepStatus.OK)
        self.assertIn("tier2_local_standard", step31.message)
        self.assertIn("orchestrator_tier_max=2", step31.message)
        self.assertIn("GTX 1050 Ti", step31.message)

    def test_amd_apu_missing_env_vars_lists_three_export_commands(self):
        profile = _profile()
        gpu = GPUInfo(vendor="amd_apu", name="Vega 8 Mobile", memory_mb=32768, is_unified_memory=True)
        with mock.patch("tasker.config.detect.detect_hardware_profile", return_value=profile), \
             mock.patch("tasker.config.gpu_backends.detect_gpu", return_value=gpu), \
             mock.patch.dict(
                 "os.environ",
                 {"OLLAMA_VULKAN": "", "ROCR_VISIBLE_DEVICES": "", "HIP_VISIBLE_DEVICES": ""},
             ):
            results = _step3_hardware()

        step33 = next(r for r in results if r.step_id == "3.3")
        self.assertEqual(step33.status, StepStatus.WARNING)
        self.assertIn("OLLAMA_VULKAN=1", step33.action_required)
        self.assertIn("ROCR_VISIBLE_DEVICES=-1", step33.action_required)
        self.assertIn("HIP_VISIBLE_DEVICES=-1", step33.action_required)

    def test_amd_apu_correct_env_vars_is_ok(self):
        profile = _profile()
        gpu = GPUInfo(vendor="amd_apu", name="Vega 8 Mobile", memory_mb=32768, is_unified_memory=True)
        with mock.patch("tasker.config.detect.detect_hardware_profile", return_value=profile), \
             mock.patch("tasker.config.gpu_backends.detect_gpu", return_value=gpu), \
             mock.patch.dict(
                 "os.environ",
                 {"OLLAMA_VULKAN": "1", "ROCR_VISIBLE_DEVICES": "-1", "HIP_VISIBLE_DEVICES": "-1"},
             ):
            results = _step3_hardware()

        step33 = next(r for r in results if r.step_id == "3.3")
        self.assertEqual(step33.status, StepStatus.OK)

    def test_no_gpu_message(self):
        profile = _profile()
        with mock.patch("tasker.config.detect.detect_hardware_profile", return_value=profile), \
             mock.patch("tasker.config.gpu_backends.detect_gpu", return_value=None):
            results = _step3_hardware()

        step33 = next(r for r in results if r.step_id == "3.3")
        self.assertEqual(step33.status, StepStatus.OK)
        self.assertIn("No GPU detected", step33.message)


class TestStep4GpuVerify(unittest.TestCase):

    def test_skipped_when_no_gpu(self):
        with mock.patch("tasker.config.gpu_backends.detect_gpu", return_value=None):
            results = _step4_gpu_verify("http://localhost:11434")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, StepStatus.SKIPPED)

    def test_skipped_when_no_model_loaded(self):
        gpu = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        payload = {"models": []}
        with mock.patch("tasker.config.gpu_backends.detect_gpu", return_value=gpu), \
             mock.patch("urllib.request.urlopen", return_value=_MockHttpResponse(payload)):
            results = _step4_gpu_verify("http://localhost:11434")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, StepStatus.SKIPPED)
        self.assertIn("No model currently loaded", results[0].message)

    def test_ok_when_verified(self):
        gpu = GPUInfo(vendor="nvidia", name="GTX 1050 Ti", memory_mb=4096, is_unified_memory=False)
        verify_result = VerifyResult(
            verified=True, size_vram_mb=1024, offload_status="full",
            message="GPU engaged for model 'x': 1024 MB VRAM (full offload).",
        )
        with mock.patch("tasker.config.gpu_backends.detect_gpu", return_value=gpu), \
             mock.patch("tasker.config.gpu_backends.NvidiaBackend.verify_live", return_value=verify_result):
            results = _step4_gpu_verify("http://localhost:11434")
        self.assertEqual(results[0].status, StepStatus.OK)
        self.assertIn("GPU OFFLOAD CONFIRMED", results[0].message)

    def test_skipped_when_amd_apu_backend_not_implemented(self):
        gpu = GPUInfo(vendor="amd_apu", name="Vega 8 Mobile", memory_mb=32768, is_unified_memory=True)
        with mock.patch("tasker.config.gpu_backends.detect_gpu", return_value=gpu):
            results = _step4_gpu_verify("http://localhost:11434")
        self.assertEqual(results[0].status, StepStatus.SKIPPED)


class TestStep6WorkerRegistry(unittest.TestCase):

    def test_flags_native_lfm25_workers(self):
        workers = [
            _worker("lfm2.5-local", "lfm2.5-thinking:latest", ToolProtocol.NATIVE),
            _worker("claude-sonnet", "claude-sonnet-4-6", ToolProtocol.NATIVE),
        ]
        with mock.patch(
            "tasker.workers.registry.WorkerRegistry.load_from_yaml",
        ) as m_load:
            mock_registry = mock.Mock()
            mock_registry.list_all.return_value = workers
            m_load.return_value = mock_registry
            results = _step6_worker_registry()

        step63 = next(r for r in results if r.step_id == "6.3")
        self.assertEqual(step63.status, StepStatus.WARNING)
        self.assertIn("lfm2.5-local", step63.detail)
        self.assertIn("lfm2.5-local", step63.action_required)
        # The non-LFM2.5 native worker should not be flagged.
        self.assertNotIn("claude-sonnet", step63.detail)

    def test_no_stale_workers_is_ok(self):
        workers = [_worker("lfm2.5-local", "lfm2.5-thinking:latest", ToolProtocol.LFM25)]
        with mock.patch("tasker.workers.registry.WorkerRegistry.load_from_yaml") as m_load:
            mock_registry = mock.Mock()
            mock_registry.list_all.return_value = workers
            m_load.return_value = mock_registry
            results = _step6_worker_registry()

        step63 = next(r for r in results if r.step_id == "6.3")
        self.assertEqual(step63.status, StepStatus.OK)

    def test_registry_load_failure_is_error(self):
        with mock.patch(
            "tasker.workers.registry.WorkerRegistry.load_from_yaml",
            side_effect=OSError("no such file"),
        ):
            results = _step6_worker_registry()
        self.assertEqual(results[0].status, StepStatus.ERROR)
        self.assertFalse(results[0].can_continue)


if __name__ == "__main__":
    unittest.main()
