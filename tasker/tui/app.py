"""
tasker.tui.app
----------------
Rudimentary interactive REPL behind the `tasker` console script.

Deliberate scoped deviation from SDD_ADDENDUM_PHASE8.md B.5 (the
full-screen Textual TUI -- addendum Phase 8.3-8.5, still pending): this
is a stdlib-only prompt-loop REPL, shipped ahead of the Textual work so
`tasker` is immediately usable rather than a "coming soon" stub. Modeled
on Claude Code's own CLI UX -- a persistent prompt showing live context
(the active mode), slash commands, and budget/status visibility surfaced
through those commands plus live per-step output during execution (see
tasker/runtime/dispatch.py's _execute_steps). Same deviation pattern
already used for tasker/setup/wizard.py's Step 7 redefinition (see that
module's docstring): a documented, deliberate interim choice, not an
omission. B.5's Textual screens (WelcomeScreen, SetupWizardScreen,
ModelSelectorScreen, HarnessPanel) remain the eventual target.

Drives the exact same production pipeline as cli/shell.py via the shared
tasker/runtime/dispatch.py helper module -- no behavior fork between the
`tasker` and `tasker-cli` entry points.

Slash commands:
  /mode [chat|code|cowork|research|secure]   get/set active mode (shown
                                              in the prompt)
  /workers                                   list registered workers
  /budget                                    show session budget for the
                                              active mode
  /resume <checkpoint_id> | --last           resume a paused checkpoint
  /checkpoints                               list saved checkpoints
  /help                                      list commands
  /quit, /exit                               exit the REPL

Anything else typed at the prompt is dispatched as a task in the active
mode, through the real orchestrator -> provider pipeline.

Budget/session persistence model: each mode gets its own lazily-built
pipeline (config + budget + SessionManager + concurrency manager +
provider map + orchestrator), cached for the lifetime of the REPL
process and reused across turns in that mode -- so budget usage
genuinely accumulates turn over turn within a mode, unlike cli/shell.py's
CLI and tasker/api/server.py's API, both of which build a fresh
one-shot budget per call. This is a deliberate, scoped approximation:
Ollama Cloud budget is really a single per-account window (SDD 5.10),
not one-per-mode, so switching modes does not share usage in this REPL.
If a mode's cached pipeline pauses (budget exhausted), it is evicted so
the next task in that mode starts a fresh window rather than sitting in
SessionManager's HOLD state forever with no way to resume in-process.
"""
from __future__ import annotations

import asyncio
import os

from tasker.runtime.dispatch import (
    _DEFAULT_STORE_DIR,
    _build_pipeline,
    _load_registry,
    _print_checkpoints,
    _print_workers,
    _resume_task,
    _run_task,
)
from tasker.session.checkpoint import CheckpointStore
from tasker.session.manager import SessionState
from tasker.workers.registry import WorkerRegistry

_MODES = ("chat", "code", "cowork", "research", "secure")
_DEFAULT_MODE = "chat"

# /policy is not in this REPL's command set (see module docstring's
# command list) -- always None, i.e. each mode's own YAML routing policy
# governs. Kept as an explicit constant (not a magic None inline) so the
# reason is visible at both call sites that need it.
_NO_POLICY_OVERRIDE = None

_HELP_TEXT = (
    "  /mode [chat|code|cowork|research|secure]   get/set active mode (shown in prompt)\n"
    "  /workers                                   list registered workers\n"
    "  /budget                                     show session budget for the active mode\n"
    "  /resume <checkpoint_id> | --last            resume a paused checkpoint\n"
    "  /checkpoints                                list saved checkpoints\n"
    "  /help                                       this message\n"
    "  /quit, /exit                                exit\n"
    "\n"
    "  Anything else is sent as a task to the active mode."
)


def _format_timedelta(td) -> str:
    """Drop sub-second precision -- window_remaining's raw str() includes
    microseconds, which is just noise for a human-facing status line."""
    return str(td).split(".")[0]


def _print_budget(mode: str, pipeline) -> None:
    """
    pipeline: this mode's cached _build_pipeline() tuple if one has been
    built yet (i.e. at least one task has run in this mode this REPL
    session), else None -- see module docstring for the caching model.
    """
    if pipeline is None:
        from tasker.modes.base import ModeConfigurator

        profile_name = os.environ.get("TASKER_PROFILE", "tier1_tasker")
        try:
            profile = ModeConfigurator().load_profile(profile_name)
        except Exception as exc:
            print(f"Config error: {exc}")
            return
        print(
            f"mode={mode}  profile={profile_name}  plan={profile.ollama_plan.value}\n"
            f"No tasks run yet in this mode this session -- budget initializes on first task."
        )
        return

    _, _, budget, session_mgr, concurrency_mgr, _, _ = pipeline
    print(
        f"mode={mode}  plan={budget.plan.value}  state={session_mgr.state.value}\n"
        f"session:  {budget.usage_consumed:.1f} / {budget.session_limit:.0f} units "
        f"({budget.usage_pct:.1%}, resets in {_format_timedelta(budget.window_remaining)})\n"
        f"weekly:   {budget.weekly_usage_consumed:.1f} / {budget.weekly_limit:.0f} units "
        f"({budget.weekly_usage_pct:.1%})\n"
        f"cloud concurrency: {concurrency_mgr.slots_available} slot(s) free"
    )


async def _dispatch(
    mode: str,
    task: str,
    registry: WorkerRegistry,
    store: CheckpointStore,
    pipelines: dict,
) -> None:
    """Get-or-build this mode's cached pipeline, run the task through it,
    and evict the cache entry if the run left the session PAUSED."""
    pipeline = pipelines.get(mode)
    if pipeline is None:
        pipeline = _build_pipeline(mode, store, _NO_POLICY_OVERRIDE)
        if pipeline is None:
            return
        pipelines[mode] = pipeline

    await _run_task(task, mode, registry, store, _NO_POLICY_OVERRIDE, pipeline=pipeline)

    session_mgr = pipeline[3]
    if session_mgr.state == SessionState.PAUSED:
        # tick() on a PAUSED SessionManager returns HOLD forever -- without
        # eviction, every future task in this mode would silently do
        # nothing until the process restarts. Evicting means the next task
        # starts a fresh 5-hour window instead (not a real resume; use
        # /resume for that -- see the docstring's caching-model note).
        del pipelines[mode]


def _repl(
    registry: WorkerRegistry,
    store: CheckpointStore,
    initial_mode: str = _DEFAULT_MODE,
) -> None:
    mode = initial_mode
    pipelines: dict = {}

    worker_count = len(registry.list_all())
    print(
        f"Ollama Tasker — interactive REPL\n"
        f"workers: {worker_count} registered  |  mode: {mode}\n"
        f"Type /help for commands, /quit to exit.\n"
    )

    while True:
        try:
            line = input(f"tasker ({mode})> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not line:
            continue

        if line.startswith("/"):
            parts = line.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd in ("/quit", "/exit"):
                break

            elif cmd == "/mode":
                if arg:
                    new_mode = arg.lower()
                    if new_mode not in _MODES:
                        print(f"Unknown mode: {new_mode!r}. Valid: {', '.join(_MODES)}")
                    else:
                        mode = new_mode
                        print(f"Mode set to: {mode}")
                else:
                    print(f"Current mode: {mode}")

            elif cmd == "/workers":
                _print_workers(registry)

            elif cmd == "/budget":
                _print_budget(mode, pipelines.get(mode))

            elif cmd == "/checkpoints":
                _print_checkpoints(store)

            elif cmd == "/resume":
                if not arg:
                    print("Usage: /resume <checkpoint_id>  or  /resume --last")
                elif arg == "--last":
                    cp = store.load_latest()
                    if cp is None:
                        print("No checkpoints found.")
                    else:
                        asyncio.run(_resume_task(cp.id, registry, store, _NO_POLICY_OVERRIDE))
                else:
                    asyncio.run(_resume_task(arg, registry, store, _NO_POLICY_OVERRIDE))

            elif cmd == "/help":
                print(_HELP_TEXT)

            else:
                print(f"Unknown command: {cmd}  (type /help)")

        else:
            # Non-slash input: dispatch as a task in the active mode.
            asyncio.run(_dispatch(mode, line, registry, store, pipelines))


def main() -> None:
    """Entry point for the `tasker` console script."""
    import logging

    logging.basicConfig(
        level=os.environ.get("TASKER_LOG_LEVEL", "WARNING").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    registry = _load_registry()
    store = CheckpointStore(_DEFAULT_STORE_DIR)
    _repl(registry, store)


if __name__ == "__main__":
    main()
