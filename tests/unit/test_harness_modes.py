"""
Unit tests -- Mode harness (Phases 5.1-5.3)
Phase 5 -- SDD Section 5.1
"""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tasker.modes.base import ExecutionConfig, HardwareProfile, ModeConfigurator, TaskerMode
from tasker.modes.chat import CHAT_MODE
from tasker.modes.code import CODE_MODE
from tasker.modes.cowork import COWORK_MODE, CoworkRunner
from tasker.modes.research import RESEARCH_MODE
from tasker.modes.secure import SECURE_MODE
from tasker.session.budget import OllamaSessionBudget
from tasker.session.checkpoint import CheckpointStore
from tasker.session.manager import SessionManager
from tasker.session.notifier import LogNotifier
from tasker.tools.bundles import (
    BUNDLES,
    CHAT_BUNDLE,
    CODE_BUNDLE,
    COWORK_BUNDLE,
    NETWORK_TOOLS,
    RESEARCH_BUNDLE,
    SECURE_BUNDLE,
    secure_bundle,
)
from tasker.workers.base import (
    AgentRole,
    Capability,
    ExecutionPlan,
    InteractionPattern,
    MemoryScope,
    OllamaPlan,
    PlanStep,
    PrivacyTier,
    RoutingPolicy,
    SessionState,
    StepStatus,
    ToolID,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _plan(task: str = "test task", steps: int = 3) -> ExecutionPlan:
    ps = [
        PlanStep(
            index=i,
            description=f"step {i}",
            role=AgentRole.WORKER,
            required_capabilities={Capability.TOOL_USE},
            depends_on=list(range(i)),
        )
        for i in range(steps)
    ]
    return ExecutionPlan(
        plan_id=f"plan-{task[:8]}",
        original_task=task,
        steps=ps,
        dependency_graph={i: list(range(i)) for i in range(steps)},
    )


def _exhausted_budget() -> OllamaSessionBudget:
    """PRO plan budget at exactly 100% session usage."""
    return OllamaSessionBudget(
        plan=OllamaPlan.PRO,
        window_start=datetime.now().astimezone(),
        usage_consumed=3000.0,   # == _SESSION_LIMIT[PRO]
    )


def _fresh_budget() -> OllamaSessionBudget:
    return OllamaSessionBudget(
        plan=OllamaPlan.PRO,
        window_start=datetime.now().astimezone(),
        usage_consumed=0.0,
    )


# --------------------------------------------------------------------------- #
# 5.1 -- Bundle correctness
# --------------------------------------------------------------------------- #

class TestBundles(unittest.TestCase):

    def test_chat_bundle_members(self):
        self.assertIn(ToolID.SEARCH, CHAT_BUNDLE)
        self.assertIn(ToolID.CALCULATOR, CHAT_BUNDLE)
        self.assertIn(ToolID.MEMORY_READ, CHAT_BUNDLE)
        self.assertEqual(len(CHAT_BUNDLE), 3)

    def test_code_bundle_members(self):
        for tid in (ToolID.BASH, ToolID.FILE_READ, ToolID.FILE_WRITE,
                    ToolID.GIT, ToolID.LINTER, ToolID.TEST_RUNNER, ToolID.CODE_SEARCH):
            self.assertIn(tid, CODE_BUNDLE)
        self.assertEqual(len(CODE_BUNDLE), 7)

    def test_cowork_bundle_is_superset_of_code(self):
        self.assertTrue(CODE_BUNDLE.issubset(COWORK_BUNDLE))

    def test_cowork_bundle_has_async_tools(self):
        for tid in (ToolID.CHECKPOINT_WRITE, ToolID.TASK_STATE,
                    ToolID.PROGRESS_REPORT, ToolID.WEB_SEARCH,
                    ToolID.RETRIEVE, ToolID.MCP_CALL_TOOL, ToolID.DELEGATE_AGENT):
            self.assertIn(tid, COWORK_BUNDLE)

    def test_research_bundle_members(self):
        for tid in (ToolID.WEB_SEARCH, ToolID.RETRIEVE, ToolID.PDF_EXTRACT,
                    ToolID.CITATION_TRACKER, ToolID.CONTRADICTION_DETECTOR):
            self.assertIn(tid, RESEARCH_BUNDLE)

    def test_secure_bundle_has_no_network_tools(self):
        self.assertTrue(SECURE_BUNDLE.isdisjoint(NETWORK_TOOLS))

    def test_secure_bundle_is_file_and_local_only(self):
        for tid in (ToolID.FILE_READ, ToolID.FILE_WRITE,
                    ToolID.LOCAL_SEARCH, ToolID.LOCAL_MEMORY):
            self.assertIn(tid, SECURE_BUNDLE)

    def test_secure_bundle_func_strips_network_from_chat(self):
        result = secure_bundle(CHAT_BUNDLE)
        self.assertNotIn(ToolID.SEARCH, result)           # SEARCH is network
        self.assertIn(ToolID.CALCULATOR, result)
        self.assertIn(ToolID.MEMORY_READ, result)

    def test_secure_bundle_func_strips_network_from_cowork(self):
        result = secure_bundle(COWORK_BUNDLE)
        for net_tool in NETWORK_TOOLS:
            self.assertNotIn(net_tool, result,
                             msg=f"{net_tool} should be stripped by secure_bundle()")

    def test_secure_bundle_func_strips_network_from_research(self):
        result = secure_bundle(RESEARCH_BUNDLE)
        for net_tool in NETWORK_TOOLS:
            self.assertNotIn(net_tool, result,
                             msg=f"{net_tool} should be stripped by secure_bundle()")
        # pdf_extract, citation_tracker, contradiction_detector are not network tools
        self.assertIn(ToolID.PDF_EXTRACT, result)
        self.assertIn(ToolID.CITATION_TRACKER, result)
        self.assertIn(ToolID.CONTRADICTION_DETECTOR, result)

    def test_bundles_dict_keys(self):
        self.assertEqual(set(BUNDLES.keys()), {"chat", "code", "cowork", "research", "secure"})


# --------------------------------------------------------------------------- #
# 5.2 -- Mode configs match SDD 5.1 table
# --------------------------------------------------------------------------- #

class TestModeConfigs(unittest.TestCase):

    def test_chat_mode(self):
        self.assertEqual(CHAT_MODE.name, "chat")
        self.assertEqual(CHAT_MODE.orchestrator_tier_max, 1)
        self.assertEqual(CHAT_MODE.routing_policy, RoutingPolicy.COST_OPTIMIZED)
        self.assertEqual(CHAT_MODE.interaction_pattern, InteractionPattern.SYNC_STREAM)
        self.assertEqual(CHAT_MODE.memory_scope, MemoryScope.SESSION)
        self.assertEqual(CHAT_MODE.privacy_tier, PrivacyTier.ANY_CLOUD)
        self.assertFalse(CHAT_MODE.private_hard_block)
        self.assertEqual(CHAT_MODE.tool_bundle, CHAT_BUNDLE)

    def test_code_mode(self):
        self.assertEqual(CODE_MODE.name, "code")
        self.assertEqual(CODE_MODE.orchestrator_tier_max, 1)
        self.assertEqual(CODE_MODE.routing_policy, RoutingPolicy.CAPABILITY_FIRST)
        self.assertEqual(CODE_MODE.interaction_pattern, InteractionPattern.CLI_REPL)
        self.assertEqual(CODE_MODE.memory_scope, MemoryScope.PROJECT_AWARE)
        self.assertEqual(CODE_MODE.privacy_tier, PrivacyTier.ANY_CLOUD)
        self.assertFalse(CODE_MODE.private_hard_block)
        self.assertEqual(CODE_MODE.tool_bundle, CODE_BUNDLE)

    def test_cowork_mode(self):
        self.assertEqual(COWORK_MODE.name, "cowork")
        self.assertEqual(COWORK_MODE.orchestrator_tier_max, 3)
        self.assertEqual(COWORK_MODE.routing_policy, RoutingPolicy.HYBRID)
        self.assertEqual(COWORK_MODE.interaction_pattern, InteractionPattern.ASYNC_CHECKPOINT)
        self.assertEqual(COWORK_MODE.memory_scope, MemoryScope.PROJECT_EPISODIC)
        self.assertEqual(COWORK_MODE.privacy_tier, PrivacyTier.ANY_CLOUD)
        self.assertFalse(COWORK_MODE.private_hard_block)
        self.assertEqual(COWORK_MODE.tool_bundle, COWORK_BUNDLE)

    def test_research_mode(self):
        self.assertEqual(RESEARCH_MODE.name, "research")
        self.assertEqual(RESEARCH_MODE.orchestrator_tier_max, 3)
        self.assertEqual(RESEARCH_MODE.routing_policy, RoutingPolicy.CAPABILITY_FIRST)
        self.assertEqual(RESEARCH_MODE.interaction_pattern, InteractionPattern.ASYNC_STREAM)
        self.assertEqual(RESEARCH_MODE.memory_scope, MemoryScope.RESEARCH_SESSION)
        self.assertEqual(RESEARCH_MODE.privacy_tier, PrivacyTier.ANY_CLOUD)
        self.assertFalse(RESEARCH_MODE.private_hard_block)
        self.assertEqual(RESEARCH_MODE.tool_bundle, RESEARCH_BUNDLE)

    def test_secure_mode(self):
        self.assertEqual(SECURE_MODE.name, "secure")
        self.assertEqual(SECURE_MODE.orchestrator_tier_max, 1)
        self.assertEqual(SECURE_MODE.routing_policy, RoutingPolicy.PRIVATE)
        self.assertEqual(SECURE_MODE.interaction_pattern, InteractionPattern.SYNC_STREAM)
        self.assertEqual(SECURE_MODE.memory_scope, MemoryScope.LOCAL_FILESYSTEM)
        self.assertEqual(SECURE_MODE.privacy_tier, PrivacyTier.LOCAL_ONLY)
        self.assertTrue(SECURE_MODE.private_hard_block)
        self.assertEqual(SECURE_MODE.tool_bundle, SECURE_BUNDLE)

    def test_secure_mode_has_no_network_tools(self):
        self.assertTrue(SECURE_MODE.tool_bundle.isdisjoint(NETWORK_TOOLS))

    def test_secure_mode_preference_is_local_only(self):
        from tasker.workers.base import ComputeLocation
        self.assertEqual(SECURE_MODE.worker_preference_order, [ComputeLocation.LOCAL_HARDWARE])


# --------------------------------------------------------------------------- #
# 5.2 -- ModeConfigurator YAML loading and resolution
# --------------------------------------------------------------------------- #

class TestModeConfigurator(unittest.TestCase):

    def setUp(self):
        self.cfg = ModeConfigurator()

    def test_load_tier1_profile(self):
        p = self.cfg.load_profile("tier1_tasker")
        self.assertEqual(p.orchestrator_tier_max, 1)
        self.assertEqual(p.ollama_plan, OllamaPlan.PRO)
        self.assertEqual(p.mode_constraints["cowork"]["behavior"], "sequential_only")
        self.assertEqual(p.mode_constraints["research"]["behavior"], "single_worker")

    def test_load_tier2_profile(self):
        p = self.cfg.load_profile("tier2_designlab")
        self.assertEqual(p.orchestrator_tier_max, 2)
        self.assertEqual(p.mode_constraints["cowork"]["behavior"], "limited_parallel")

    def test_load_chat_mode(self):
        m = self.cfg.load_mode("chat")
        self.assertEqual(m.routing_policy, RoutingPolicy.COST_OPTIMIZED)
        self.assertEqual(m.privacy_tier, PrivacyTier.ANY_CLOUD)

    def test_load_secure_mode(self):
        m = self.cfg.load_mode("secure")
        self.assertTrue(m.private_hard_block)
        self.assertEqual(m.privacy_tier, PrivacyTier.LOCAL_ONLY)

    def test_tier1_cowork_effective_tier_is_capped(self):
        ec = self.cfg.build("tier1_tasker", "cowork")
        # COWORK wants tier 3, TASKER-P1 supports tier 1 → effective = 1
        self.assertEqual(ec.effective_tier_max, 1)
        self.assertEqual(ec.cowork_behavior, "sequential_only")

    def test_tier2_cowork_effective_tier(self):
        ec = self.cfg.build("tier2_designlab", "cowork")
        # COWORK wants tier 3, Designlab supports tier 2 → effective = 2
        self.assertEqual(ec.effective_tier_max, 2)
        self.assertEqual(ec.cowork_behavior, "limited_parallel")

    def test_tier2_research_parallel_fetch(self):
        ec = self.cfg.build("tier2_designlab", "research")
        self.assertEqual(ec.research_behavior, "parallel_fetch")

    def test_tier0_secure_effective_tier(self):
        ec = self.cfg.build("tier0_minimal", "secure")
        # SECURE wants tier 1, tier0 supports tier 0 → effective = 0
        self.assertEqual(ec.effective_tier_max, 0)

    def test_missing_profile_raises(self):
        from tasker.workers.base import TaskerConfigError
        with self.assertRaises(TaskerConfigError):
            self.cfg.load_profile("nonexistent_profile")

    def test_missing_mode_raises(self):
        from tasker.workers.base import TaskerConfigError
        with self.assertRaises(TaskerConfigError):
            self.cfg.load_mode("nonexistent_mode")


# --------------------------------------------------------------------------- #
# 5.3 -- SECURE hard-block via WorkerSelector
# --------------------------------------------------------------------------- #

class TestSecureHardBlock(unittest.TestCase):

    def test_secure_policy_blocks_cloud_workers(self):
        """WorkerSelector raises TaskerPolicyError when SECURE mode is active."""
        from tasker.workers.base import (
            Capability,
            ComputeLocation,
            LatencyClass,
            ProviderType,
            ToolProtocol,
            WorkerManifest,
        )
        from tasker.workers.registry import WorkerSelector

        cloud_worker = WorkerManifest(
            id="cloud-1",
            provider=ProviderType.ANTHROPIC,
            model_id="claude-haiku-4-5-20251001",
            compute_location=ComputeLocation.DIRECT_CLOUD,
            capabilities={Capability.TOOL_USE},
            tool_protocol=ToolProtocol.NATIVE,
            context_window=200000,
            cost_input=0.80,
            cost_output=4.00,
            ollama_usage_level=None,
            latency_class=LatencyClass.MEDIUM,
            available=True,
            requires_gpu=False,
            vram_mb=None,
        )

        from tasker.workers.base import TaskerPolicyError
        with self.assertRaises(TaskerPolicyError):
            WorkerSelector.select(
                workers=[cloud_worker],
                required_capabilities={Capability.TOOL_USE},
                policy=SECURE_MODE.routing_policy,
                privacy_tier=SECURE_MODE.privacy_tier,
                slots_available=1,
                should_throttle=False,
            )

    def test_secure_privacy_tier_is_local_only(self):
        self.assertEqual(SECURE_MODE.privacy_tier, PrivacyTier.LOCAL_ONLY)

    def test_secure_private_hard_block_is_true(self):
        self.assertTrue(SECURE_MODE.private_hard_block)


# --------------------------------------------------------------------------- #
# 5.3 -- COWORK pause / checkpoint integration test
# --------------------------------------------------------------------------- #

class TestCoworkPauseOnExhaustion(unittest.IsolatedAsyncioTestCase):

    async def test_pause_checkpoint_written_on_budget_exhaustion(self):
        """
        Drive a 3-step plan through an exhausted budget.
        On the first tick() the session is exhausted → PAUSE.
        CoworkRunner must write a checkpoint and transition to PAUSED.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            store      = CheckpointStore(Path(tmpdir))
            notifier   = LogNotifier()
            budget     = _exhausted_budget()
            session_mgr = SessionManager(budget, store, notifier, auto_resume=False)

            runner = CoworkRunner(
                mode=COWORK_MODE,
                session_mgr=session_mgr,
                store=store,
                hardware_profile="tier1_tasker",
            )

            plan = _plan("multi-step research task", steps=3)
            result = await runner.run("multi-step research task", plan)

            # Runner must return None (halted before any output)
            self.assertIsNone(result)

            # Session state must be PAUSED
            self.assertEqual(session_mgr.state, SessionState.PAUSED)

            # Exactly one checkpoint must exist
            checkpoints = store.list_all()
            self.assertEqual(len(checkpoints), 1)

            cp = checkpoints[0]
            self.assertEqual(cp.original_task, "multi-step research task")
            self.assertEqual(cp.mode, "cowork")
            self.assertEqual(cp.hardware_profile, "tier1_tasker")
            self.assertEqual(cp.current_step_index, 0)

    async def test_full_plan_completes_when_budget_ok(self):
        """Ensure the runner finishes all steps when budget is healthy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store       = CheckpointStore(Path(tmpdir))
            notifier    = LogNotifier()
            budget      = _fresh_budget()
            session_mgr = SessionManager(budget, store, notifier, auto_resume=False)

            runner = CoworkRunner(
                mode=COWORK_MODE,
                session_mgr=session_mgr,
                store=store,
            )

            plan   = _plan("quick task", steps=2)
            result = await runner.run("quick task", plan)

            # Runner must return a non-None output
            self.assertIsNotNone(result)

            # No checkpoint should have been written
            self.assertEqual(store.list_all(), [])

            # All steps should be COMPLETED
            self.assertTrue(all(s.status == StepStatus.COMPLETED for s in plan.steps))

    async def test_checkpoint_plan_survives_round_trip(self):
        """Verify plan round-trips cleanly through Checkpoint serialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store       = CheckpointStore(Path(tmpdir))
            notifier    = LogNotifier()
            budget      = _exhausted_budget()
            session_mgr = SessionManager(budget, store, notifier, auto_resume=False)

            runner = CoworkRunner(
                mode=COWORK_MODE,
                session_mgr=session_mgr,
                store=store,
            )

            plan = _plan("serialization test", steps=2)
            await runner.run("serialization test", plan)

            cp    = store.load_latest()
            self.assertIsNotNone(cp)
            self.assertEqual(cp.plan.original_task, "serialization test")
            self.assertEqual(len(cp.plan.steps), 2)

    async def test_pause_mid_plan_records_completed_step(self):
        """
        Budget is fresh at start.  Step 0 executes successfully.  The step_fn
        then exhausts the budget so tick() before step 1 returns PAUSE.
        The checkpoint must record step_index=1 (where we paused) and
        completed_steps=[{step_index: 0, output: ...}] (what finished first).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            store      = CheckpointStore(Path(tmpdir))
            notifier   = LogNotifier()
            budget     = _fresh_budget()          # starts at 0%
            session_mgr = SessionManager(budget, store, notifier, auto_resume=False)

            executed: list[int] = []

            async def _step_fn(step):
                executed.append(step.index)
                if step.index == 0:
                    # Simulates expensive step 0 exhausting the PRO-plan budget
                    budget.record_usage(3000.0)   # == _SESSION_LIMIT[PRO]
                return f"output_of_step_{step.index}"

            runner = CoworkRunner(
                mode=COWORK_MODE,
                session_mgr=session_mgr,
                store=store,
                hardware_profile="tier1_tasker",
                _step_fn=_step_fn,
            )

            plan   = _plan("deep research task", steps=3)
            result = await runner.run("deep research task", plan)

            # Runner returns None — halted mid-plan
            self.assertIsNone(result)

            # Only step 0 actually ran; step 1 was blocked by the PAUSE directive
            self.assertEqual(executed, [0])

            # Session must be PAUSED
            self.assertEqual(session_mgr.state, SessionState.PAUSED)

            # Checkpoint reflects where we stopped and what completed
            cp = store.load_latest()
            self.assertIsNotNone(cp)
            self.assertEqual(cp.current_step_index, 1)          # paused entering step 1
            self.assertEqual(len(cp.completed_steps), 1)        # step 0 completed
            self.assertEqual(cp.completed_steps[0]["step_index"], 0)
            self.assertEqual(cp.completed_steps[0]["output"], "output_of_step_0")

            # Step 0 in the plan should be COMPLETED; steps 1 and 2 still PENDING
            self.assertEqual(plan.steps[0].status, StepStatus.COMPLETED)
            self.assertEqual(plan.steps[1].status, StepStatus.PENDING)
            self.assertEqual(plan.steps[2].status, StepStatus.PENDING)


# --------------------------------------------------------------------------- #
# CLI smoke test
# --------------------------------------------------------------------------- #

class TestCLIArgparse(unittest.TestCase):

    def test_build_parser_modes(self):
        from cli.shell import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["--mode", "code"])
        self.assertEqual(args.mode, "code")

    def test_build_parser_resume_last(self):
        from cli.shell import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["resume", "--last"])
        self.assertEqual(args.command, "resume")
        self.assertTrue(args.last)

    def test_build_parser_shell_command(self):
        from cli.shell import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["shell"])
        self.assertEqual(args.command, "shell")

    def test_build_parser_workers_command(self):
        from cli.shell import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["workers"])
        self.assertEqual(args.command, "workers")

    def test_build_parser_checkpoints_command(self):
        from cli.shell import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["checkpoints"])
        self.assertEqual(args.command, "checkpoints")


if __name__ == "__main__":
    unittest.main()
