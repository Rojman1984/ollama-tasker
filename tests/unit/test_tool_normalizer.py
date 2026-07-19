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

    def test_extract_bare_object_with_nested_arguments(self):
        # No fence, nested {} in arguments -- the regex paths cannot match
        # this; the raw_decode fallback scan (B.4.3a) must recover it.
        text = 'Sure: {"name": "get_current_time", "arguments": {"timezone": "America/Chicago"}}'
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.JSON_EXTRACT)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "get_current_time")
        self.assertEqual(results[0].tool_input, {"timezone": "America/Chicago"})

    def test_extract_bare_array_with_nested_arguments(self):
        text = '[{"name": "get_current_time", "arguments": {"timezone": "UTC"}}]'
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.JSON_EXTRACT)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "get_current_time")
        self.assertEqual(results[0].tool_input, {"timezone": "UTC"})

    def test_scan_fallback_ignores_json_without_tool_name_key(self):
        # An arguments-only object is not trusted by the fallback scan --
        # only LFM25 does flat-object inference (anchored to tool schemas).
        text = 'Result: {"timezone": "America/Chicago"}'
        results = ToolCallNormalizer.extract(text, None, ToolProtocol.JSON_EXTRACT)
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
# LFM25 protocol
# ------------------------------------------------------------------ #

class TestLfm25InjectTools(unittest.TestCase):

    def test_appends_list_of_tools_to_system_message(self):
        messages = [{"role": "system", "content": "You are helpful."}]
        tools = [_tool("get_weather")]
        result = ToolCallNormalizer.inject_tools(messages, tools, ToolProtocol.LFM25)
        self.assertIn("List of tools:", result[0]["content"])
        self.assertIn("get_weather", result[0]["content"])

    def test_appends_json_output_instruction(self):
        messages = [{"role": "system", "content": "You are helpful."}]
        result = ToolCallNormalizer.inject_tools(messages, [_tool()], ToolProtocol.LFM25)
        self.assertIn("Output function calls as JSON", result[0]["content"])

    def test_no_wrapper_tokens(self):
        messages = [{"role": "system", "content": "sys"}]
        result = ToolCallNormalizer.inject_tools(messages, [_tool()], ToolProtocol.LFM25)
        self.assertNotIn("<|tool_list_start|>", result[0]["content"])
        self.assertNotIn("<|tool_list_end|>", result[0]["content"])

    def test_creates_system_message_if_absent(self):
        messages = [{"role": "user", "content": "hi"}]
        result = ToolCallNormalizer.inject_tools(messages, [_tool()], ToolProtocol.LFM25)
        self.assertEqual(result[0]["role"], "system")
        self.assertIn("List of tools:", result[0]["content"])
        self.assertEqual(result[1]["role"], "user")

    def test_does_not_mutate_input(self):
        messages = [{"role": "system", "content": "sys"}]
        ToolCallNormalizer.inject_tools(messages, [_tool()], ToolProtocol.LFM25)
        self.assertEqual(messages[0]["content"], "sys")

    def test_empty_tools_returns_messages_unchanged(self):
        messages = [{"role": "system", "content": "sys"}]
        result = ToolCallNormalizer.inject_tools(messages, [], ToolProtocol.LFM25)
        self.assertEqual(result, messages)

    def test_undefined_injection_protocol_passes_through_unchanged(self):
        # XML_EXTRACT/FEW_SHOT still have no injection behavior defined
        # (JSON_EXTRACT gained one in Phase 8.2 -- B.4.3a).
        messages = [{"role": "system", "content": "sys"}]
        result = ToolCallNormalizer.inject_tools(messages, [_tool()], ToolProtocol.XML_EXTRACT)
        self.assertEqual(result, messages)


class TestJsonExtractInjectTools(unittest.TestCase):

    def test_appends_tool_list_and_json_array_instruction(self):
        messages = [{"role": "system", "content": "You are helpful."}]
        result = ToolCallNormalizer.inject_tools(messages, [_tool("get_weather")], ToolProtocol.JSON_EXTRACT)
        self.assertIn("List of tools:", result[0]["content"])
        self.assertIn("get_weather", result[0]["content"])
        self.assertIn('"arguments"', result[0]["content"])

    def test_creates_system_message_if_absent(self):
        messages = [{"role": "user", "content": "hi"}]
        result = ToolCallNormalizer.inject_tools(messages, [_tool()], ToolProtocol.JSON_EXTRACT)
        self.assertEqual(result[0]["role"], "system")
        self.assertIn("List of tools:", result[0]["content"])
        self.assertEqual(result[1]["role"], "user")

    def test_does_not_mutate_input(self):
        messages = [{"role": "system", "content": "sys"}]
        ToolCallNormalizer.inject_tools(messages, [_tool()], ToolProtocol.JSON_EXTRACT)
        self.assertEqual(messages[0]["content"], "sys")


class TestLfm25ExtractToolCalls(unittest.TestCase):

    def test_json_array_single_call(self):
        text = '[{"name": "get_weather", "arguments": {"location": "McAllen, TX"}}]'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "get_weather")
        self.assertEqual(results[0].tool_input, {"location": "McAllen, TX"})

    def test_json_array_multiple_calls(self):
        text = (
            '[{"name": "a", "arguments": {"x": 1}}, '
            '{"name": "b", "arguments": {"y": 2}}]'
        )
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].tool_name, "a")
        self.assertEqual(results[1].tool_name, "b")

    def test_json_array_nested_dict_argument(self):
        text = '[{"name": "configure", "arguments": {"opts": {"nested": true, "n": 2}}}]'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        self.assertEqual(results[0].tool_input["opts"], {"nested": True, "n": 2})

    def test_pythonic_fallback_parsed(self):
        text = '<|tool_call_start|>[get_weather(location="McAllen, TX")]<|tool_call_end|>'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "get_weather")
        self.assertEqual(results[0].tool_input, {"location": "McAllen, TX"})

    def test_pythonic_trailing_text_stripped(self):
        text = (
            'Sure, let me check.'
            '<|tool_call_start|>[get_weather(location="Austin")]<|tool_call_end|>'
            ' anything after this is ignored'
        )
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_input["location"], "Austin")

    def test_plain_text_returns_empty(self):
        results = ToolCallNormalizer.extract_tool_calls("Just a plain answer.", ToolProtocol.LFM25)
        self.assertEqual(results, [])

    def test_malformed_json_array_falls_through_to_pythonic(self):
        text = '[not valid json <|tool_call_start|>[bash(cmd="ls")]<|tool_call_end|>'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "bash")

    def test_bare_json_object_without_array_wrapper_parsed(self):
        # Live testing against lfm2.5-thinking:latest showed the model
        # sometimes emits a single object instead of a 1-element array.
        text = '{"name": "get_weather", "arguments": {"location": "McAllen, TX"}}'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "get_weather")

    def test_json_object_wrapped_in_markdown_fence_parsed(self):
        # Live testing showed the model sometimes wraps its JSON in a
        # ```json fence despite being told to emit only the JSON.
        text = '```json\n{"name": "get_weather", "arguments": {"location": "Austin"}}\n```'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_input["location"], "Austin")

    def test_json_array_wrapped_in_markdown_fence_parsed(self):
        text = '```json\n[{"name": "get_weather", "arguments": {"location": "Austin"}}]\n```'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        self.assertEqual(len(results), 1)

    def test_extract_tool_calls_equivalent_to_extract_with_none_native_calls(self):
        text = '[{"name": "x", "arguments": {}}]'
        a = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        b = ToolCallNormalizer.extract(text, None, ToolProtocol.LFM25)
        self.assertEqual(a, b)


class TestLfm25FlatObjectInference(unittest.TestCase):
    """
    Live testing (Designlab1, lfm2.5-thinking:latest, Ollama 0.30.11)
    found the model reliably drops the {"name","arguments"} envelope and
    emits a bare flat object instead -- e.g. {"command": "ls"} rather
    than {"name": "bash", "arguments": {"command": "ls"}}. Reproduced
    identically across three separate prompts, not a one-off. When
    `tools` is supplied, the flat object's keys are matched against each
    offered tool's JSON Schema to recover the tool name.
    """

    def _bash_tool(self) -> ToolDefinition:
        return ToolDefinition(
            name="bash",
            description="Execute a shell command",
            parameters={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        )

    def test_flat_object_matches_unique_tool(self):
        text = '[{"command": "hostname"}]'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25, tools=[self._bash_tool()])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "bash")
        self.assertEqual(results[0].tool_input, {"command": "hostname"})

    def test_flat_object_without_array_wrapper(self):
        text = '{"command": "date"}'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25, tools=[self._bash_tool()])
        self.assertEqual(results[0].tool_name, "bash")

    def test_no_tools_given_leaves_name_empty(self):
        """Without tools, there's nothing to infer against -- unchanged, prior behavior."""
        text = '[{"command": "ls"}]'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25)
        self.assertEqual(results[0].tool_name, "")

    def test_ambiguous_match_across_two_tools_left_unresolved(self):
        other_tool = ToolDefinition(
            name="run_shell",
            description="Also takes a command",
            parameters={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        )
        text = '[{"command": "ls"}]'
        results = ToolCallNormalizer.extract_tool_calls(
            text, ToolProtocol.LFM25, tools=[self._bash_tool(), other_tool],
        )
        self.assertEqual(results[0].tool_name, "")

    def test_flat_object_missing_required_key_does_not_match(self):
        text = '[{"unrelated_key": "value"}]'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25, tools=[self._bash_tool()])
        self.assertEqual(results[0].tool_name, "")

    def test_well_formed_envelope_not_affected_by_inference(self):
        """A properly-formed {"name","arguments"} call must not be re-inferred."""
        text = '[{"name": "bash", "arguments": {"command": "ls"}}]'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25, tools=[self._bash_tool()])
        self.assertEqual(results[0].tool_name, "bash")
        self.assertEqual(results[0].tool_input, {"command": "ls"})

    def test_tool_with_no_required_params_never_matched(self):
        """A tool with no required keys can't safely anchor inference -- too ambiguous."""
        vague_tool = ToolDefinition(
            name="vague", description="no required params",
            parameters={"type": "object", "properties": {"command": {"type": "string"}}},
        )
        text = '[{"command": "ls"}]'
        results = ToolCallNormalizer.extract_tool_calls(text, ToolProtocol.LFM25, tools=[vague_tool])
        self.assertEqual(results[0].tool_name, "")


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
