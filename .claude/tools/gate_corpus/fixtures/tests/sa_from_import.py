import inspect

from bot import alpha_cmd


def test_alpha_has_a_guard():
    assert "reply_text" in inspect.getsource(alpha_cmd)
