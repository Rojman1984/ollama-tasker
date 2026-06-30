"""
tasker.tools.normalizer
------------------------
ToolCallNormalizer -- translates model-specific tool call formats
to the standard WorkerToolResult.

Protocols:
  NATIVE      -- standard tool_calls[] in response
  JSON_EXTRACT-- tool call embedded in JSON text block
  XML_EXTRACT -- tool call in <tool_call> XML tags
  FEW_SHOT    -- no native support; few-shot examples injected
See SDD Section 5.7.
"""
from __future__ import annotations

# TODO Phase 4