"""
tasker.tui.widgets.status_bar
-------------------------------
HardwareStatusBar -- persistent status widget shown on every screen.
See SDD_ADDENDUM_PHASE8.md B.5.4:

    [CPU: 4c/32GB] [GPU: NVIDIA GTX 1050 Ti / 4GB] [Tier: 2 / resident]
    [Model: lfm2.5-thinking:latest / lfm25] [Session: READY]

Phase 8.3 scope: hardware/tier/profile fields are populated from the
cached hardware detection (never a live detect_gpu()/psutil call --
same A.3.1 caching convention every other CLI/TUI entry point follows).
`active_model`/`session_state` are reactive placeholders wired to real
values only once ModelSelectorScreen (8.4) and HarnessPanel (8.5) exist
to set them.
"""
from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static

_NOT_DETECTED = "hardware: not detected -- run: tasker-hardware detect"


class HardwareStatusBar(Static):
    """One-line persistent status bar, updated via refresh_hardware()."""

    DEFAULT_CSS = """
    HardwareStatusBar {
        dock: top;
        height: 1;
        width: 100%;
        background: $primary-darken-2;
        color: $text;
        content-align: left middle;
        padding: 0 1;
    }
    """

    hardware_summary: reactive[str] = reactive(_NOT_DETECTED)
    active_model: reactive[str] = reactive("none")
    session_state: reactive[str] = reactive("READY")

    def render(self) -> str:
        return f"{self.hardware_summary}  [Model: {self.active_model}]  [Session: {self.session_state}]"

    def on_mount(self) -> None:
        self.refresh_hardware()

    def refresh_hardware(self) -> None:
        """
        Re-derive hardware_summary from the machine-local cache. Reaches
        into tasker.config.detect's private _read_matching_cache /
        _CACHE_PATH -- same internal-reuse pattern already used by
        tasker/setup/wizard.py's Step 5 (see that module's comment) rather
        than a second, divergence-prone implementation of the cache
        schema. The raw cache already carries a computed_profile block
        (tier/load-strategy computed once at `tasker-hardware detect`
        time per SDD_ADDENDUM_7.5.md A.3.3) -- read that directly rather
        than re-deriving a profile via load_cached_detection(), which
        would be a second, potentially-divergent resolution of the same
        answer.
        """
        from tasker.config.detect import _CACHE_PATH, _read_matching_cache, load_cached_gpu_info

        raw = _read_matching_cache(_CACHE_PATH)
        if raw is None:
            self.hardware_summary = _NOT_DETECTED
            return

        gpu = load_cached_gpu_info()

        cpu = raw.get("cpu_cores", "?")
        ram_raw = raw.get("ram_gb")
        ram = f"{ram_raw:.0f}" if isinstance(ram_raw, (int, float)) else "?"
        gpu_desc = f"{gpu.vendor} {gpu.name} / {gpu.memory_mb}MB" if gpu else "none"

        computed = raw.get("computed_profile") or {}
        tier = computed.get("orchestrator_tier_max", "?")
        load_style = computed.get("load_strategy", "?")

        self.hardware_summary = (
            f"[CPU: {cpu}c/{ram}GB] [GPU: {gpu_desc}] [Tier: {tier} / {load_style}]"
        )
