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
  /mode /workers /policy /secure /budget /checkpoint /resume /model
  /models /effort /context /status /help

See SDD Section 7.6.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from tasker.runtime.dispatch import (
    _DEFAULT_STORE_DIR,
    _REGISTRY_YAML,
    _POLICY_ALIASES,
    _build_pipeline,
    _build_session,
    _deserialize_step_result,
    _execute_steps,
    _load_registry,
    _print_checkpoints,
    _print_workers,
    _resolve_policy_override,
    _resume_task,
    _run_chat_task,
    _run_task,
    _serialize_step_result,
    DEFAULT_CHAT_WORKER_ID,
    _EFFORT_LEVELS,
    _DEFAULT_EFFORT,
)
from tasker.session.checkpoint import CheckpointStore
from tasker.setup.onboarding import looks_like_model_tag, onboard_model
from tasker.workers.registry import WorkerRegistry

_KNOWN_COMMANDS = (
    "/mode", "/workers", "/policy", "/secure", "/budget",
    "/checkpoint", "/resume", "/model", "/models", "/effort",
    "/context", "/status", "/help", "/quit", "/exit",
)
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


def _format_hms(td) -> str:
    total = int(td.total_seconds())
    h, rem = divmod(max(0, total), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _print_budget(mode: str, pipeline) -> None:
    """/budget (SDD 5.6.1a): the REPL session builds one pipeline per mode
    up front (see _ensure_pipeline in _repl()), so budget tracking starts
    at 0.0 the moment a mode is entered, not "not active" until a task
    happens to run."""
    if pipeline is None:
        print("(budget unavailable -- pipeline failed to build for this mode, see earlier Config error)")
        return
    _, config, budget, _, _, _, _ = pipeline
    print(
        f"mode={mode}  budget={budget.usage_consumed:.1f}/{budget.session_limit:.0f} units "
        f"({budget.usage_pct:.1%})  plan={budget.plan.value}  "
        f"window_remaining={_format_hms(budget.window_remaining)}"
    )


def _print_models(registry: WorkerRegistry) -> None:
    """/models (alias `/model list`) -- SDD 5.6.1a: DEFAULT/LOCAL/CLOUD
    groups with tool protocol, max context, and a "fits in VRAM" hint for
    local workers whose declared context_window exceeds what the cached
    GPU detection estimates will actually fit."""
    from tasker.config.detect import load_cached_gpu_info
    from tasker.workers.base import ComputeLocation
    from tasker.workers.providers.ollama import resolve_num_ctx

    workers = registry.list_all()
    if not workers:
        print("(no workers registered)")
        return

    gpu = load_cached_gpu_info()
    groups: dict[str, list] = {"DEFAULT": [], "LOCAL": [], "CLOUD": []}
    for w in workers:
        if w.id == DEFAULT_CHAT_WORKER_ID:
            groups["DEFAULT"].append(w)
        elif w.compute_location == ComputeLocation.LOCAL_HARDWARE:
            groups["LOCAL"].append(w)
        else:
            groups["CLOUD"].append(w)

    for label in ("DEFAULT", "LOCAL", "CLOUD"):
        members = groups[label]
        if not members:
            continue
        print(f"{label}:")
        for w in members:
            num_ctx, capped = resolve_num_ctx(w, gpu)
            hint = f"  (fits ~{num_ctx} of {w.context_window} in VRAM)" if capped else ""
            status = "available" if w.available else "unavailable"
            print(
                f"  {w.id:30s}  {w.tool_protocol.value:12s}  "
                f"max_context={w.context_window:<8d}  {status}{hint}"
            )


def _pull_progress_printer():
    """De-duplicated progress printer for /api/pull's NDJSON stream --
    prints each distinct status line once rather than flooding the
    terminal with a line per byte-progress tick."""
    last_status = None

    def _cb(evt: dict) -> None:
        nonlocal last_status
        status = evt.get("status")
        if status and status != last_status:
            print(f"  [pull] {status}")
            last_status = status

    return _cb


_MODE_NAMES = frozenset({"chat", "code", "cowork", "research", "secure"})


def _onboard_and_pin(registry: WorkerRegistry, model_tag: str) -> str | None:
    """
    /model <tag> dynamic onboarding (SDD_ADDENDUM_PHASE8.md B.5.5): an
    unregistered id that looks like a genuine Ollama model tag gets
    offered for download + registration rather than a flat "unknown
    worker id" rejection. Confirms with the user first (never pulls
    without an explicit yes), pulls via HTTP /api/pull (never the
    `ollama` CLI -- CLAUDE.md's binding server rules), probes it for
    tool-calling readiness, and registers it on success. Returns the new
    worker id to pin CHAT to, or None if declined/failed (message
    already printed either way).
    """
    base_url = os.environ.get("OLLAMA_BASE_URL", _DEFAULT_OLLAMA_BASE_URL)
    print(
        f"Worker '{model_tag}' is not registered, but looks like an Ollama "
        f"model tag. This will pull it via {base_url} (HTTP /api/pull, "
        f"never the `ollama` CLI) if not already downloaded, then probe it "
        f"for tool-calling support."
    )
    try:
        confirmed = input(f"Download and onboard '{model_tag}'? [y/N] ").strip().lower() == "y"
    except (KeyboardInterrupt, EOFError):
        print()
        confirmed = False
    if not confirmed:
        print("Cancelled.")
        return None

    manifest, message = asyncio.run(
        onboard_model(model_tag, registry, base_url, progress_cb=_pull_progress_printer())
    )
    print(message)
    return manifest.id if manifest is not None else None


def _suggest_command(cmd: str) -> str | None:
    """
    Nearest-command suggestion for an unrecognized slash command.

    A user typing e.g. "/chat" almost always means "switch to chat mode"
    (a natural guess given the mode names), not a typo of some other
    slash command -- so that case is special-cased ahead of the generic
    fuzzy match, which instead catches real typos like "/wrkers".
    """
    name = cmd[1:]
    if name in _MODE_NAMES:
        return f"/mode {name}"
    import difflib

    matches = difflib.get_close_matches(cmd, _KNOWN_COMMANDS, n=1, cutoff=0.6)
    return matches[0] if matches else None

# --------------------------------------------------------------------------- #
# Singletons shared between CLI surface and REPL
# --------------------------------------------------------------------------- #
#
# The pipeline-building and task-dispatch logic (_build_session,
# _build_pipeline, _execute_steps, _run_task, _resume_task, and friends)
# lives in tasker/runtime/dispatch.py, shared verbatim with
# tasker/tui/app.py's REPL -- both entry points drive the identical
# production path. Re-imported here unchanged (same names, including the
# leading underscore) so this module's own namespace and existing tests
# (tests/unit/test_cli_session_wiring.py imports these from cli.shell) are
# unaffected by the move.


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
    # Only apply the REPL policy as an override when the user actually chose
    # one (CLI flag or /policy) — otherwise each mode's YAML policy governs.
    policy_explicit = initial_policy is not None
    secure = False

    # CHAT mode direct-dispatch state (SDD 5.3a): chat_model/chat_effort/
    # chat_context_override are session-scoped REPL levers (/model,
    # /effort, /context), never persisted. chat_history accumulates real
    # multi-turn conversation context across turns in this REPL session --
    # passed to every chat dispatch call.
    chat_model: str | None = None
    chat_effort: str = _DEFAULT_EFFORT
    chat_context_override: int | None = None
    chat_history: list[dict] = []

    # One pipeline per mode, built up front rather than lazily on first
    # task (SDD 5.6.1a) -- so /budget reflects a real, zero-initialized
    # budget object from the moment a mode is entered, not a static
    # "not active" placeholder. A pipeline is cached across turns within
    # this REPL session so budget usage genuinely accumulates; switching
    # /policy after a mode's pipeline is already built does not
    # retroactively rebuild it (documented limitation, same simplification
    # the prior TUI REPL used).
    pipelines: dict[str, tuple] = {}

    def _ensure_pipeline(m: str):
        if m not in pipelines:
            built = _build_pipeline(
                m, store, _resolve_policy_override(policy) if policy_explicit else None,
            )
            if built is not None:
                pipelines[m] = built
        return pipelines.get(m)

    def _evict_if_paused(m: str) -> None:
        """A paused pipeline is evicted from the cache so the next task in
        this mode starts fresh (a fresh budget window, SDD 9.4) rather than
        sitting in PAUSED forever within this REPL process."""
        from tasker.session.manager import SessionState

        cached = pipelines.get(m)
        if cached is not None and cached[3].state == SessionState.PAUSED:
            del pipelines[m]

    _ensure_pipeline(mode)

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
                    _ensure_pipeline(mode)
                    print(f"Mode set to: {mode}")
                else:
                    print(f"Current mode: {mode}")

            elif cmd == "/policy":
                if arg:
                    policy = _POLICY_ALIASES.get(arg.lower(), arg.lower())
                    policy_explicit = True
                    print(f"Policy set to: {policy}")
                else:
                    print(f"Current policy: {policy}")

            elif cmd == "/secure":
                toggle = arg.lower() if arg else ("off" if secure else "on")
                secure = toggle != "off"
                if secure:
                    mode   = "secure"
                    policy = "private"
                    _ensure_pipeline(mode)
                print(f"Secure mode: {'ON — LOCAL_ONLY enforced' if secure else 'OFF'}")

            elif cmd == "/workers":
                workers = registry.list_all()
                if not workers:
                    print("(no workers registered)")
                for w in workers:
                    status = "available" if w.available else "unavailable"
                    print(f"  {w.id:30s}  {w.model_id:25s}  {w.compute_location.value:12s}  {status}")

            elif cmd == "/budget":
                _print_budget(mode, pipelines.get(mode))

            elif cmd == "/checkpoint":
                checkpoints = store.list_all()
                if not checkpoints:
                    print("(no checkpoints)")
                for cp in checkpoints:
                    print(f"  {cp.id}  [{cp.mode}]  {cp.created_at.strftime('%Y-%m-%d %H:%M')}  {cp.original_task[:40]}")

            elif cmd == "/resume":
                if not arg:
                    print("Usage: /resume <checkpoint_id>  or  /resume --last")
                else:
                    rest = ["--last"] if arg == "--last" else [arg]
                    _cmd_resume(registry, store, rest,
                                policy if policy_explicit else None)

            elif cmd == "/model":
                if arg == "list":
                    _print_models(registry)
                elif arg:
                    worker = registry.get(arg)
                    if worker is not None:
                        chat_model = arg
                        print(f"CHAT model pinned to: {chat_model}")
                    elif looks_like_model_tag(arg):
                        onboarded = _onboard_and_pin(registry, arg)
                        if onboarded:
                            chat_model = onboarded
                    else:
                        print(f"Unknown worker id: {arg!r}  (see /workers)")
                elif chat_model:
                    print(f"Current CHAT model: {chat_model} (explicit)")
                else:
                    print(
                        f"Current CHAT model: {DEFAULT_CHAT_WORKER_ID} "
                        f"(default, effort={chat_effort})"
                    )

            elif cmd == "/models":
                _print_models(registry)

            elif cmd == "/effort":
                if arg:
                    level = arg.lower()
                    if level not in _EFFORT_LEVELS:
                        print(f"Usage: /effort <{'|'.join(_EFFORT_LEVELS)}>")
                    else:
                        chat_effort = level
                        print(f"CHAT effort set to: {chat_effort}")
                else:
                    print(f"Current CHAT effort: {chat_effort}")

            elif cmd == "/context":
                if arg:
                    try:
                        tokens = int(arg)
                        if tokens <= 0:
                            raise ValueError
                    except ValueError:
                        print("Usage: /context <positive integer tokens>")
                    else:
                        chat_context_override = tokens
                        print(f"CHAT context override set to: {chat_context_override} tokens")
                elif chat_context_override:
                    print(f"Current CHAT context override: {chat_context_override} tokens")
                else:
                    print(
                        "No CHAT context override set -- using each worker's "
                        "manifest context_window (capped by VRAM for local "
                        "workers, see /models)"
                    )

            elif cmd == "/status":
                chat_model_desc = chat_model or f"{DEFAULT_CHAT_WORKER_ID} (default)"
                context_desc = f"{chat_context_override} tokens" if chat_context_override else "auto"
                print(
                    f"mode={mode}  policy={policy}  secure={secure}  "
                    f"chat_model={chat_model_desc}  chat_effort={chat_effort}  "
                    f"chat_context={context_desc}"
                )

            elif cmd == "/help":
                print(
                    "  /mode <mode>        switch mode (chat|code|cowork|research|secure)\n"
                    "  /workers            list registered workers\n"
                    "  /models             list workers by DEFAULT/LOCAL/CLOUD (alias: /model list)\n"
                    "  /policy <policy>    change routing policy\n"
                    "  /secure [on|off]    toggle SECURE mode\n"
                    "  /budget             show session budget (initializes at 0.0)\n"
                    "  /checkpoint         list checkpoints\n"
                    "  /resume <id|--last> resume from checkpoint\n"
                    "  /model <worker_id>  pin CHAT mode to an exact worker\n"
                    "                      (an unregistered but valid-looking\n"
                    "                      Ollama tag offers to pull + onboard it)\n"
                    "  /effort <low|med|high>  redirect CHAT mode's default worker\n"
                    "  /context <tokens>   override CHAT mode's num_ctx for this session\n"
                    "  /status             show current session state\n"
                    "  /help               this message\n"
                    "  /quit               exit"
                )

            else:
                suggestion = _suggest_command(cmd)
                if suggestion:
                    print(f"Unknown command: {cmd}  (did you mean: {suggestion}?)")
                else:
                    print(f"Unknown command: {cmd}  (type /help)")

        elif mode == "chat":
            # CHAT mode bypasses plan()/synthesize() entirely (SDD 5.3a) --
            # a direct call to the chat worker with the raw message and
            # this REPL session's running conversation history. Reuses
            # this mode's cached pipeline (see _ensure_pipeline) so budget
            # usage genuinely accumulates across turns.
            asyncio.run(_run_chat_task(
                line, registry, store, chat_history,
                _resolve_policy_override(policy) if policy_explicit else None,
                pipeline=_ensure_pipeline(mode),
                model_override=chat_model, effort=chat_effort,
                context_override=chat_context_override,
            ))
            # No _evict_if_paused() here -- CHAT's direct-dispatch path
            # never calls SessionManager.tick()/pause (SDD 5.3a), so its
            # cached pipeline's session_mgr can never reach PAUSED.

        else:
            # Non-slash input in every other mode: treat as a task, full
            # orchestrator plan -> execute-steps -> synthesize pipeline.
            asyncio.run(_run_task(
                line, mode, registry, store,
                _resolve_policy_override(policy) if policy_explicit else None,
                pipeline=_ensure_pipeline(mode),
            ))
            _evict_if_paused(mode)


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
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show INFO/WARNING plumbing logs (provider calls, slot/budget "
             "accounting) instead of keeping the chat flow quiet",
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


_cmd_workers = _print_workers
_cmd_checkpoints = _print_checkpoints


def _cmd_resume(
    registry: WorkerRegistry,
    store: CheckpointStore,
    rest: list[str],
    policy_str: str | None = None,
) -> None:
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

    asyncio.run(
        _resume_task(checkpoint_id, registry, store, _resolve_policy_override(policy_str))
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

# Boolean flags take no value -- must be excluded from the "next token is
# this option's value" skip logic below, or the token right after one of
# these (which may be the actual task string or subcommand) gets silently
# swallowed as if it were the flag's argument.
_BOOL_FLAGS = frozenset({"--verbose", "--last"})


def _first_positional() -> str | None:
    """Return the first non-flag argument from sys.argv, skipping option values."""
    skip_next = False
    for tok in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if tok.startswith("--") and "=" not in tok and tok not in _BOOL_FLAGS:
            skip_next = True   # next token is the value for this option
            continue
        if tok.startswith("-"):
            continue
        return tok
    return None


def main() -> None:
    import logging

    # Default the interactive shell to quiet: WARNING+ plumbing logs
    # (provider/registry/concurrency internals) were showing up interleaved
    # with the chat flow by default. --verbose restores the old WARNING
    # default; TASKER_LOG_LEVEL (when set) always wins over both, so
    # existing debugging workflows that export it explicitly are unaffected.
    verbose = "--verbose" in sys.argv[1:]
    default_level = "WARNING" if verbose else "ERROR"
    logging.basicConfig(
        level=os.environ.get("TASKER_LOG_LEVEL", default_level).upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    registry = _load_registry()
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
            _cmd_resume(registry, store, rest, getattr(args, "resume_policy", None))
            return
        _build_parser().print_help()
        return

    # Free-form task string — avoid subparsers clash by using a flags-only parser.
    _tp = argparse.ArgumentParser(add_help=False)
    _tp.add_argument("--mode", default="chat",
                     choices=["chat", "code", "cowork", "research", "secure"])
    _tp.add_argument("--policy", default=None)
    _tp.add_argument("--verbose", action="store_true")
    args, remaining = _tp.parse_known_args()
    task = " ".join(remaining).strip()
    if task:
        if args.mode == "chat":
            # One-shot CLI invocation: fresh (empty) history each call --
            # multi-turn context only accumulates within a REPL session.
            asyncio.run(
                _run_chat_task(task, registry, store, [],
                                _resolve_policy_override(args.policy))
            )
        else:
            asyncio.run(
                _run_task(task, args.mode, registry, store,
                          _resolve_policy_override(args.policy))
            )
    else:
        _build_parser().print_help()


if __name__ == "__main__":
    main()
