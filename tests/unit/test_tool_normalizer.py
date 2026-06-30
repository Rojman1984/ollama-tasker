"""
Unit tests -- ToolCallNormalizer (tasker/tools/normalizer.py)
Phase 4 -- SDD Section 5.7
"""
import json
import unittest

from tasker.tools.normalizer import ToolCallNormalizer
from tasker.workers.base import ToolDefinition, ToolProtocol, WorkerToolResult


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

def _tool(name: str = "my_tool") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="Does something useful",
        parameters={"type": "object", "properties": {"x": {"type": "string"}}},
    )


def _native_call(name: str, args: dict, call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args),
        },
    }


# ------------------------------------------------------------------ #
# NATIVE protocol
# ------------------------------------------------------------------ #

class TestNativeProtocol(unittest.TestCase):

    def test_extract_single_call(self):
        calls = [_native_call("bash", {"cmd": "ls"})]
        results = ToolCallNormalizer.extract(None, calls, ToolProtocol.NATIVE)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "bash")
        self.assertEqual(results[0].tool_input, {"cmd": "ls"})

    def test_extract_multiple_calls(self):
        calls = [
            _native_call("read_file", {"path": "/etc/hosts"}, "c1"),
            _native_call("write_file", {"path": "/tmp/out", "content": "x"}, "c2"),
        ]
        results = ToolCallNormalizer.extract("", calls, ToolProtocol.NATIVE)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].tool_name, "read_file")
        self.assertEqual(results[1].tool_name, "write_file")

    def test_extract_empty_calls_returns_empty(self):
        results = ToolCallNormalizer.extract("some text", [], ToolProtocol.NATIVE)
        self.assertEqual(results, [])

    def test_extract_none_calls_returns_empty(self):
        results = ToolCallNormalizer.extract("some text", None, ToolProtocol.NATIVE)
        self.assertEqual(results, [])

    def test_output_fields_are_none_on_extract(self):
        calls = [_native_call("tool", {"k": "v"})]
        r = ToolCallNormalizer.extract(None, calls, ToolProtocol.NATIVE)[0]
        self.assertIsNone(r.tool_output)
        self.assertIsNone(r.error)
        self.assertEqual(r.duration_ms, 0)

    def test_malformed_arguments_string_stored_raw(self):
        calls = [{"id": "c1", "type": "function", "function": {"name": "tool", "arguments": "not_json"}}]
        r = ToolCallNormalizer.extract(None, calls, ToolProtocol.NATIVE)[0]
        self.assertEqual(r.tool_name, "tool")
        self.assertIn("raw", r.tool_input)

    def test_arguments_as_dict_accepted(self):
        # Some providers pass arguments already as dict (e.g., Ollama pre-normalized)
        calls = [{"id": "c1", "type": "function", "function": {"name": "tool", "arguments": {"x": 1}}}]
        r = ToolCallNormalizer.extract(None, calls, ToolProtocol.NATIVE)[0]
        self.assertEqual(r.tool_input, {"x": 1})


# ------------------------------------------------------------------ #
# JSON_EXTRACT protocol
# ------------------------------------------------------------------ #

class TestJsonExtractProtocol(unittest.TestCase):

    def test_extract_from_fenced_block(self):
        text = '```json\n{"tool_name": "bash", "arguments": {"cmd": "pwd"}}\n```'
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.JSON_EXTRACT)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "bash")
        self.assertEqual(results[0].tool_input["cmd"], "pwd")

    def test_extract_tool_key_alias(self):
        text = '```json\n{"tool": "search", "arguments": {"q": "python"}}\n```'
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.JSON_EXTRACT)
        self.assertEqual(results[0].tool_name, "search")

    def test_extract_name_key_alias(self):
        text = '```json\n{"name": "calculator", "args": {"expr": "2+2"}}\n```'
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.JSON_EXTRACT)
        self.assertEqual(results[0].tool_name, "calculator")

    def test_extract_no_json_returns_empty(self):
        results = ToolCallNormalizer.extract("Just a plain answer.", None, ToolProtocol.JSON_EXTRACT)
        self.assertEqual(results, [])

    def test_output_fields_are_none(self):
        text = '```json\n{"tool_name": "t", "arguments": {}}\n```'
        r = ToolCallNormalizer.extract(text, None, ToolProtocol.JSON_EXTRACT)[0]
        self.assertIsNone(r.tool_output)
        self.assertIsNone(r.error)


# ------------------------------------------------------------------ #
# XML_EXTRACT protocol
# ------------------------------------------------------------------ #

class TestXmlExtractProtocol(unittest.TestCase):

    def test_extract_single_tag(self):
        text = 'I will call the tool. <tool_call>{"name": "bash", "arguments": {"cmd": "ls"}}</tool_call>'
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.XML_EXTRACT)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "bash")
        self.assertEqual(results[0].tool_input["cmd"], "ls")

    def test_extract_multiple_tags(self):
        text = (
            '<tool_call>{"name": "read", "arguments": {"path": "/a"}}</tool_call>'
            ' then '
            '<tool_call>{"name": "write", "input": {"path": "/b", "content": "x"}}</tool_call>'
        )
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.XML_EXTRACT)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].tool_name, "read")
        self.assertEqual(results[1].tool_name, "write")

    def test_extract_tool_name_alias(self):
        text = '<tool_call>{"tool_name": "search", "args": {"q": "AI"}}</tool_call>'
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.XML_EXTRACT)
        self.assertEqual(results[0].tool_name, "search")

    def test_extract_no_tag_returns_empty(self):
        results = ToolCallNormalizer.extract("No tags here.", None, ToolProtocol.XML_EXTRACT)
        self.assertEqual(results, [])

    def test_malformed_json_in_tag_skipped(self):
        text = '<tool_call>not valid json</tool_call>'
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.XML_EXTRACT)
        self.assertEqual(results, [])


# ------------------------------------------------------------------ #
# FEW_SHOT protocol
# ------------------------------------------------------------------ #

class TestFewShotProtocol(unittest.TestCase):

    def test_extract_tool_call_prefix(self):
        text = 'Let me check. TOOL_CALL: {"name": "bash", "arguments": {"cmd": "date"}}'
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.FEW_SHOT)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "bash")
        self.assertEqual(results[0].tool_input["cmd"], "date")

    def test_extract_multiple_calls(self):
        text = (
            'First TOOL_CALL: {"name": "search", "arguments": {"q": "news"}}'
            ' then TOOL_CALL: {"name": "summarize", "args": {}}'
        )
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.FEW_SHOT)
        self.assertEqual(len(results), 2)

    def test_extract_no_prefix_returns_empty(self):
        results = ToolCallNormalizer.extract("plain answer", None, ToolProtocol.FEW_SHOT)
        self.assertEqual(results, [])


# ------------------------------------------------------------------ #
# format_tools
# ------------------------------------------------------------------ #

class TestFormatTools(unittest.TestCase):

    def test_format_tools_openai_structure(self):
        tools = [_tool("bash"), _tool("search")]
        formatted = ToolCallNormalizer.format_tools(tools, ToolProtocol.NATIVE)
        self.assertEqual(len(formatted), 2)
        self.assertEqual(formatted[0]["type"], "function")
        self.assertEqual(formatted[0]["function"]["name"], "bash")
        self.assertEqual(formatted[1]["function"]["name"], "search")

    def test_format_tools_includes_description(self):
        tools = [_tool("my_tool")]
        formatted = ToolCallNormalizer.format_tools(tools, ToolProtocol.NATIVE)
        self.assertEqual(formatted[0]["function"]["description"], "Does something useful")

    def test_format_tools_includes_parameters(self):
        tools = [_tool()]
        formatted = ToolCallNormalizer.format_tools(tools, ToolProtocol.NATIVE)
        self.assertIn("parameters", formatted[0]["function"])

    def test_format_tools_empty_list(self):
        self.assertEqual(ToolCallNormalizer.format_tools([], ToolProtocol.NATIVE), [])

    def test_format_tools_same_structure_all_protocols(self):
        tools = [_tool()]
        for protocol in ToolProtocol:
            result = ToolCallNormalizer.format_tools(tools, protocol)
            self.assertEqual(len(result), 1)
            self.assertIn("function", result[0])


if __name__ == "__main__":
    unittest.main()
