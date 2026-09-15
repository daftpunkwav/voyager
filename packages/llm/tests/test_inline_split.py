"""InlineTagSplitter tests: inline <think> reasoning and <tool_call> block
separation (streaming state machine and one-shot split), including tags
split across chunks."""

from llm.inline_split import InlineTagSplitter, parse_tool_blocks, split_inline


def _feed_all(splitter: InlineTagSplitter, chunks: list[str]) -> tuple[str, str, list[str]]:
    answer, reasoning = "", ""
    for c in chunks:
        a, r = splitter.feed(c)
        answer += a
        reasoning += r
    ta, tr = splitter.flush()
    return answer + ta, reasoning + tr, splitter.tool_blocks


class TestThinkSplit:
    def test_plain_text_passthrough(self) -> None:
        answer, reasoning, blocks = _feed_all(InlineTagSplitter(), ["Hello", " world"])
        assert answer == "Hello world"
        assert reasoning == ""
        assert blocks == []

    def test_complete_think_block(self) -> None:
        answer, reasoning, _ = _feed_all(
            InlineTagSplitter(), ["<think>pondering</think>", "The answer."]
        )
        assert answer == "The answer."
        assert reasoning == "pondering"

    def test_open_tag_split_across_chunks(self) -> None:
        # "<thi" | "nk>" — the partial open tag is held back until complete
        answer, reasoning, _ = _feed_all(InlineTagSplitter(), ["A<thi", "nk>hidden</think>B"])
        assert answer == "AB"
        assert reasoning == "hidden"

    def test_close_tag_split_across_chunks(self) -> None:
        answer, reasoning, _ = _feed_all(InlineTagSplitter(), ["<think>x</thi", "nk>done"])
        assert answer == "done"
        assert reasoning == "x"

    def test_unclosed_think_goes_to_reasoning_on_flush(self) -> None:
        answer, reasoning, _ = _feed_all(InlineTagSplitter(), ["<think>still thinking..."])
        assert answer == ""
        assert reasoning == "still thinking..."

    def test_multiple_think_blocks(self) -> None:
        answer, reasoning, _ = _feed_all(
            InlineTagSplitter(), ["<think>a</think>X<think>b</think>", "Y"]
        )
        assert answer == "XY"
        assert reasoning == "ab"

    def test_partial_suffix_shorter_than_tag(self) -> None:
        # "A<" ends with "<" (prefix of "<think>"): held, then released as text
        answer, reasoning, _ = _feed_all(InlineTagSplitter(), ["A<", " B"])
        assert answer == "A< B"
        assert reasoning == ""


class TestToolCallSplit:
    def test_block_captured_out_of_text(self) -> None:
        chunks = [
            "Sure. ",
            '<tool_call>\n{"name": "load_skill", "arguments": {"skill_name": "x"}}\n</tool_call>',
            " Done.",
        ]
        answer, reasoning, blocks = _feed_all(InlineTagSplitter(), chunks)
        assert answer == "Sure.  Done."
        assert reasoning == ""
        assert blocks == ['\n{"name": "load_skill", "arguments": {"skill_name": "x"}}\n']

    def test_tags_split_across_chunks(self) -> None:
        # Both the open and close tags arrive cut mid-tag
        answer, _, blocks = _feed_all(
            InlineTagSplitter(),
            ["A<tool_ca", 'll>{"name": "f"}</tool_', "call>B"],
        )
        assert answer == "AB"
        assert blocks == ['{"name": "f"}']

    def test_unclosed_block_captured_on_flush(self) -> None:
        answer, _, blocks = _feed_all(InlineTagSplitter(), ["A<tool_call>", '{"name": "f"}'])
        assert answer == "A"
        assert blocks == ['{"name": "f"}']

    def test_garbled_block_never_reaches_text(self) -> None:
        # MiniMax echo variant: non-JSON inner content — captured, not shown
        answer, _, blocks = _feed_all(
            InlineTagSplitter(), ['<tool_call>]<]minimax[>[<invoke name="x"/></tool_call>A']
        )
        assert answer == "A"
        assert blocks == [']<]minimax[>[<invoke name="x"/>']

    def test_tool_tag_inside_think_stays_reasoning(self) -> None:
        # Inside a think block the markup is model thinking, not a call
        answer, reasoning, blocks = _feed_all(
            InlineTagSplitter(), ["<think>plan <tool_call>{}</tool_call></think>out"]
        )
        assert answer == "out"
        assert reasoning == "plan <tool_call>{}</tool_call>"
        assert blocks == []

    def test_multiple_blocks(self) -> None:
        answer, _, blocks = _feed_all(
            InlineTagSplitter(),
            ['<tool_call>{"name": "a"}</tool_call>x<tool_call>{"name": "b"}</tool_call>'],
        )
        assert answer == "x"
        assert blocks == ['{"name": "a"}', '{"name": "b"}']


class TestSplitInline:
    def test_no_tags(self) -> None:
        assert split_inline("plain") == ("plain", "", [])

    def test_with_think(self) -> None:
        answer, reasoning, blocks = split_inline("<think>r</think>answer")
        assert answer == "answer"
        assert reasoning == "r"
        assert blocks == []

    def test_with_tool_call(self) -> None:
        answer, reasoning, blocks = split_inline('A<tool_call>{"name": "f"}</tool_call>B')
        assert answer == "AB"
        assert reasoning == ""
        assert blocks == ['{"name": "f"}']

    def test_empty(self) -> None:
        assert split_inline("") == ("", "", [])


class TestParseToolBlocks:
    def test_single_object(self) -> None:
        calls = parse_tool_blocks(['{"name": "f", "arguments": {"a": 1}}'])
        assert calls == [{"id": "inline_0", "name": "f", "arguments": {"a": 1}}]

    def test_json_array(self) -> None:
        calls = parse_tool_blocks(['[{"name": "a"}, {"name": "b"}]'])
        assert [c["name"] for c in calls] == ["a", "b"]

    def test_string_arguments_parsed(self) -> None:
        calls = parse_tool_blocks(['{"name": "f", "arguments": "{\\"k\\": 1}"}'])
        assert calls[0]["arguments"] == {"k": 1}

    def test_unparseable_dropped(self) -> None:
        assert parse_tool_blocks([']<]minimax[>[<invoke name="x"/>', ""]) == []

    def test_nameless_entry_dropped(self) -> None:
        assert parse_tool_blocks(['{"arguments": {}}']) == []

    def test_non_dict_arguments_become_empty(self) -> None:
        calls = parse_tool_blocks(['{"name": "f", "arguments": [1, 2]}'])
        assert calls[0]["arguments"] == {}

    def test_null_function_field_does_not_crash(self) -> None:
        # Poisoned echo variant: "function": null must degrade to the flat
        # shape (name wins), never raise
        calls = parse_tool_blocks(['{"name": "f", "function": null}'])
        assert calls == [{"id": "inline_0", "name": "f", "arguments": {}}]

    def test_function_shape_fallback_for_name_and_arguments(self) -> None:
        # OpenAI-echo shape inside the block: name/arguments live under function
        calls = parse_tool_blocks(['{"function": {"name": "f", "arguments": "{\\"k\\": 1}"}}'])
        assert calls == [{"id": "inline_0", "name": "f", "arguments": {"k": 1}}]

    def test_array_entries_get_unique_ids(self) -> None:
        # Two calls in one block: ids must stay unique or result pairing on
        # the following turn is ambiguous
        calls = parse_tool_blocks(['[{"name": "a"}, {"name": "b"}]'])
        assert [c["id"] for c in calls] == ["inline_0", "inline_1"]
