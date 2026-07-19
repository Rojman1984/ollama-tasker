"""
tasker.setup.wizard
---------------------
Headless setup wizard: WizardStepResult/StepStatus data model, run_wizard()
(the 7 steps per SDD_ADDENDUM_PHASE8.md B.3.2), and the `tasker-setup`
CLI entry point.

Phase 8.1 wizard + the Phase 8.2 `--check-model` readiness flow (which
delegates to tasker/setup/readiness.py); the TUI (tasker/tui/) is Phase 8.3+.

Step numbering note: B.3.2's own Step 7 is "Model selector + agentic
readiness" (Phase 8.2, deferred). This session's task explicitly redefines
Step 7 as the headless wizard's Summary step instead, so this module's
Step 7 differs from the addendum's B.3.2 text -- deliberate, not a
transcription error.

Import-cycle note: this module imports environment.py's check functions
lazily (inside each _stepN_* function body, not at module top level)
because environment.py imports WizardStepResult/StepStatus from *this*
module at its own top level. A top-level import here would create a
load-time cycle. Same pattern as tasker.modes.base <-> tasker.config.detect.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class StepStatus(Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class WizardStepResult:
    """Per SDD_ADDENDUM_PHASE8.md B.3.3."""
    step_id: str                       # e.g. "2.3"
    step_name: str                     # e.g. "Ollama service reachability"
    status: StepStatus                 # OK | WARNING | ERROR | SKIPPED
    message: str                       # human-readable result
    detail: str | None                 # extended detail (collapsible in TUI)
    action_required: str | None        # command to run if user action needed
    can_continue: bool                 # False blocks wizard from proceeding


# --------------------------------------------------------------------------- #
# Step 1 — Environment detection (1.1-1.4)
# --------------------------------------------------------------------------- #

def _step1_environment() -> list[WizardStepResult]:
    from tasker.setup.environment import check_python, check_venv, is_wsl2

    results = [check_python(), check_venv()]

    wsl2 = is_wsl2()
    results.append(WizardStepResult(
        step_id="1.3",
        step_name="WSL2 vs native Linux detection",
        status=StepStatus.OK,
        message="Running under WSL2." if wsl2 else "Running on native Linux (not WSL2).",
        detail=None,
        action_required=None,
        can_continue=True,
    ))

    try:
        from importlib.metadata import version
        pkg_version = version("ollama-tasker")
        results.append(WizardStepResult(
            step_id="1.4",
            step_name="Harness package install check",
            status=StepStatus.OK,
            message=f"ollama-tasker installed (version {pkg_version}).",
            detail=None,
            action_required=None,
            can_continue=True,
        ))
    except Exception as exc:
        results.append(WizardStepResult(
            step_id="1.4",
            step_name="Harness package install check",
            status=StepStatus.WARNING,
            message=f"Could not confirm ollama-tasker install: {exc}",
            detail=None,
            action_required="Run: pip install -e .",
            can_continue=True,
        ))

    return results


# --------------------------------------------------------------------------- #
# Step 2 — Ollama presence and service (2.1-2.3). 2.4 is a TUI concern
# (wait-and-reprompt) -- headless just reports and moves on.
# --------------------------------------------------------------------------- #

def _step2_ollama(base_url: str) -> list[WizardStepResult]:
    from tasker.setup.environment import (
        check_ollama_binary,
        check_ollama_service,
        check_ollama_version,
    )

    return [
        check_ollama_binary(),
        check_ollama_version(),
        check_ollama_service(base_url),
    ]


# --------------------------------------------------------------------------- #
# Step 3 — Hardware detection + vendor-specific GPU guidance
# --------------------------------------------------------------------------- #

def _step3_hardware() -> list[WizardStepResult]:
    from tasker.config.detect import detect_hardware_profile
    from tasker.config.gpu_backends import detect_gpu

    results: list[WizardStepResult] = []
    try:
        gpu = detect_gpu()
        profile = detect_hardware_profile()
    except Exception as exc:
        return [WizardStepResult(
            step_id="3.1",
            step_name="Hardware detection",
            status=StepStatus.ERROR,
            message=f"Hardware detection failed: {exc}",
            detail=None,
            action_required=None,
            can_continue=False,
        )]

    gpu_desc = (
        f"{gpu.vendor} ({gpu.name}, {gpu.memory_mb}MB{' unified' if gpu.is_unified_memory else ''})"
        if gpu else "none"
    )
    results.append(WizardStepResult(
        step_id="3.1",
        step_name="Hardware detection",
        status=StepStatus.OK,
        message=(
            f"Profile: {profile.name} | orchestrator_tier_max={profile.orchestrator_tier_max} "
            f"| GPU: {gpu_desc}"
        ),
        detail=None,
        action_required=None,
        can_continue=True,
    ))

    if gpu is None:
        results.append(WizardStepResult(
            step_id="3.3",
            step_name="GPU acceleration guidance",
            status=StepStatus.OK,
            message="No GPU detected -- CPU inference only.",
            detail=None,
            action_required=None,
            can_continue=True,
        ))
    elif gpu.vendor == "nvidia":
        results.append(WizardStepResult(
            step_id="3.3",
            step_name="GPU acceleration guidance",
            status=StepStatus.OK,
            message=(
                f"NVIDIA GPU detected via nvidia-smi (confirms WSL2 passthrough if "
                f"applicable): {gpu.name}, {gpu.memory_mb}MB."
            ),
            detail=None,
            action_required=None,
            can_continue=True,
        ))
    elif gpu.vendor == "amd_apu":
        import os
        vulkan_ok = os.environ.get("OLLAMA_VULKAN") == "1"
        rocm_ok = (
            os.environ.get("ROCR_VISIBLE_DEVICES") == "-1"
            and os.environ.get("HIP_VISIBLE_DEVICES") == "-1"
        )
        if vulkan_ok and rocm_ok:
            results.append(WizardStepResult(
                step_id="3.3",
                step_name="GPU acceleration guidance",
                status=StepStatus.OK,
                message=f"AMD APU detected ({gpu.name}); Vulkan env vars correctly set.",
                detail=None,
                action_required=None,
                can_continue=True,
            ))
        else:
            missing = []
            if not vulkan_ok:
                missing.append("OLLAMA_VULKAN")
            if not rocm_ok:
                missing.append("ROCR_VISIBLE_DEVICES/HIP_VISIBLE_DEVICES")
            results.append(WizardStepResult(
                step_id="3.3",
                step_name="GPU acceleration guidance",
                status=StepStatus.WARNING,
                message=(
                    f"AMD APU detected ({gpu.name}) but env vars not fully set: "
                    f"{', '.join(missing)} missing."
                ),
                detail=None,
                action_required=(
                    "export OLLAMA_VULKAN=1\n"
                    "export ROCR_VISIBLE_DEVICES=-1\n"
                    "export HIP_VISIBLE_DEVICES=-1"
                ),
                can_continue=True,
            ))

    return results


# --------------------------------------------------------------------------- #
# Step 4 — GPU acceleration verification (SKIPPED, not ERROR, if no GPU or
# no model loaded)
# --------------------------------------------------------------------------- #

def _step4_gpu_verify(base_url: str) -> list[WizardStepResult]:
    from tasker.config.gpu_backends import NvidiaBackend, detect_gpu

    gpu = detect_gpu()
    if gpu is None:
        return [WizardStepResult(
            step_id="4",
            step_name="GPU acceleration verification",
            status=StepStatus.SKIPPED,
            message="No GPU detected -- skipping acceleration verification.",
            detail=None,
            action_required=None,
            can_continue=True,
        )]

    if gpu.vendor == "amd_apu":
        return [WizardStepResult(
            step_id="4",
            step_name="GPU acceleration verification",
            status=StepStatus.SKIPPED,
            message="AmdApuBackend.verify_live() not yet implemented (Phase 7.5.4/7.5.5).",
            detail=None,
            action_required=None,
            can_continue=True,
        )]

    verify = NvidiaBackend().verify_live(base_url)

    if "No model currently loaded" in verify.message:
        return [WizardStepResult(
            step_id="4",
            step_name="GPU acceleration verification",
            status=StepStatus.SKIPPED,
            message="No model currently loaded in Ollama -- skipping GPU offload verification.",
            detail=None,
            action_required=(
                "Load a model (e.g. ollama run <model>) in another terminal, "
                "then re-run tasker-setup."
            ),
            can_continue=True,
        )]

    if verify.verified:
        return [WizardStepResult(
            step_id="4",
            step_name="GPU acceleration verification",
            status=StepStatus.OK,
            message=f"GPU OFFLOAD CONFIRMED: {verify.message}",
            detail=None,
            action_required=None,
            can_continue=True,
        )]

    return [WizardStepResult(
        step_id="4",
        step_name="GPU acceleration verification",
        status=StepStatus.WARNING,
        message=f"GPU OFFLOAD NOT CONFIRMED: {verify.message}",
        detail=None,
        action_required="Check Ollama's logs for GPU offload errors; confirm the model fits in VRAM.",
        can_continue=True,
    )]


# --------------------------------------------------------------------------- #
# Step 5 — Hardware profile cache (show existing, then detect + write)
# --------------------------------------------------------------------------- #

def _step5_cache() -> list[WizardStepResult]:
    # Reaches into detect.py's private cache-writing helpers deliberately --
    # duplicating the A.3.3 cache-schema logic here would be a second,
    # divergence-prone implementation of the same schema. Internal reuse
    # within the same package, not new external API surface.
    from tasker.config.detect import _CACHE_PATH, _build_cache_dict, _run_live_detection

    results: list[WizardStepResult] = []
    path = _CACHE_PATH

    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            results.append(WizardStepResult(
                step_id="5.1",
                step_name="Hardware profile cache (existing)",
                status=StepStatus.OK,
                message=(
                    f"Existing cache found at {path} "
                    f"(detected {existing.get('detected_at', 'unknown time')})."
                ),
                detail=json.dumps(existing, indent=2),
                action_required=None,
                can_continue=True,
            ))
        except (json.JSONDecodeError, OSError) as exc:
            results.append(WizardStepResult(
                step_id="5.1",
                step_name="Hardware profile cache (existing)",
                status=StepStatus.WARNING,
                message=f"Existing cache at {path} is unreadable: {exc}",
                detail=None,
                action_required=None,
                can_continue=True,
            ))
    else:
        results.append(WizardStepResult(
            step_id="5.1",
            step_name="Hardware profile cache (existing)",
            status=StepStatus.OK,
            message=f"No cache found at {path} -- will be written.",
            detail=None,
            action_required=None,
            can_continue=True,
        ))

    try:
        cpu_cores, ram_gb, gpu, profile_name, profile = _run_live_detection()
        cache = _build_cache_dict(cpu_cores, ram_gb, gpu, profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        results.append(WizardStepResult(
            step_id="5.2",
            step_name="Hardware profile cache (write)",
            status=StepStatus.OK,
            message=(
                f"Cache written to {path}, hostname={cache['hostname']!r}, "
                f"profile={profile_name}."
            ),
            detail=None,
            action_required=None,
            can_continue=True,
        ))
    except Exception as exc:
        results.append(WizardStepResult(
            step_id="5.2",
            step_name="Hardware profile cache (write)",
            status=StepStatus.ERROR,
            message=f"Failed to write hardware profile cache: {exc}",
            detail=None,
            action_required=None,
            can_continue=False,
        ))

    return results


# --------------------------------------------------------------------------- #
# Step 6 — Worker registry status
# --------------------------------------------------------------------------- #

def _step6_worker_registry() -> list[WizardStepResult]:
    from tasker.workers.base import ToolProtocol
    from tasker.workers.registry import WorkerRegistry

    results: list[WizardStepResult] = []
    registry_path = Path(__file__).parent.parent.parent / "config" / "workers" / "worker_registry.yaml"

    try:
        registry = WorkerRegistry.load_from_yaml(registry_path)
        workers = registry.list_all()
    except Exception as exc:
        return [WizardStepResult(
            step_id="6.1",
            step_name="Worker registry status",
            status=StepStatus.ERROR,
            message=f"Could not load worker registry from {registry_path}: {exc}",
            detail=None,
            action_required=None,
            can_continue=False,
        )]

    summary_lines = [
        f"{w.id} ({w.provider.value}/{w.model_id}, protocol={w.tool_protocol.value}, "
        f"available={w.available})"
        for w in workers
    ]
    results.append(WizardStepResult(
        step_id="6.1",
        step_name="Worker registry status",
        status=StepStatus.OK,
        message=f"{len(workers)} worker(s) registered.",
        detail="\n".join(summary_lines) or None,
        action_required=None,
        can_continue=True,
    ))

    gpu_workers = [w for w in workers if w.requires_gpu]
    if gpu_workers:
        results.append(WizardStepResult(
            step_id="6.2",
            step_name="GPU VRAM cross-check",
            status=StepStatus.OK,
            message=(
                f"{len(gpu_workers)} worker(s) declare requires_gpu=true. Full VRAM "
                "cross-check per SDD_ADDENDUM_7.5.md A.3.4 is Phase 7.5.6 (not yet "
                "implemented) -- availability is not yet auto-adjusted from detected VRAM."
            ),
            detail=", ".join(w.id for w in gpu_workers),
            action_required=None,
            can_continue=True,
        ))

    # 6.3: LFM2.5-family workers stuck on tool_protocol: native reject tools[]
    # -- see SDD_ADDENDUM_7.5.md A.2b.
    stale = [
        w for w in workers
        if w.tool_protocol == ToolProtocol.NATIVE and "lfm2.5" in w.model_id.lower()
    ]
    if stale:
        results.append(WizardStepResult(
            step_id="6.3",
            step_name="Stale tool_protocol check",
            status=StepStatus.WARNING,
            message=(
                f"{len(stale)} worker(s) registered as tool_protocol: native but appear "
                "to be LFM2.5 models -- Ollama rejects tools[] for this family "
                "(SDD_ADDENDUM_7.5.md A.2b)."
            ),
            detail=", ".join(w.id for w in stale),
            action_required=f"Update tool_protocol: lfm25 for: {', '.join(w.id for w in stale)}",
            can_continue=True,
        ))
    else:
        results.append(WizardStepResult(
            step_id="6.3",
            step_name="Stale tool_protocol check",
            status=StepStatus.OK,
            message="No LFM2.5 workers registered with tool_protocol: native.",
            detail=None,
            action_required=None,
            can_continue=True,
        ))

    # 6.4 (offer to launch model selector) is interactive/TUI-oriented --
    # headless just points at the future entry point, no prompting.
    return results


# --------------------------------------------------------------------------- #
# Step 7 — Summary (this session's headless-wizard redefinition of B.3.2's
# Step 7 -- see module docstring)
# --------------------------------------------------------------------------- #

def _step7_summary(results: list[WizardStepResult]) -> WizardStepResult:
    n_error = sum(1 for r in results if r.status == StepStatus.ERROR)
    n_warning = sum(1 for r in results if r.status == StepStatus.WARNING)
    actions = [r.action_required for r in results if r.action_required]

    if n_error:
        status = StepStatus.ERROR
        headline = f"{n_error} error(s), {n_warning} warning(s) found -- resolve errors before running tasks."
        next_action = "Resolve the errors above, then re-run: tasker-setup"
    elif n_warning:
        status = StepStatus.WARNING
        headline = f"{n_warning} warning(s) found -- harness will work, review recommended."
        next_action = "Run: tasker-setup --check-model <name> to test a model, then: tasker to launch the TUI."
    else:
        status = StepStatus.OK
        headline = "All checks passed."
        next_action = "Run: tasker-setup --check-model <name> to test a model, then: tasker to launch the TUI."

    return WizardStepResult(
        step_id="7",
        step_name="Summary",
        status=status,
        message=f"{headline} Next: {next_action}",
        detail="\n".join(f"- {a}" for a in actions) if actions else None,
        action_required=None,
        can_continue=(n_error == 0),
    )


# --------------------------------------------------------------------------- #
# run_wizard() — runs all 7 steps; never aborts early, always collects the
# full picture (per B.3.1's re-runnable/headless-capable design principles)
# --------------------------------------------------------------------------- #

def run_wizard(base_url: str = "http://localhost:11434", verbose: bool = False) -> list[WizardStepResult]:
    results: list[WizardStepResult] = []

    def _safe_extend(step_fn, *args) -> None:
        try:
            outcome = step_fn(*args)
            results.extend(outcome if isinstance(outcome, list) else [outcome])
        except Exception as exc:
            results.append(WizardStepResult(
                step_id="?",
                step_name=getattr(step_fn, "__name__", "unknown step"),
                status=StepStatus.ERROR,
                message=f"Unexpected error running this step: {exc}",
                detail=None,
                action_required=None,
                can_continue=False,
            ))

    _safe_extend(_step1_environment)
    _safe_extend(_step2_ollama, base_url)
    _safe_extend(_step3_hardware)
    _safe_extend(_step4_gpu_verify, base_url)
    _safe_extend(_step5_cache)
    _safe_extend(_step6_worker_registry)

    try:
        results.append(_step7_summary(results))
    except Exception as exc:
        results.append(WizardStepResult(
            step_id="7",
            step_name="Summary",
            status=StepStatus.ERROR,
            message=f"Could not generate summary: {exc}",
            detail=None,
            action_required=None,
            can_continue=False,
        ))

    return results


# --------------------------------------------------------------------------- #
# tasker-setup CLI entry point
# --------------------------------------------------------------------------- #

_ANSI_COLOR = {
    StepStatus.OK: "\033[32m",       # green
    StepStatus.WARNING: "\033[33m",  # yellow
    StepStatus.ERROR: "\033[31m",    # red
    StepStatus.SKIPPED: "\033[90m",  # grey
}
_ANSI_RESET = "\033[0m"


def _print_result(result: WizardStepResult, *, verbose: bool) -> None:
    color = _ANSI_COLOR.get(result.status, "")
    print(f"{color}[{result.status.value.upper():7}]{_ANSI_RESET} {result.step_id:>4}  {result.step_name}: {result.message}")
    if result.detail and verbose:
        for line in result.detail.splitlines():
            print(f"                {line}")
    if result.action_required:
        for line in result.action_required.splitlines():
            print(f"                -> {line}")


def _run_readiness_check(
    model_name: str,
    base_url: str,
    *,
    registry: str | None = None,
    assume_yes: bool = False,
) -> None:
    """
    Headless `tasker-setup --check-model <name>` flow (Phase 8.2, B.4):
    run the 3-round probe, print the readiness report, and -- only on a
    supported verdict and explicit confirmation -- write the suggested
    entry to the worker registry. Lazy import for the same cycle-avoidance
    reason as the step functions.
    """
    import asyncio

    from tasker.setup.readiness import (
        ReadinessChecker,
        format_report,
        write_manifest_to_registry,
    )

    kwargs: dict = {"base_url": base_url}
    if registry is not None:
        kwargs["registry_path"] = Path(registry)
    checker = ReadinessChecker(**kwargs)

    print(f"Probing {model_name} at {base_url} (up to 3 rounds; a slow model "
          "can take minutes per round)...")
    result = asyncio.run(checker.check(model_name))
    print()
    print(format_report(result))

    if not result.supported or result.suggested_manifest is None:
        return

    from tasker.setup.readiness import _DEFAULT_REGISTRY_PATH
    target = Path(registry) if registry is not None else _DEFAULT_REGISTRY_PATH
    print()
    if assume_yes:
        confirmed = True
    else:
        try:
            answer = input(f"Write this entry to {target}? [Y/n] ").strip().lower()
        except EOFError:
            answer = "n"
        confirmed = answer in ("", "y", "yes")

    if not confirmed:
        print("Not written.")
        return

    outcome = write_manifest_to_registry(result.suggested_manifest, target)
    print(f"Registry entry '{result.suggested_manifest.id}' {outcome} in {target}.")


def cli_main(argv: list[str] | None = None) -> None:
    """Entry point for the `tasker-setup` console script (B.2)."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="tasker-setup",
        description="Ollama Tasker headless setup wizard.",
    )
    parser.add_argument(
        "--check-model", metavar="NAME", default=None,
        help="Probe a model's tool-calling readiness (3 rounds: native, lfm25, json_extract).",
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434).",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="With --check-model: write the confirmed registry entry without prompting.",
    )
    parser.add_argument(
        "--registry", metavar="PATH", default=None,
        help="With --check-model: worker registry YAML to read/write "
             "(default: config/workers/worker_registry.yaml).",
    )
    parser.add_argument("--verbose", action="store_true", help="Show step detail output.")
    args = parser.parse_args(argv)

    if args.check_model:
        _run_readiness_check(
            args.check_model, args.ollama_url,
            registry=args.registry, assume_yes=args.yes,
        )
        return

    results = run_wizard(base_url=args.ollama_url, verbose=args.verbose)
    for result in results:
        _print_result(result, verbose=args.verbose)
