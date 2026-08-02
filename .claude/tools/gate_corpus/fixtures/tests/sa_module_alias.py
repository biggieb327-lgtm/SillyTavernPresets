import inspect

import bot as b


def test_alpha_has_a_guard():
    assert "reply_text" in inspect.getsource(b.alpha_cmd)
