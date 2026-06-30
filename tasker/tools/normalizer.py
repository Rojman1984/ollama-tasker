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
See SDD Section 5.7.
"""
from __future__ import annotations

import json
import re

from tasker.workers.base import ToolDefinition, ToolProtocol, WorkerToolResult


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
    ) -> list[WorkerToolResult]:
        """
        Extract tool call requests from a model response.

        response_text: the text portion of the model's reply
        native_calls:  provider-normalized tool_calls array (OpenAI format)
                       used only for NATIVE protocol
        protocol:      which format to parse
        """
        if protocol == ToolProtocol.NATIVE:
            return ToolCallNormalizer._extract_native(native_calls)
        if protocol == ToolProtocol.JSON_EXTRACT:
            return ToolCallNormalizer._extract_json(response_text)
        if protocol == ToolProtocol.XML_EXTRACT:
            return ToolCallNormalizer._extract_xml(response_text)
        if protocol == ToolProtocol.FEW_SHOT:
            return ToolCallNormalizer._extract_few_shot(response_text)
        return []

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
