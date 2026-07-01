"""
tasker.setup.environment
--------------------------
Environment and Ollama-presence checks for the setup wizard. Pure,
side-effect-free (aside from the subprocess/network calls each check makes)
functions returning WizardStepResult -- no wizard-orchestration logic here,
that lives in tasker.setup.wizard.

See docs/SDD_ADDENDUM_PHASE8.md B.3.2 (steps 1-2) and B.6 (WSL2 detection).

Note on the environment/wizard import cycle: WizardStepResult/StepStatus
live in wizard.py per B.3.3, but wizard.py also needs to call the check
functions in this module. This module imports WizardStepResult/StepStatus
at the top level; wizard.py must import this module's functions lazily
(inside function bodies, not at its own top level) to avoid a load-time
cycle -- same pattern already used for tasker.modes.base <-> tasker.config.detect.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from tasker.setup.wizard import StepStatus, WizardStepResult


def is_wsl2() -> bool:
    """Per B.6: /proc/version contains "microsoft" or "wsl" (case-insensitive)."""
    try:
        version = Path("/proc/version").read_text().lower()
        return "microsoft" in version or "wsl" in version
    except (FileNotFoundError, PermissionError):
        return False


def check_python() -> WizardStepResult:
    ok = sys.version_info >= (3, 11)
    version_str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return WizardStepResult(
        step_id="1.1",
        step_name="Python version check",
        status=StepStatus.OK if ok else StepStatus.ERROR,
        message=f"Python {version_str} ({'>= 3.11, OK' if ok else '< 3.11, unsupported'})",
        detail=None,
        action_required=None if ok else "Install Python 3.11 or newer.",
        can_continue=ok,
    )


def check_venv() -> WizardStepResult:
    """Warn but do not block -- advanced users may run without a venv."""
    in_venv = sys.prefix != sys.base_prefix
    return WizardStepResult(
        step_id="1.2",
        step_name="Virtual environment detection",
        status=StepStatus.OK if in_venv else StepStatus.WARNING,
        message=(
            f"Running inside a virtual environment ({sys.prefix})."
            if in_venv else
            "Not running inside a virtual environment."
        ),
        detail=None,
        action_required=(
            None if in_venv else
            "Consider using a venv: python -m venv .venv && source .venv/bin/activate"
        ),
        can_continue=True,
    )


def check_ollama_binary() -> WizardStepResult:
    path = shutil.which("ollama")
    if path:
        return WizardStepResult(
            step_id="2.1",
            step_name="Ollama binary detection",
            status=StepStatus.OK,
            message=f"Found ollama at {path}",
            detail=None,
            action_required=None,
            can_continue=True,
        )
    return WizardStepResult(
        step_id="2.1",
        step_name="Ollama binary detection",
        status=StepStatus.ERROR,
        message="ollama binary not found on PATH",
        detail=None,
        action_required="Install Ollama: curl -fsSL https://ollama.com/install.sh | sh",
        can_continue=False,
    )


def check_ollama_version() -> WizardStepResult:
    """Any version found -> OK. Subprocess failure -> WARNING (non-blocking)."""
    try:
        result = subprocess.run(
            ["ollama", "--version"], capture_output=True, text=True, timeout=5,
        )
        version_str = (result.stdout or result.stderr).strip()
        if result.returncode != 0 or not version_str:
            return WizardStepResult(
                step_id="2.2",
                step_name="Ollama version check",
                status=StepStatus.WARNING,
                message="ollama --version did not report a usable version string",
                detail=(result.stderr or result.stdout or "").strip() or None,
                action_required=None,
                can_continue=True,
            )
        return WizardStepResult(
            step_id="2.2",
            step_name="Ollama version check",
            status=StepStatus.OK,
            message=f"Ollama version: {version_str}",
            detail=None,
            action_required=None,
            can_continue=True,
        )
    except Exception as exc:
        return WizardStepResult(
            step_id="2.2",
            step_name="Ollama version check",
            status=StepStatus.WARNING,
            message=f"Could not run 'ollama --version': {exc}",
            detail=None,
            action_required=None,
            can_continue=True,
        )


def check_ollama_service(base_url: str = "http://localhost:11434") -> WizardStepResult:
    """
    GET {base_url}/api/tags, 3s timeout. ERROR (blocking) if unreachable --
    action_required message depends on environment (B.6): WSL2 and
    no-systemd native Linux both say "run ollama serve"; systemd-based
    native Linux says "sudo systemctl start ollama". Never auto-starts
    Ollama -- that's the user's decision (B.3.1 non-destructive principle).
    """
    import json as _json
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = _json.loads(resp.read())
        models = data.get("models") or []
        return WizardStepResult(
            step_id="2.3",
            step_name="Ollama service reachability",
            status=StepStatus.OK,
            message=f"Ollama service reachable at {base_url} ({len(models)} model(s) available)",
            detail=None,
            action_required=None,
            can_continue=True,
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        if is_wsl2():
            action = "Run in a separate terminal: ollama serve"
        elif shutil.which("systemctl") is not None:
            action = "Run: sudo systemctl start ollama"
        else:
            action = "Run in a separate terminal: ollama serve"
        return WizardStepResult(
            step_id="2.3",
            step_name="Ollama service reachability",
            status=StepStatus.ERROR,
            message=f"Ollama service not reachable at {base_url} ({exc})",
            detail=None,
            action_required=action,
            can_continue=False,
        )
