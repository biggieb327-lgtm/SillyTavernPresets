import pytest

from skillforge.llm import LLM, MockLLM, extract_json, scripted


def test_mock_is_an_llm_and_records_calls():
    m = MockLLM(lambda msgs: "hi")
    assert isinstance(m, LLM)
    assert m.chat([{"role": "user", "content": "x"}]) == "hi"
    assert len(m.calls) == 1


def test_scripted_returns_in_order_then_sticks():
    r = scripted(["a", "b"])
    assert [r([]) for _ in range(4)] == ["a", "b", "b", "b"]


def test_extract_json_plain_object():
    assert extract_json('{"op": "append"}') == {"op": "append"}


def test_extract_json_with_prose_and_fence():
    text = 'Here is my plan.\n```json\n{"target": "s", "op": "create"}\n```\ndone'
    assert extract_json(text) == {"target": "s", "op": "create"}


def test_extract_json_array():
    assert extract_json("prefix [1, 2, 3] suffix") == [1, 2, 3]


def test_extract_json_raises_when_absent():
    with pytest.raises(ValueError, match="no parseable JSON"):
        extract_json("no json here")
