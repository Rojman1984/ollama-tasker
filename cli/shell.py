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
import sys
from pathlib import Path

from tasker.session.checkpoint import CheckpointStore
from tasker.workers.base import RoutingPolicy
from tasker.workers.registry import WorkerRegistry

# --------------------------------------------------------------------------- #
# Singletons shared between CLI surface and REPL
# --------------------------------------------------------------------------- #

_DEFAULT_STORE_DIR = Path(".tasker") / "checkpoints"

_POLICY_ALIASES: dict[str, str] = {
    "local":      "private",
    "cost":       "cost_optimized",
    "capability": "capability_first",
    "speed":      "speed_optimized",
    "hybrid":     "hybrid",
    "private":    "private",
}


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
            print(f"[{mode}] Task execution requires an active worker session (Phase 6).")
            print(f"  Task: {line!r}")


# --------------------------------------------------------------------------- #
# Non-interactive CLI surface
# --------------------------------------------------------------------------- #

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


def _cmd_resume(store: CheckpointStore, checkpoint_id: str | None, use_last: bool) -> None:
    if use_last:
        cp = store.load_latest()
        if cp is None:
            print("No checkpoints found.")
            return
        checkpoint_id = cp.id

    if not checkpoint_id:
        print("Provide a checkpoint ID or use --last.")
        return

    cp = store.load(checkpoint_id)
    if cp is None:
        print(f"Checkpoint not found: {checkpoint_id}")
        return

    print(f"Resuming checkpoint {cp.id}  [{cp.mode}]  task={cp.original_task!r}")
    print("(Full resume requires an active worker session — Phase 6.)")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = _build_parser()

    # If called with no args, or only --mode/--policy but no subcommand and
    # no task string, drop into the REPL.
    args, remaining = parser.parse_known_args()

    registry = WorkerRegistry()
    store    = CheckpointStore(_DEFAULT_STORE_DIR)

    if args.command == "shell" or (args.command is None and not remaining):
        _repl(registry, store, initial_mode=args.mode, initial_policy=args.policy)
        return

    if args.command == "workers":
        _cmd_workers(registry)
        return

    if args.command == "checkpoints":
        _cmd_checkpoints(store)
        return

    if args.command == "resume":
        _cmd_resume(store, args.checkpoint_id, args.last)
        return

    # Positional task string: tasker --mode code "do something"
    task = " ".join(remaining).strip()
    if task:
        policy = args.policy or "default"
        print(f"[{args.mode}] policy={policy}  task={task!r}")
        print("(Task execution requires an active worker session — Phase 6.)")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
