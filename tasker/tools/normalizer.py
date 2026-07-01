"""
tasker.tools.normalizer
------------------------
ToolCallNormalizer -- translates model-specific tool call formats
to the standard WorkerToolResult, and formats tool definitions for
model input.

Protocols:
  NATIVE      -- standard tool_calls[] in response (OpenAI format)
  JSON_EXTRACT-- tool call embedded in a JSON text block
  XML_EXTRACT -- tool call in <tool_call> XML tags
  FEW_SHOT    -- few-shot taught format (TOOL_CALL: {...})
  LFM25       -- LFM2.5-Instruct/Thinking: JSON array primary, Pythonic
                 <|tool_call_start|>/<|tool_call_end|> fallback. No wrapper
                 tokens on input, unlike LFM2's <|tool_list_start|>/
                 <|tool_list_end|>. See SDD Section 5.7 and
                 SDD_ADDENDUM_7.5.md A.2b.
"""
from __future__ import annotations

import json
import re

from tasker.workers.base import ToolDefinition, ToolProtocol, WorkerToolResult

_LFM25_CALL_START = "<|tool_call_start|>"
_LFM25_CALL_END = "<|tool_call_end|>"
_LFM25_PYTHONIC_RE = re.compile(r"^(\w+)\((.*)\)$", re.DOTALL)
_LFM25_KWARG_RE = re.compile(r'(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"')


def _infer_tool_from_flat_object(item: dict, tools: list[ToolDefinition]) -> str | None:
    """
    Given a dict with no {"name", "arguments"} envelope, guess which
    offered tool it was meant to call by matching its keys against each
    tool's JSON Schema parameters (all its keys must be required or
    known-optional properties, and every required key must be present).
    Returns the tool name only if exactly one tool matches uniquely --
    ambiguous matches are left unresolved rather than guessed.
    """
    item_keys = set(item.keys())
    matches = []
    for t in tools:
        required = set(t.parameters.get("required", []))
        properties = set(t.parameters.get("properties", {}).keys())
        if not required:
            continue  # nothing to anchor the match on -- too ambiguous
        if required.issubset(item_keys) and item_keys.issubset(properties | required):
            matches.append(t.name)
    return matches[0] if len(matches) == 1 else None


class ToolCallNormalizer:
    """
    Stateless helper. All methods are static.

    extract(): model response → list[WorkerToolResult] with tool_output=None
               (output is filled after the tool actually executes)
    format_tools(): list[ToolDefinition] → OpenAI-compatible list[dict]
                    (all protocols; text-based providers embed this in the system prompt)
    """

    # ------------------------------------------------------------------ #
    # Output normalization  (model response → WorkerToolResult)
    # ------------------------------------------------------------------ #

    @staticmethod
    def extract(
        response_text: str | None,
        native_calls: list[dict] | None,
        protocol: ToolProtocol,
        tools: list[ToolDefinition] | None = None,
    ) -> list[WorkerToolResult]:
        """
        Extract tool call requests from a model response.

        response_text: the text portion of the model's reply
        native_calls:  provider-normalized tool_calls array (OpenAI format)
                       used only for NATIVE protocol
        protocol:      which format to parse
        tools:         the tool definitions offered to the model this turn.
                       Only consumed by LFM25 -- see _extract_lfm25's
                       docstring for why. Every other protocol ignores it.
        """
        if protocol == ToolProtocol.NATIVE:
            return ToolCallNormalizer._extract_native(native_calls)
        if protocol == ToolProtocol.JSON_EXTRACT:
            return ToolCallNormalizer._extract_json(response_text)
        if protocol == ToolProtocol.XML_EXTRACT:
            return ToolCallNormalizer._extract_xml(response_text)
        if protocol == ToolProtocol.FEW_SHOT:
            return ToolCallNormalizer._extract_few_shot(response_text)
        if protocol == ToolProtocol.LFM25:
            return ToolCallNormalizer._extract_lfm25(response_text, tools)
        return []

    @staticmethod
    def extract_tool_calls(
        response_text: str | None,
        protocol: ToolProtocol,
        tools: list[ToolDefinition] | None = None,
    ) -> list[WorkerToolResult]:
        """
        Convenience entry point for non-NATIVE callers (e.g. OllamaProvider)
        that only have response text, never a native_calls array. Equivalent
        to extract(response_text, None, protocol, tools).
        """
        return ToolCallNormalizer.extract(response_text, None, protocol, tools)

    @staticmethod
    def _extract_native(native_calls: list[dict] | None) -> list[WorkerToolResult]:
        """Parse OpenAI-format tool_calls array."""
        results = []
        for call in native_calls or []:
            func = call.get("function", {})
            name = func.get("name", "")
            raw_args = func.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except (json.JSONDecodeError, TypeError):
                args = {"raw": raw_args}
            results.append(
                WorkerToolResult(
                    tool_name=name,
                    tool_input=args,
                    tool_output=None,
                    error=None,
                    duration_ms=0,
                )
            )
        return results

    @staticmethod
    def _extract_json(response_text: str | None) -> list[WorkerToolResult]:
        """
        Parse tool calls embedded as JSON in response text.
        Supports:
          - ```json blocks
          - bare JSON objects/arrays containing "tool_name"/"tool"/"name" keys
        """
        text = response_text or ""
        results = []

        # Try fenced code block first
        block_match = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", text, re.DOTALL)
        if block_match:
            raw = block_match.group(1)
        else:
            # Try bare JSON object with a tool/name key
            raw_match = re.search(
                r'(\{[^{}]*(?:"tool(?:_name)?"|"name")[^{}]*\})',
                text,
                re.DOTALL,
            )
            raw = raw_match.group(1) if raw_match else None

        if not raw:
            return results

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return results

        if isinstance(data, dict):
            data = [data]
        for item in data:
            name = item.get("tool_name") or item.get("tool") or item.get("name", "")
            args = item.get("arguments") or item.get("args") or {}
            results.append(
                WorkerToolResult(
                    tool_name=name,
                    tool_input=args if isinstance(args, dict) else {"value": args},
                    tool_output=None,
                    error=None,
                    duration_ms=0,
                )
            )
        return results

    @staticmethod
    def _extract_xml(response_text: str | None) -> list[WorkerToolResult]:
        """Parse tool calls from <tool_call>JSON</tool_call> tags."""
        text = response_text or ""
        results = []
        for match in re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL):
            raw = match.group(1).strip()
            try:
                data = json.loads(raw)
                name = data.get("name") or data.get("tool_name", "")
                args = data.get("arguments") or data.get("args") or data.get("input") or {}
                results.append(
                    WorkerToolResult(
                        tool_name=name,
                        tool_input=args if isinstance(args, dict) else {"value": args},
                        tool_output=None,
                        error=None,
                        duration_ms=0,
                    )
                )
            except json.JSONDecodeError:
                pass
        return results

    @staticmethod
    def _extract_few_shot(response_text: str | None) -> list[WorkerToolResult]:
        """
        Parse tool calls taught via few-shot examples.
        Expected format: TOOL_CALL: {"name": "...", "arguments": {...}}
        Uses raw_decode so nested JSON objects are parsed correctly.
        """
        text = response_text or ""
        results = []
        decoder = json.JSONDecoder()
        for match in re.finditer(r"TOOL_CALL:\s*", text):
            try:
                data, _ = decoder.raw_decode(text, match.end())
                name = data.get("name") or data.get("tool_name", "")
                args = data.get("arguments") or data.get("args") or {}
                results.append(
                    WorkerToolResult(
                        tool_name=name,
                        tool_input=args if isinstance(args, dict) else {"value": args},
                        tool_output=None,
                        error=None,
                        duration_ms=0,
                    )
                )
            except (json.JSONDecodeError, ValueError):
                pass
        return results

    @staticmethod
    def _extract_lfm25(
        response_text: str | None,
        tools: list[ToolDefinition] | None = None,
    ) -> list[WorkerToolResult]:
        """
        LFM2.5 output parsing. Primary: JSON (array of calls, or a single
        call object -- live testing against lfm2.5-thinking:latest showed
        the model sometimes emits one bare object instead of a 1-element
        array, occasionally inside a ```json fence despite being told not
        to). Fallback: Pythonic <|tool_call_start|>[func(key="val")]<|tool_call_end|>.

        The JSON path uses JSONDecoder.raw_decode rather than hand-rolled
        bracket counting or a greedy regex: it is the standard library's
        own bracket/string-aware scanner, so it naturally finds the correct
        boundary even when an argument value is itself a nested dict, and
        it ignores any trailing text without needing a separate strip step.

        tools: live testing (Designlab1, lfm2.5-thinking:latest, Ollama
        0.30.11) found the model reliably drops the {"name", "arguments"}
        envelope entirely and emits the arguments as a bare flat object,
        e.g. {"command": "ls"} instead of {"name": "bash", "arguments":
        {"command": "ls"}} -- reproduced identically across multiple
        prompts, not a one-off. When an item has neither "name" nor
        "arguments" and tools is given, _infer_tool_from_flat_object()
        tries to recover the tool name from the flat object's own keys.
        """
        text = (response_text or "").strip()
        if not text:
            return []

        fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        json_candidate = fence_match.group(1).strip() if fence_match else text

        if json_candidate.startswith("[") or json_candidate.startswith("{"):
            try:
                parsed, _ = json.JSONDecoder().raw_decode(json_candidate)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                parsed = [parsed]
            if isinstance(parsed, list):
                results = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name", "")
                    args = item.get("arguments")
                    if not name and args is None and tools:
                        inferred = _infer_tool_from_flat_object(item, tools)
                        if inferred is not None:
                            name, args = inferred, item
                    args = args or {}
                    results.append(
                        WorkerToolResult(
                            tool_name=name,
                            tool_input=args if isinstance(args, dict) else {"value": args},
                            tool_output=None,
                            error=None,
                            duration_ms=0,
                        )
                    )
                if results:
                    return results

        # Fallback: Pythonic format. find() locates fixed literal token
        # boundaries -- regex would add no value here and risks matching
        # across multiple calls. Trailing text after the end token is
        # discarded simply by never slicing past end_idx.
        start_idx = text.find(_LFM25_CALL_START)
        end_idx = text.find(_LFM25_CALL_END)
        if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
            return []

        inner = text[start_idx + len(_LFM25_CALL_START):end_idx].strip()
        if inner.startswith("[") and inner.endswith("]"):
            inner = inner[1:-1].strip()

        match = _LFM25_PYTHONIC_RE.match(inner)
        if not match:
            return []

        func_name, args_str = match.group(1), match.group(2)
        args = {k: v.replace('\\"', '"') for k, v in _LFM25_KWARG_RE.findall(args_str)}
        return [
            WorkerToolResult(
                tool_name=func_name,
                tool_input=args,
                tool_output=None,
                error=None,
                duration_ms=0,
            )
        ]

    # ------------------------------------------------------------------ #
    # Input normalization  (ToolDefinition → model input format)
    # ------------------------------------------------------------------ #

    @staticmethod
    def format_tools(
        tools: list[ToolDefinition],
        protocol: ToolProtocol,
    ) -> list[dict]:
        """
        Return tool definitions in OpenAI-compatible format for all protocols.

        For NATIVE: pass directly to the tools[] field of the API request.
        For text protocols (JSON_EXTRACT, XML_EXTRACT, FEW_SHOT): providers
        serialize this list into the system prompt so the model knows what
        tools are available.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    @staticmethod
    def inject_tools(
        messages: list[dict],
        tools: list[ToolDefinition],
        protocol: ToolProtocol,
    ) -> list[dict]:
        """
        Inject tool definitions directly into the message list, for
        protocols where the provider must NOT send a native tools[]
        request parameter (Ollama rejects it for these model families).
        Returns a new list -- does not mutate the input.

        LFM25: appends "List of tools: <json>\\nOutput function calls as
        JSON" to the system message (creating one if absent). No wrapper
        tokens -- this is the key difference from the LFM2 dialect, which
        wraps definitions in <|tool_list_start|>/<|tool_list_end|>. See
        SDD_ADDENDUM_7.5.md A.2b.

        Other non-NATIVE protocols (JSON_EXTRACT, XML_EXTRACT, FEW_SHOT)
        have no registered worker today and no injection behavior defined
        yet here -- messages pass through unchanged. Implement when a real
        worker is registered on one of those protocols.
        """
        if not tools or protocol != ToolProtocol.LFM25:
            return list(messages)

        tools_json = json.dumps([
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in tools
        ])
        # "Output function calls as JSON" alone was not enough on live testing
        # against lfm2.5-thinking:latest (Ollama 0.30.11): the model reasoned
        # to the correct call inside its thinking trace but then emitted no
        # content at all. Appending an explicit "respond with ONLY the call"
        # instruction was the fix that got it into content -- see
        # SDD_ADDENDUM_7.5.md A.2b live test note.
        suffix = (
            f"List of tools: {tools_json}\n"
            "Output function calls as JSON. Respond with ONLY the JSON array "
            "function call and no other text."
        )

        result = [dict(m) for m in messages]
        for m in result:
            if m.get("role") == "system":
                m["content"] = f"{m.get('content', '')}\n{suffix}"
                return result

        result.insert(0, {"role": "system", "content": suffix})
        return result
