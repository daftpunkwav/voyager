"""ThinkSplitter tests: inline <think> reasoning separation (streaming state
machine and one-shot split), including tags split across chunks."""

from llm.think_split import ThinkSplitter, split_inline_think


def _feed_all(splitter: ThinkSplitter, chunks: list[str]) -> tuple[str, str]:
    answer, reasoning = "", ""
    for c in chunks:
        a, r = splitter.feed(c)
        answer += a
        reasoning += r
    ta, tr = splitter.flush()
    return answer + ta, reasoning + tr


class TestThinkSplitter:
    def test_plain_text_passthrough(self) -> None:
        answer, reasoning = _feed_all(ThinkSplitter(), ["Hello", " world"])
        assert answer == "Hello world"
        assert reasoning == ""

    def test_complete_think_block(self) -> None:
        answer, reasoning = _feed_all(ThinkSplitter(), ["<think>pondering</think>", "The answer."])
        assert answer == "The answer."
        assert reasoning == "pondering"

    def test_open_tag_split_across_chunks(self) -> None:
        # "<thi" | "nk>" — the partial open tag is held back until complete
        answer, reasoning = _feed_all(ThinkSplitter(), ["A<thi", "nk>hidden</think>B"])
        assert answer == "AB"
        assert reasoning == "hidden"

    def test_close_tag_split_across_chunks(self) -> None:
        answer, reasoning = _feed_all(ThinkSplitter(), ["<think>x</thi", "nk>done"])
        assert answer == "done"
        assert reasoning == "x"

    def test_unclosed_think_goes_to_reasoning_on_flush(self) -> None:
        answer, reasoning = _feed_all(ThinkSplitter(), ["<think>still thinking..."])
        assert answer == ""
        assert reasoning == "still thinking..."

    def test_multiple_think_blocks(self) -> None:
        answer, reasoning = _feed_all(ThinkSplitter(), ["<think>a</think>X<think>b</think>", "Y"])
        assert answer == "XY"
        assert reasoning == "ab"

    def test_partial_suffix_shorter_than_tag(self) -> None:
        # "A<" ends with "<" (prefix of "<think>"): held, then released as text
        answer, reasoning = _feed_all(ThinkSplitter(), ["A<", " B"])
        assert answer == "A< B"
        assert reasoning == ""


class TestSplitInlineThink:
    def test_no_think(self) -> None:
        assert split_inline_think("plain") == ("plain", "")

    def test_with_think(self) -> None:
        answer, reasoning = split_inline_think("<think>r</think>answer")
        assert answer == "answer"
        assert reasoning == "r"

    def test_empty(self) -> None:
        assert split_inline_think("") == ("", "")
