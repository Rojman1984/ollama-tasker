"""
tasker.setup.readiness
----------------------
Agentic Readiness Checker (Phase 8.2 -- SDD_ADDENDUM_PHASE8.md B.4).

Answers one question empirically: "Can this specific Ollama model handle
tool-calling as a harness worker?" -- by probing it live with a structured
3-round protocol (NATIVE -> LFM25 -> JSON_EXTRACT), never by trusting
Ollama's capability flags (wrong for the LFM2.5 family, A.2b).

Headless, no UI dependency: the TUI (Phase 8.4) and the `tasker-setup
--check-model` CLI both call ReadinessChecker.check() and render the same
ReadinessResult. Registry writes happen only on explicit confirmation --
this module exposes write_manifest_to_registry(); prompting is the
caller's job.

Probe calls go through OllamaProvider so a round exercises the exact code
path a real worker call takes (tool formatting/injection, extraction,
retries) -- a round that passes here passes in production by construction.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    PrivacyTier,
    ProviderType,
    RoutingPolicy,
    AgentRole,
    ToolDefinition,
    ToolProtocol,
    WorkerManifest,
    WorkerRole,
    WorkerStatus,
    WorkerTask,
)

logger = logging.getLogger(__name__)

# Callable types for HTTP injection, same pattern as OllamaProvider.
_PostFn = Callable[[str, dict], Awaitable[tuple[int, dict]]]
_GetFn = Callable[[str], Awaitable[tuple[int, dict]]]

_DEFAULT_REGISTRY_PATH = (
    Path(__file__).parent.parent.parent / "config" / "workers" / "worker_registry.yaml"
)

# Fallback when neither /api/show nor an existing registry entry reports a
# context window. Deliberately small: role assignment (B.4.6) treats context
# thresholds as promotions, so an unknown window must not promote.
_FALLBACK_CONTEXT_WINDOW = 8192

# The B.4.3 probe tool: unambiguous (unanswerable without the tool), one
# required string parameter, needs no actual execution.
PROBE_TOOL = ToolDefinition(
    name="get_current_time",
    description="Returns the current time in the specified timezone.",
    parameters={
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "IANA timezone string e.g. America/Chicago",
            }
        },
        "required": ["timezone"],
    },
)
PROBE_PROMPT = "What time is it in Chicago?"

# Round order is the point of the protocol: prefer the richest dialect the
# model actually supports, falling back to progressively cruder ones.
_PROBE_ROUNDS = (ToolProtocol.NATIVE, ToolProtocol.LFM25, ToolProtocol.JSON_EXTRACT)


@dataclass
class ProbeResult:
    """One round of the B.4.3 probe protocol (B.4.5)."""
    protocol: ToolProtocol
    attempted: bool
    succeeded: bool
    raw_response: str | None
    parsed: dict | None
    error: str | None


@dataclass
class ReadinessResult:
    """Full outcome of a readiness check (B.4.5 + B.4.6 roles)."""
    model_id: str                       # suggested registry id
    ollama_model: str                   # the model name as probed
    pulled_locally: bool

    native_result: ProbeResult
    lfm25_result: ProbeResult
    json_extract_result: ProbeResult

    supported: bool
    recommended_protocol: ToolProtocol | None
    recommended_capabilities: set[Capability]
    recommended_roles: list[WorkerRole]
    raw_response: str                   # winning (or last attempted) round's raw text
    parsed_tool_call: dict | None       # what the winning round extracted
    suggested_manifest: WorkerManifest | None


def _unattempted(protocol: ToolProtocol) -> ProbeResult:
    return ProbeResult(
        protocol=protocol,
        attempted=False,
        succeeded=False,
        raw_response=None,
        parsed=None,
        error=None,
    )


def assign_roles(
    location: ComputeLocation,
    context_window: int,
    protocol: ToolProtocol,
) -> list[WorkerRole]:
    """
    B.4.6 role-assignment rules, applied after probing. Order within the
    list is presentation order only -- roles carry no ranking.
    """
    if location == ComputeLocation.LOCAL_HARDWARE:
        roles = [WorkerRole.BACKGROUND_AGENT, WorkerRole.EXECUTION_WORKER]
        if context_window >= 32768:
            roles.append(WorkerRole.REASONING_WORKER)
    elif context_window >= 32768:
        roles = [WorkerRole.REASONING_WORKER, WorkerRole.ORCHESTRATOR]
    else:
        # Cloud below the reasoning threshold isn't covered by a B.4.6 rule;
        # tool execution is the one thing the probe itself confirmed.
        roles = [WorkerRole.EXECUTION_WORKER]

    if context_window >= 128000 and WorkerRole.ORCHESTRATOR not in roles:
        roles.append(WorkerRole.ORCHESTRATOR)

    if protocol in (ToolProtocol.LFM25, ToolProtocol.JSON_EXTRACT):
        # EXECUTION_WORKER confirmed; ORCHESTRATOR not recommended --
        # planning requires reliable structured output across turns.
        if WorkerRole.EXECUTION_WORKER not in roles:
            roles.insert(0, WorkerRole.EXECUTION_WORKER)
        roles = [r for r in roles if r != WorkerRole.ORCHESTRATOR]

    return roles


class ReadinessChecker:
    """
    Runs the 3-round probe protocol against one Ollama model and produces a
    ReadinessResult with a suggested WorkerManifest on success.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        registry_path: Path = _DEFAULT_REGISTRY_PATH,
        provider=None,
        *,
        _get_fn: _GetFn | None = None,
        _post_fn: _PostFn | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._registry_path = registry_path
        if provider is None:
            from tasker.workers.providers.ollama import OllamaProvider
            provider = OllamaProvider(base_url)
        self._provider = provider
        self._get_fn = _get_fn or self._default_get
        self._post_fn = _post_fn or self._default_post

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    async def check(self, model_name: str) -> ReadinessResult:
        existing = self._existing_registry_entry(model_name)
        location = self._infer_location(model_name, existing)

        pulled = await self._is_pulled(model_name)
        if not pulled and location == ComputeLocation.LOCAL_HARDWARE:
            # B.4.2: never auto-pull. Report and stop -- the caller shows
            # the `ollama pull` command and the user decides. Cloud models
            # are exempt: a signed-in server serves them via /api/chat even
            # when absent from /api/tags (B.4.2 cloud-model exception).
            return ReadinessResult(
                model_id=self._suggest_id(model_name, location, existing),
                ollama_model=model_name,
                pulled_locally=False,
                native_result=_unattempted(ToolProtocol.NATIVE),
                lfm25_result=_unattempted(ToolProtocol.LFM25),
                json_extract_result=_unattempted(ToolProtocol.JSON_EXTRACT),
                supported=False,
                recommended_protocol=None,
                recommended_capabilities=set(),
                recommended_roles=[],
                raw_response="",
                parsed_tool_call=None,
                suggested_manifest=None,
            )

        context_window = await self._resolve_context_window(model_name, existing)

        probes: dict[ToolProtocol, ProbeResult] = {p: _unattempted(p) for p in _PROBE_ROUNDS}
        winning: ProbeResult | None = None
        duration_ms = 0
        for protocol in _PROBE_ROUNDS:
            probe, probe_duration_ms = await self._probe(model_name, protocol, location, context_window)
            probes[protocol] = probe
            if probe.succeeded:
                winning = probe
                duration_ms = probe_duration_ms
                break

        supported = winning is not None
        protocol = winning.protocol if winning else None
        roles = assign_roles(location, context_window, protocol) if supported else []
        capabilities = self._recommend_capabilities(existing) if supported else set()

        manifest = None
        if supported:
            manifest = self._build_manifest(
                model_name, location, protocol, context_window,
                capabilities, roles, duration_ms, existing,
            )

        attempted = [p for p in probes.values() if p.attempted]
        last_raw = next(
            (p.raw_response for p in reversed(attempted) if p.raw_response), ""
        )
        return ReadinessResult(
            model_id=self._suggest_id(model_name, location, existing),
            ollama_model=model_name,
            pulled_locally=pulled,
            native_result=probes[ToolProtocol.NATIVE],
            lfm25_result=probes[ToolProtocol.LFM25],
            json_extract_result=probes[ToolProtocol.JSON_EXTRACT],
            supported=supported,
            recommended_protocol=protocol,
            recommended_capabilities=capabilities,
            recommended_roles=roles,
            raw_response=(winning.raw_response if winning else last_raw) or "",
            parsed_tool_call=winning.parsed if winning else None,
            suggested_manifest=manifest,
        )

    # ------------------------------------------------------------------ #
    # Probe machinery
    # ------------------------------------------------------------------ #

    async def _probe(
        self,
        model_name: str,
        protocol: ToolProtocol,
        location: ComputeLocation,
        context_window: int,
    ) -> tuple[ProbeResult, int]:
        manifest = WorkerManifest(
            id=f"readiness-probe-{protocol.value}",
            provider=ProviderType.OLLAMA,
            model_id=model_name,
            compute_location=location,
            capabilities={Capability.TOOL_USE},
            tool_protocol=protocol,
            context_window=context_window,
            cost_input=0.0,
            cost_output=0.0,
            ollama_usage_level=None,
            latency_class=LatencyClass.MEDIUM,
            available=True,
            requires_gpu=False,
            vram_mb=None,
        )
        task = WorkerTask(
            task_id=f"readiness-{protocol.value}",
            step_index=0,
            role=AgentRole.WORKER,
            instruction=PROBE_PROMPT,
            tools=[PROBE_TOOL],
            context={},
            routing_policy=RoutingPolicy.COST_OPTIMIZED,
            privacy_tier=PrivacyTier.OLLAMA_CLOUD_OK,
        )

        try:
            result = await self._provider.execute(task, manifest)
        except Exception as exc:
            return ProbeResult(
                protocol=protocol,
                attempted=True,
                succeeded=False,
                raw_response=None,
                parsed=None,
                error=f"{type(exc).__name__}: {exc}",
            ), 0

        if result.status != WorkerStatus.SUCCESS:
            return ProbeResult(
                protocol=protocol,
                attempted=True,
                succeeded=False,
                raw_response=result.output,
                parsed=None,
                error=result.reason or f"worker status {result.status.value}",
            ), result.duration_ms

        # B.4.3 success criterion: at least one extracted call naming the
        # probe tool with its required argument present.
        parsed = next(
            (
                {"name": tr.tool_name, "arguments": tr.tool_input}
                for tr in result.tool_results
                if tr.tool_name == PROBE_TOOL.name
                and isinstance(tr.tool_input, dict)
                and "timezone" in tr.tool_input
            ),
            None,
        )
        return ProbeResult(
            protocol=protocol,
            attempted=True,
            succeeded=parsed is not None,
            raw_response=result.output,
            parsed=parsed,
            error=None if parsed is not None else "no valid get_current_time call in response",
        ), result.duration_ms

    # ------------------------------------------------------------------ #
    # Model metadata resolution
    # ------------------------------------------------------------------ #

    async def _is_pulled(self, model_name: str) -> bool:
        try:
            status, data = await self._get_fn(f"{self._base_url}/api/tags")
        except Exception as exc:
            logger.warning("Readiness: could not query %s/api/tags: %s", self._base_url, exc)
            return False
        if status != 200:
            return False
        names = [m.get("name", "") for m in data.get("models", [])]
        if model_name in names:
            return True
        # A tagless name matches its own :latest (Ollama's own resolution rule).
        return ":" not in model_name and f"{model_name}:latest" in names

    async def _resolve_context_window(
        self, model_name: str, existing: WorkerManifest | None,
    ) -> int:
        """/api/show's model_info is authoritative; registry entry is the
        fallback; a deliberately small default otherwise (see constant)."""
        try:
            status, data = await self._post_fn(
                f"{self._base_url}/api/show", {"model": model_name}
            )
            if status == 200:
                model_info = data.get("model_info") or {}
                for key, value in model_info.items():
                    if key.endswith(".context_length") and isinstance(value, int):
                        return value
        except Exception as exc:
            logger.warning("Readiness: /api/show failed for %s: %s", model_name, exc)
        if existing is not None:
            return existing.context_window
        return _FALLBACK_CONTEXT_WINDOW

    def _existing_registry_entry(self, model_name: str) -> WorkerManifest | None:
        from tasker.workers.registry import WorkerRegistry
        try:
            registry = WorkerRegistry.load_from_yaml(self._registry_path)
        except Exception:
            return None
        return next(
            (w for w in registry.list_all()
             if w.provider == ProviderType.OLLAMA and w.model_id == model_name),
            None,
        )

    @staticmethod
    def _infer_location(
        model_name: str, existing: WorkerManifest | None,
    ) -> ComputeLocation:
        if existing is not None:
            return existing.compute_location
        # Ollama Cloud models carry "cloud" in the tag ("kimi-k2.7-code:cloud",
        # "qwen3-coder:480b-cloud").
        tag = model_name.split(":")[-1] if ":" in model_name else ""
        return ComputeLocation.OLLAMA_CLOUD if "cloud" in tag else ComputeLocation.LOCAL_HARDWARE

    @staticmethod
    def _suggest_id(
        model_name: str,
        location: ComputeLocation,
        existing: WorkerManifest | None,
    ) -> str:
        if existing is not None:
            return existing.id
        base = model_name.split(":")[0].replace("/", "-").lower()
        suffix = "-local" if location == ComputeLocation.LOCAL_HARDWARE else "-cloud"
        return f"{base}{suffix}"

    @staticmethod
    def _recommend_capabilities(existing: WorkerManifest | None) -> set[Capability]:
        # Only TOOL_USE is empirically confirmed by the probe. An existing
        # registry entry's hand-curated capabilities are kept (union) so a
        # re-check never silently narrows a worker.
        caps = {Capability.TOOL_USE}
        if existing is not None:
            caps |= existing.capabilities
        return caps

    @staticmethod
    def _build_manifest(
        model_name: str,
        location: ComputeLocation,
        protocol: ToolProtocol,
        context_window: int,
        capabilities: set[Capability],
        roles: list[WorkerRole],
        duration_ms: int,
        existing: WorkerManifest | None,
    ) -> WorkerManifest:
        if duration_ms < 2_000:
            latency = LatencyClass.FAST
        elif duration_ms < 10_000:
            latency = LatencyClass.MEDIUM
        else:
            latency = LatencyClass.SLOW

        if existing is not None:
            usage_level = existing.ollama_usage_level
        elif location == ComputeLocation.OLLAMA_CLOUD:
            # Unknown cloud model: assume MEDIUM until measured -- budget
            # accounting errs busy rather than free.
            from tasker.workers.base import OllamaUsageLevel
            usage_level = OllamaUsageLevel.MEDIUM
        else:
            usage_level = None

        return WorkerManifest(
            id=ReadinessChecker._suggest_id(model_name, location, existing),
            provider=ProviderType.OLLAMA,
            model_id=model_name,
            compute_location=location,
            capabilities=capabilities,
            tool_protocol=protocol,
            context_window=context_window,
            cost_input=existing.cost_input if existing else 0.0,
            cost_output=existing.cost_output if existing else 0.0,
            ollama_usage_level=usage_level,
            latency_class=latency,
            available=True,
            requires_gpu=existing.requires_gpu if existing else False,
            vram_mb=existing.vram_mb if existing else None,
            # "tool" is the tested-first default for non-NATIVE protocols;
            # fall back to "user" manually if Ollama rejects it (A.2b).
            tool_result_role=None if protocol == ToolProtocol.NATIVE else "tool",
            worker_role=list(roles),
        )

    # ------------------------------------------------------------------ #
    # Default HTTP (aiohttp) -- mirrors OllamaProvider's injection pattern
    # ------------------------------------------------------------------ #

    async def _default_get(self, url: str) -> tuple[int, dict]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return resp.status, await resp.json()

    async def _default_post(self, url: str, payload: dict) -> tuple[int, dict]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status, await resp.json()


# --------------------------------------------------------------------------- #
# Registry write (on confirmation -- prompting is the caller's job)
# --------------------------------------------------------------------------- #

_REGISTRY_ENTRY_KEYS = (
    # YAML schema order (SDD 8.3); runtime-only fields (available,
    # capability_scores) are intentionally not persisted.
    "id", "provider", "model_id", "compute_location", "capabilities",
    "tool_protocol", "tool_result_role", "context_window", "cost_input",
    "cost_output", "ollama_usage_level", "latency_class", "requires_gpu",
    "vram_mb", "worker_role",
)


def _format_registry_entry(manifest: WorkerManifest) -> str:
    """One worker entry as an indented YAML block matching the file's
    existing 2-space list style."""
    data = manifest.to_dict()
    entry = {}
    for key in _REGISTRY_ENTRY_KEYS:
        value = data.get(key)
        if key in ("tool_result_role", "vram_mb") and value is None:
            continue  # optional keys: omit rather than write nulls
        if key == "worker_role" and not value:
            continue
        entry[key] = value
    dumped = yaml.safe_dump(entry, sort_keys=False, default_flow_style=False)
    lines = dumped.rstrip("\n").splitlines()
    block = [f"  - {lines[0]}"] + [f"    {line}" for line in lines[1:]]
    return "\n".join(block) + "\n"


def write_manifest_to_registry(
    manifest: WorkerManifest, path: Path = _DEFAULT_REGISTRY_PATH,
) -> str:
    """
    Persist a confirmed manifest to worker_registry.yaml. Returns "added" or
    "updated".

    Text-splicing rather than a YAML round-trip, deliberately: PyYAML drops
    comments on dump, and this file's hand-written comments carry real
    institutional knowledge (e.g. the lfm2.5 native->lfm25 history). A new
    id is appended verbatim after the existing content; an existing id has
    exactly its own "- id:" block replaced (any comments inside that one
    block are superseded along with the entry itself).
    """
    text = path.read_text(encoding="utf-8")
    entry_block = _format_registry_entry(manifest)

    # Locate an existing block for this id: from its "- id: <id>" line to
    # the next "- id:" line (or EOF).
    lines = text.splitlines(keepends=True)
    start = end = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None:
            if stripped == f"- id: {manifest.id}":
                start = i
        elif stripped.startswith("- id:"):
            end = i
            break
    if start is not None:
        end = end if end is not None else len(lines)
        # Keep trailing blank lines of the old block as the separator.
        block_lines = lines[start:end]
        trailing_blanks = []
        while block_lines and block_lines[-1].strip() == "":
            trailing_blanks.insert(0, block_lines.pop())
        new_text = "".join(lines[:start]) + entry_block + "".join(trailing_blanks) + "".join(lines[end:])
        path.write_text(new_text, encoding="utf-8")
        logger.info("Readiness: updated registry entry '%s' in %s", manifest.id, path)
        return "updated"

    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + "\n" + entry_block, encoding="utf-8")
    logger.info("Readiness: added registry entry '%s' to %s", manifest.id, path)
    return "added"


# --------------------------------------------------------------------------- #
# Report rendering (B.4.4) -- shared by the CLI and the future TUI panel
# --------------------------------------------------------------------------- #

_RULE = "─" * 62


def _round_lines(title: str, probe: ProbeResult) -> list[str]:
    lines = [f"{title}"]
    if not probe.attempted:
        lines.append("  Result:   NOT ATTEMPTED (earlier round succeeded)"
                     if title.startswith("ROUND 2") or title.startswith("ROUND 3")
                     else "  Result:   NOT ATTEMPTED")
        return lines
    if probe.succeeded:
        lines.append("  Result:   SUPPORTED")
        if probe.raw_response:
            lines.append(f"  Response: {probe.raw_response.strip()[:200]}")
        if probe.parsed:
            args = ", ".join(f'{k}="{v}"' for k, v in probe.parsed["arguments"].items())
            lines.append(f"  Parsed:   {probe.parsed['name']}({args}) ✓")
    else:
        lines.append(f"  Result:   REJECTED ({probe.error or 'no valid tool call'})")
        if probe.raw_response:
            lines.append(f"  Response: {probe.raw_response.strip()[:200]}")
    return lines


def format_report(result: ReadinessResult) -> str:
    probed = result.native_result.attempted
    if result.pulled_locally:
        pulled_line = "YES"
    elif probed:
        pulled_line = "NO (Ollama Cloud model -- pull not required)"
    else:
        pulled_line = "NO"
    lines = [
        "MODEL READINESS REPORT",
        _RULE,
        f"Model:          {result.ollama_model}",
        f"Pulled locally: {pulled_line}",
        "",
    ]
    if not probed:
        lines += [
            "Model is not pulled -- probes not run.",
            f"Run: ollama pull {result.ollama_model}",
            "then re-run this check. (The checker never pulls automatically.)",
        ]
        return "\n".join(lines)

    lines += _round_lines("ROUND 1 — Native API (tools[])", result.native_result)
    lines.append("")
    lines += _round_lines("ROUND 2 — LFM25 (system prompt injection, JSON output)", result.lfm25_result)
    lines.append("")
    lines += _round_lines("ROUND 3 — JSON_EXTRACT (generic JSON injection)", result.json_extract_result)
    lines.append("")

    if result.supported:
        roles = ", ".join(r.value for r in result.recommended_roles) or "(none)"
        caps = ", ".join(sorted(c.value for c in result.recommended_capabilities))
        lines += [
            f"Recommended protocol:  {result.recommended_protocol.value}",
            f"Recommended roles:     {roles}",
            f"Capabilities:          {caps}",
        ]
        if result.suggested_manifest is not None:
            lines += [
                "",
                "WORKER REGISTRY ENTRY",
                _RULE,
                _format_registry_entry(result.suggested_manifest).rstrip("\n"),
            ]
    else:
        lines += [
            "VERDICT: NOT SUPPORTED -- no probe round produced a valid",
            "get_current_time call. This model cannot be used as a harness",
            "worker (Capability.TOOL_USE is mandatory at registration).",
        ]
    return "\n".join(lines)
