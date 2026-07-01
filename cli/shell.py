"""
cli.shell
----------
Entry point for the `tasker` CLI command.

Non-interactive surface (argparse):
  tasker --mode <mode> "<task>"
  tasker --mode <mode> --policy <policy> "<task>"
  tasker resume <checkpoint_id>
  tasker resume --last
  tasker resume --last --policy local
  tasker checkpoints
  tasker workers
  tasker shell

Interactive REPL slash commands:
  /mode /workers /policy /secure /budget /checkpoint /resume /status /help

See SDD Section 7.6.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

from tasker.session.checkpoint import CheckpointStore
from tasker.workers.base import RoutingPolicy
from tasker.workers.registry import WorkerRegistry

# --------------------------------------------------------------------------- #
# Singletons shared between CLI surface and REPL
# --------------------------------------------------------------------------- #

_DEFAULT_STORE_DIR = Path(".tasker") / "checkpoints"
_REGISTRY_YAML = Path(__file__).parent.parent / "config" / "workers" / "worker_registry.yaml"

_POLICY_ALIASES: dict[str, str] = {
    "local":      "private",
    "cost":       "cost_optimized",
    "capability": "capability_first",
    "speed":      "speed_optimized",
    "hybrid":     "hybrid",
    "private":    "private",
}


# --------------------------------------------------------------------------- #
# Task execution
# --------------------------------------------------------------------------- #

async def _run_task(
    task: str,
    mode_name: str,
    registry: WorkerRegistry,
    store: CheckpointStore,
) -> None:
    """Dispatch a task through the orchestrator → provider pipeline."""
    from tasker.modes.base import ModeConfigurator
    from tasker.orchestrator.factory import build_orchestrator
    from tasker.tools.bundles import get_definitions, narrow_bundle_to_step
    from tasker.workers.base import (
        AgentRole,
        Capability,
        ClassifierResult,
        ProviderType,
        TaskType,
        WorkerStatus,
        WorkerTask,
    )
    from tasker.session.concurrency import OllamaCloudConcurrencyManager
    from tasker.tools.loop import run_tool_loop
    from tasker.workers.providers.ollama import OllamaProvider
    from tasker.workers.registry import WorkerSelector

    profile_name = os.environ.get("TASKER_PROFILE", "tier1_tasker")
    configurator = ModeConfigurator()
    try:
        profile = configurator.load_profile(profile_name)
        mode_cfg = configurator.load_mode(mode_name)
    except Exception as exc:
        print(f"Config error: {exc}")
        return

    config = configurator.resolve(profile, mode_cfg)
    # config.mode.tool_bundle is already the correct per-mode set -- SECURE's
    # bundle is pre-stripped of network tools at the YAML/TaskerMode level
    # (see tasker/tools/bundles.py secure_bundle()/SECURE_BUNDLE), so no
    # extra stripping is needed here. Per-step narrowing (see
    # narrow_bundle_to_step()) happens inside the step loop below, once
    # each step's description is known.
    #
    # One shared concurrency manager for the whole run -- covers both
    # regular worker dispatch (via WorkerSelector/run_tool_loop) and
    # orchestrator-level plan/synthesize/retry calls (via
    # build_orchestrator()'s call_model closures), since both paths route
    # through this same OllamaProvider instance. Previously never
    # constructed anywhere in production code, so OLLAMA_CLOUD calls on
    # either path proceeded without any concurrency slot-limiting.
    concurrency_mgr = OllamaCloudConcurrencyManager(profile.ollama_plan)
    ollama_provider = OllamaProvider(profile.ollama_base_url, concurrency_mgr)
    provider_map = {ProviderType.OLLAMA: ollama_provider}
    orchestrator = build_orchestrator(config, provider_map)

    all_workers = registry.list_all()
    classifier_output = ClassifierResult(
        task_type=TaskType.CONVERSATIONAL,
        complexity_score=0.3,
        required_capabilities={Capability.TOOL_USE},
        suggested_workers=[],
        estimated_duration_s=15.0,
    )

    print(f"[{mode_name}] Planning with {type(orchestrator).__name__}...")
    try:
        plan = await orchestrator.plan(task, classifier_output, all_workers)
    except Exception as exc:
        print(f"Planning failed: {type(exc).__name__}: {exc}")
        return

    print(f"  {len(plan.steps)} step(s)")
    results = []
    for step in plan.steps:
        print(f"  Step {step.index}: {step.description[:70]}...")
        try:
            worker = WorkerSelector.select(
                all_workers,
                step.required_capabilities,
                config.mode.routing_policy,
                config.mode.privacy_tier,
                slots_available=1,
                should_throttle=False,
            )
        except Exception as exc:
            print(f"  Worker selection failed: {exc}")
            continue

        step_tools = get_definitions(
            narrow_bundle_to_step(config.mode.tool_bundle, step.description)
        )
        wt = WorkerTask(
            task_id=str(uuid.uuid4()),
            step_index=step.index,
            role=step.role,
            instruction=step.description,
            tools=step_tools,
            context={},
            routing_policy=config.mode.routing_policy,
            privacy_tier=config.mode.privacy_tier,
        )
        provider = provider_map.get(worker.provider)
        if provider is None:
            print(f"  No provider for {worker.provider.value}")
            continue
        try:
            result = await run_tool_loop(wt, worker, provider, cwd=Path.cwd())
            status_str = "ok" if result.status == WorkerStatus.SUCCESS else result.status.value
            print(f"  [{status_str}] {worker.model_id} ({result.duration_ms}ms)")
            results.append(result)
        except Exception as exc:
            print(f"  Execution error: {exc}")

    if not results:
        print("No results to synthesize.")
        return

    print("\nSynthesizing...")
    try:
        output = await orchestrator.synthesize(task, results)
        print(f"\n{output}")
    except Exception as exc:
        print(f"Synthesis error: {exc}")


# --------------------------------------------------------------------------- #
# REPL helpers
# --------------------------------------------------------------------------- #

def _repl(
    registry: WorkerRegistry,
    store: CheckpointStore,
    initial_mode: str = "chat",
    initial_policy: str | None = None,
) -> None:
    mode   = initial_mode
    policy = initial_policy or "cost_optimized"
    secure = False

    print(f"Tasker REPL  |  mode={mode}  policy={policy}  secure={secure}")
    print("Type /help for commands, Ctrl-C or /quit to exit.\n")

    while True:
        try:
            line = input("tasker> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not line:
            continue

        if line.startswith("/"):
            parts = line.split(maxsplit=1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts) > 1 else ""

            if cmd in ("/quit", "/exit"):
                break

            elif cmd == "/mode":
                if arg:
                    mode = arg.lower()
                    print(f"Mode set to: {mode}")
                else:
                    print(f"Current mode: {mode}")

            elif cmd == "/policy":
                if arg:
                    policy = _POLICY_ALIASES.get(arg.lower(), arg.lower())
                    print(f"Policy set to: {policy}")
                else:
                    print(f"Current policy: {policy}")

            elif cmd == "/secure":
                toggle = arg.lower() if arg else ("off" if secure else "on")
                secure = toggle != "off"
                if secure:
                    mode   = "secure"
                    policy = "private"
                print(f"Secure mode: {'ON — LOCAL_ONLY enforced' if secure else 'OFF'}")

            elif cmd == "/workers":
                workers = registry.list_all()
                if not workers:
                    print("(no workers registered)")
                for w in workers:
                    status = "available" if w.available else "unavailable"
                    print(f"  {w.id:30s}  {w.model_id:25s}  {w.compute_location.value:12s}  {status}")

            elif cmd == "/budget":
                print("(budget tracking not active in REPL — start a task to initialise)")

            elif cmd == "/checkpoint":
                checkpoints = store.list_all()
                if not checkpoints:
                    print("(no checkpoints)")
                for cp in checkpoints:
                    print(f"  {cp.id}  [{cp.mode}]  {cp.created_at.strftime('%Y-%m-%d %H:%M')}  {cp.original_task[:40]}")

            elif cmd == "/resume":
                if not arg:
                    print("Usage: /resume <checkpoint_id>  or  /resume --last")
                elif arg == "--last":
                    cp = store.load_latest()
                    if cp is None:
                        print("No checkpoints found.")
                    else:
                        print(f"Would resume checkpoint {cp.id} (full resume requires active session).")
                else:
                    cp = store.load(arg)
                    if cp is None:
                        print(f"Checkpoint not found: {arg}")
                    else:
                        print(f"Would resume checkpoint {cp.id} (full resume requires active session).")

            elif cmd == "/status":
                print(f"mode={mode}  policy={policy}  secure={secure}")

            elif cmd == "/help":
                print(
                    "  /mode <mode>        switch mode (chat|code|cowork|research|secure)\n"
                    "  /workers            list registered workers\n"
                    "  /policy <policy>    change routing policy\n"
                    "  /secure [on|off]    toggle SECURE mode\n"
                    "  /budget             show session budget\n"
                    "  /checkpoint         list checkpoints\n"
                    "  /resume <id|--last> resume from checkpoint\n"
                    "  /status             show current session state\n"
                    "  /help               this message\n"
                    "  /quit               exit"
                )

            else:
                print(f"Unknown command: {cmd}  (type /help)")

        else:
            # Non-slash input: treat as a task in the current mode
            asyncio.run(_run_task(line, mode, registry, store))


# --------------------------------------------------------------------------- #
# Non-interactive CLI surface
# --------------------------------------------------------------------------- #

_SUBCOMMANDS = frozenset({"shell", "workers", "checkpoints", "resume"})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tasker",
        description="Ollama Tasker — provider-agnostic multi-agent orchestration",
    )
    parser.add_argument(
        "--mode", default="chat",
        choices=["chat", "code", "cowork", "research", "secure"],
        help="Operating mode (default: chat)",
    )
    parser.add_argument(
        "--policy", default=None,
        help="Routing policy override",
    )

    sub = parser.add_subparsers(dest="command")

    # tasker shell
    sub.add_parser("shell", help="Enter interactive REPL")

    # tasker workers
    sub.add_parser("workers", help="List registered workers")

    # tasker checkpoints
    sub.add_parser("checkpoints", help="List saved checkpoints")

    # tasker resume
    resume_p = sub.add_parser("resume", help="Resume from a checkpoint")
    resume_p.add_argument("checkpoint_id", nargs="?", default=None)
    resume_p.add_argument("--last", action="store_true", help="Resume most recent checkpoint")
    resume_p.add_argument(
        "--policy", dest="resume_policy", default=None,
        help="Policy override for resumed session",
    )

    return parser


def _cmd_workers(registry: WorkerRegistry) -> None:
    workers = registry.list_all()
    if not workers:
        print("No workers registered.")
        return
    print(f"{'ID':<30}  {'MODEL':<25}  {'LOCATION':<14}  STATUS")
    print("-" * 80)
    for w in workers:
        status = "available" if w.available else "unavailable"
        print(f"{w.id:<30}  {w.model_id:<25}  {w.compute_location.value:<14}  {status}")


def _cmd_checkpoints(store: CheckpointStore) -> None:
    checkpoints = store.list_all()
    if not checkpoints:
        print("No checkpoints found.")
        return
    print(f"{'ID':<38}  {'MODE':<10}  {'CREATED':<18}  TASK")
    print("-" * 90)
    for cp in checkpoints:
        ts = cp.created_at.strftime("%Y-%m-%d %H:%M")
        print(f"{cp.id:<38}  {cp.mode:<10}  {ts:<18}  {cp.original_task[:30]}")


def _cmd_resume(store: CheckpointStore, rest: list[str]) -> None:
    use_last = "--last" in rest
    checkpoint_id = next((r for r in rest if not r.startswith("-")), None)

    if use_last:
        cp = store.load_latest()
        if cp is None:
            print("No checkpoints found.")
            return
        checkpoint_id = cp.id

    if not checkpoint_id:
        print("Usage: tasker resume <checkpoint_id>  or  tasker resume --last")
        return

    cp = store.load(checkpoint_id)
    if cp is None:
        print(f"Checkpoint not found: {checkpoint_id}")
        return

    print(f"Resuming checkpoint {cp.id}  [{cp.mode}]  task={cp.original_task!r}")
    print("(Full session resume not yet wired — load the checkpoint and resubmit the task.)")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def _first_positional() -> str | None:
    """Return the first non-flag argument from sys.argv, skipping option values."""
    skip_next = False
    for tok in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if tok.startswith("--") and "=" not in tok:
            skip_next = True   # next token is the value for this option
            continue
        if tok.startswith("-"):
            continue
        return tok
    return None


def main() -> None:
    if _REGISTRY_YAML.exists():
        registry = WorkerRegistry.load_from_yaml(_REGISTRY_YAML)
    else:
        registry = WorkerRegistry()
    store = CheckpointStore(_DEFAULT_STORE_DIR)

    first = _first_positional()

    if first is None or first in _SUBCOMMANDS:
        # Standard subcommand path — subparsers parser works fine here.
        args, _ = _build_parser().parse_known_args()
        cmd = getattr(args, "command", None)

        if cmd is None or cmd == "shell":
            _repl(registry, store, initial_mode=args.mode, initial_policy=args.policy)
            return
        if cmd == "workers":
            _cmd_workers(registry)
            return
        if cmd == "checkpoints":
            _cmd_checkpoints(store)
            return
        if cmd == "resume":
            rest = []
            if getattr(args, "last", False):
                rest.append("--last")
            if getattr(args, "checkpoint_id", None):
                rest.append(args.checkpoint_id)
            _cmd_resume(store, rest)
            return
        _build_parser().print_help()
        return

    # Free-form task string — avoid subparsers clash by using a flags-only parser.
    _tp = argparse.ArgumentParser(add_help=False)
    _tp.add_argument("--mode", default="chat",
                     choices=["chat", "code", "cowork", "research", "secure"])
    _tp.add_argument("--policy", default=None)
    args, remaining = _tp.parse_known_args()
    task = " ".join(remaining).strip()
    if task:
        asyncio.run(_run_task(task, args.mode, registry, store))
    else:
        _build_parser().print_help()


if __name__ == "__main__":
    main()
